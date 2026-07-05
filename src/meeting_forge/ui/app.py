"""Interfaz Streamlit de MeetingForge — visor de reuniones procesadas."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, cast

import streamlit as st

from meeting_forge import meeting_store
from meeting_forge.analysis.insights_editing import (
    actions_to_rows,
    decisions_to_rows,
    rows_to_actions,
    rows_to_decisions,
)
from meeting_forge.analysis.schemas import MeetingInsights
from meeting_forge.config import configure_logging, settings
from meeting_forge.generation.diffing import unified_md_diff
from meeting_forge.generation.schemas import MeetingMetadata
from meeting_forge.git_integration import pr as pr_module
from meeting_forge.git_integration import publisher as pub_module
from meeting_forge.ingestion.schemas import Transcript, TranscriptSegment
from meeting_forge.system_status import (
    CheckResult,
    check_ffmpeg,
    check_gh,
    check_llm_key,
    check_rag_index,
)
from meeting_forge.ui.evidence import read_source_slice
from meeting_forge.ui.loader import (
    GeneratedDocView,
    MeetingData,
    MeetingSummary,
    list_meetings,
    load_generated_docs,
    load_meeting,
    load_publish_state,
)
from meeting_forge.validation import store as val_store
from meeting_forge.validation.schemas import MeetingValidationState, ValidationStatus

_P = ParamSpec("_P")
_R = TypeVar("_R")

_OUTPUTS_DIR: Path = settings.data_dir / "outputs"
_PROJECT_ROOT: Path = settings.project_root

_KIND_LABELS: dict[str, str] = {
    "adr": "ADR",
    "acta": "Acta",
    "roadmap": "Roadmap",
    "technical-doc": "Doc técnica",
}


# ---------------------------------------------------------------------------
# Carga con caché de Streamlit (evita releer JSON en cada interacción)
# ---------------------------------------------------------------------------


def _cache(fn: Callable[_P, _R]) -> Callable[_P, _R]:
    return cast(Callable[_P, _R], st.cache_data(show_spinner=False)(fn))


@_cache
def _cached_load_meeting(meeting_dir_str: str) -> MeetingData:
    return load_meeting(Path(meeting_dir_str))


@_cache
def _cached_load_docs(meeting_dir_str: str) -> list[GeneratedDocView]:
    return load_generated_docs(Path(meeting_dir_str))


# Check del índice RAG con caché corta (abrir Chroma en cada rerun sería costoso).
_cached_rag_check: Callable[[], CheckResult] = cast(
    Callable[[], CheckResult],
    st.cache_data(show_spinner=False, ttl=60)(check_rag_index),
)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def _render_sidebar(meetings: list[MeetingSummary]) -> MeetingSummary:
    """Renderiza el selector de reunión en el sidebar (preselecciona la recién procesada)."""
    labels = [m.meeting_id for m in meetings]
    default_idx = 0
    target = st.session_state.get("selected_meeting_id")
    if target:
        for i, summary in enumerate(meetings):
            if summary.meeting_id == target:
                default_idx = i
                break
    idx_raw = st.sidebar.selectbox(
        "Selecciona reunión",
        range(len(labels)),
        index=default_idx,
        format_func=lambda i: labels[i],
    )
    idx: int = int(idx_raw) if idx_raw is not None else 0
    return meetings[idx]


def _render_sidebar_metadata(metadata: dict[str, object]) -> None:
    """Renderiza el bloque de metadatos del run en el sidebar."""
    st.sidebar.divider()
    st.sidebar.subheader("Metadatos del run")
    st.sidebar.markdown(f"**Proveedor**: {metadata.get('provider', '—')}")
    st.sidebar.markdown(f"**Whisper**: {metadata.get('whisper_model', '—')}")
    rag_enabled = metadata.get("rag_enabled")
    st.sidebar.markdown(f"**RAG**: {'Sí' if rag_enabled else 'No'}")
    if metadata.get("embedding_model"):
        st.sidebar.markdown(f"**Embeddings**: {metadata['embedding_model']}")


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------


def _render_resumen(data: MeetingData) -> None:
    """Tab Resumen: summary ejecutivo, topics y contadores."""
    if data.insights.summary:
        st.subheader("Resumen ejecutivo")
        st.write(data.insights.summary)

    if data.insights.topics:
        st.subheader("Temas")
        n_cols = min(len(data.insights.topics), 4)
        cols = st.columns(n_cols)
        for i, topic in enumerate(data.insights.topics):
            cols[i % n_cols].info(topic)

    st.divider()
    col1, col2 = st.columns(2)
    col1.metric("Decisiones", len(data.insights.decisions))
    col2.metric("Tareas", len(data.insights.action_items))


def _fmt_timestamp(value: object) -> str:
    """Formatea segundos (int/float) como `mm:ss`; devuelve '' si no es numérico."""
    if not isinstance(value, (int, float)):
        return ""
    total = int(value)
    return f"{total // 60:02d}:{total % 60:02d}"


def _render_speaker_names(transcript: Transcript, meeting_dir: Path, wkey: str) -> None:
    """Formulario de mapeo etiqueta → nombre real de hablante (UX-3)."""
    labels = sorted({seg.speaker for seg in transcript.segments if seg.speaker})
    if not labels:
        return
    with st.expander("🗣️ Nombres de hablantes"):
        current = meeting_store.load_speaker_names(meeting_dir)
        new_names = {
            label: st.text_input(
                label,
                value=current.get(label, ""),
                key=f"spk_{wkey}{label}",
                placeholder="Nombre real (opcional)",
            )
            for label in labels
        }
        if st.button("Guardar nombres", key=f"spk_save_{wkey}"):
            meeting_store.save_speaker_names(meeting_dir, new_names)
            st.cache_data.clear()
            st.rerun()
        st.caption(
            "Los nombres se aplican al re-extraer insights: el LLM asigna responsables "
            "mucho mejor con nombres reales delante de cada intervención."
        )


def _rerun_extraction_ui(meeting_dir: Path) -> None:
    """Ejecuta la re-extracción (UX-2) con progreso y refresca la UI."""
    from meeting_forge.pipeline import rerun_extraction  # import perezoso (dependencias pesadas)

    with st.status("Re-extrayendo insights…", expanded=True) as status:
        try:
            res = rerun_extraction(meeting_dir, progress=status.write)
        except Exception as exc:
            status.update(label="Error al re-extraer", state="error")
            st.error(f"Error al re-extraer insights: {exc}")
            return
        status.update(
            label=(
                f"Listo: {res.n_decisions} decisiones · {res.n_actions} tareas · "
                f"{res.n_documents} documentos"
            ),
            state="complete",
        )
    st.session_state.pop(f"val_state_{meeting_dir}", None)
    st.cache_data.clear()
    st.rerun()


def _render_transcript(data: MeetingData, meeting_dir: Path) -> None:
    """Tab Transcript: editor de segmentos (UX-2) + nombres de hablantes (UX-3)."""
    try:
        transcript = meeting_store.load_transcript(meeting_dir)
    except (OSError, ValueError) as exc:
        st.warning(f"Transcript no cargable ({exc}); se muestra en solo lectura.")
        st.dataframe(data.transcript_segments, use_container_width=True)
        return
    if not transcript.segments:
        st.info("No hay segmentos de transcripción disponibles.")
        return

    wkey = f"{meeting_dir.name}_"
    _render_speaker_names(transcript, meeting_dir, wkey)

    rows = [
        {
            "Inicio": _fmt_timestamp(seg.start),
            "Fin": _fmt_timestamp(seg.end),
            "Texto": seg.text,
            "Speaker": seg.speaker or "",
        }
        for seg in transcript.segments
    ]
    edited_rows = st.data_editor(
        rows,
        use_container_width=True,
        disabled=["Inicio", "Fin"],
        key=f"tredit_{wkey}",
    )
    st.caption(
        "Corrige el texto (o el speaker) de los segmentos y guarda; vaciar el texto elimina "
        "el segmento. Después usa «Re-extraer insights» para que la corrección llegue a "
        "insights y documentos."
    )

    llm_ok = check_llm_key().ok
    col_save, col_rerun = st.columns(2)
    with col_save:
        if st.button("💾 Guardar transcript", key=f"trsave_{wkey}"):
            new_segments = [
                TranscriptSegment(
                    start=seg.start,
                    end=seg.end,
                    text=str(row.get("Texto") or "").strip(),
                    speaker=str(row.get("Speaker") or "").strip() or None,
                )
                for seg, row in zip(transcript.segments, edited_rows, strict=False)
                if str(row.get("Texto") or "").strip()
            ]
            meeting_store.save_transcript(
                meeting_dir,
                Transcript(
                    segments=new_segments,
                    duration_seconds=transcript.duration_seconds,
                    language=transcript.language,
                ),
            )
            # El estado del editor queda ligado a las filas antiguas: descartarlo evita
            # que ediciones previas se re-apliquen desalineadas tras el guardado.
            st.session_state.pop(f"tredit_{wkey}", None)
            st.cache_data.clear()
            st.rerun()
    with col_rerun:
        if st.button(
            "🔁 Re-extraer insights",
            key=f"trrerun_{wkey}",
            type="primary",
            disabled=not llm_ok,
            help=None
            if llm_ok
            else "Configura la API key del proveedor LLM (ver Estado del sistema)",
        ):
            _rerun_extraction_ui(meeting_dir)


def _render_source_refs(sources: list[object]) -> None:
    """Renderiza el sub-expander de fuentes para una decisión o tarea."""
    from meeting_forge.rag.schemas import SourceRef

    source_refs = [SourceRef.model_validate(s) for s in sources if isinstance(s, dict)]
    if not source_refs:
        return
    with st.expander(f"Fuentes ({len(source_refs)})"):
        for src in source_refs:
            breadcrumb = " > ".join(src.section_path) if src.section_path else "—"
            st.caption(f"`{src.source_path}` — L{src.line_start}–{src.line_end} — _{breadcrumb}_")


def _meeting_audio_path(data: MeetingData) -> Path | None:
    """Ruta del audio origen si está disponible en disco (para el reproductor · UX-6)."""
    meta = data.result.get("meeting_metadata")
    if not isinstance(meta, dict):
        return None
    raw = meta.get("source_audio")
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw)
    return path if path.exists() else None


def _render_transcript_refs(refs: list[Any], audio_path: Path | None, key: str) -> None:
    """Muestra los momentos citados del transcript (mm:ss) y un reproductor de audio (UX-6)."""
    if not refs:
        return
    st.caption("🎧 Momentos en la reunión:")
    for ref in refs:
        st.markdown(f"`{_fmt_timestamp(ref.start)}` — {ref.text}")
    if audio_path is not None:
        # Arranca en el primer momento citado (st.audio no admite varios inicios simultáneos).
        st.audio(str(audio_path), start_time=int(refs[0].start))


def _render_insights_editor(data: MeetingData, meeting_dir: Path, wkey: str) -> None:
    """Modo edición de insights (UX-5): corregir la fuente y regenerar todos los documentos."""
    summary = st.text_area(
        "Resumen ejecutivo", value=data.insights.summary, key=f"ins_summary_{wkey}"
    )
    topics_csv = st.text_input(
        "Temas (separados por comas)",
        value=", ".join(data.insights.topics),
        key=f"ins_topics_{wkey}",
    )

    st.markdown("**Decisiones**")
    dec_rows = st.data_editor(
        decisions_to_rows(data.insights.decisions),
        num_rows="dynamic",
        use_container_width=True,
        disabled=["#"],
        key=f"ins_dec_{wkey}",
    )
    st.markdown("**Tareas**")
    act_rows = st.data_editor(
        actions_to_rows(data.insights.action_items),
        num_rows="dynamic",
        use_container_width=True,
        disabled=["#"],
        key=f"ins_act_{wkey}",
    )
    st.caption(
        "Las fuentes (citas) de cada fila se conservan al editar; las filas nuevas empiezan "
        "sin fuentes. Al guardar se regeneran TODOS los documentos desde los insights "
        "corregidos y la validación vuelve a Pendiente."
    )

    llm_ok = check_llm_key().ok
    if st.button(
        "💾 Guardar insights y regenerar documentos",
        type="primary",
        key=f"ins_save_{wkey}",
        disabled=not llm_ok,
        help=None if llm_ok else "Configura la API key del proveedor LLM (ver Estado del sistema)",
    ):
        from meeting_forge.pipeline import regenerate_documents  # import perezoso

        new_insights = MeetingInsights(
            decisions=rows_to_decisions(list(dec_rows), data.insights.decisions),
            action_items=rows_to_actions(list(act_rows), data.insights.action_items),
            topics=[t.strip() for t in topics_csv.split(",") if t.strip()],
            summary=summary.strip(),
        )
        meeting_store.save_insights(meeting_dir, new_insights)
        with st.status("Regenerando documentos…", expanded=True) as status:
            try:
                regenerate_documents(meeting_dir, progress=status.write)
            except Exception as exc:
                status.update(label="Error al regenerar", state="error")
                st.error(f"Insights guardados, pero la regeneración de documentos falló: {exc}")
                st.cache_data.clear()
                return
            status.update(label="Documentos regenerados", state="complete")
        # Editor y validación quedan ligados a los insights/documentos anteriores.
        for prefix in ("ins_dec_", "ins_act_", "ins_summary_", "ins_topics_"):
            st.session_state.pop(f"{prefix}{wkey}", None)
        st.session_state.pop(f"val_state_{meeting_dir}", None)
        st.cache_data.clear()
        st.rerun()


def _render_insights(data: MeetingData, meeting_dir: Path) -> None:
    """Tab Insights: decisiones y tareas con sus fuentes, con modo edición (UX-5)."""
    wkey = f"{meeting_dir.name}_"
    if st.toggle("✏️ Editar insights", key=f"ins_edit_{wkey}"):
        _render_insights_editor(data, meeting_dir, wkey)
        return

    audio_path = _meeting_audio_path(data)

    if data.insights.decisions:
        st.subheader("Decisiones")
        for i, dec in enumerate(data.insights.decisions):
            with st.expander(dec.title):
                st.write(dec.description)
                if dec.rationale:
                    st.caption(f"Justificación: {dec.rationale}")
                if dec.owners:
                    st.write(f"Responsables: {', '.join(dec.owners)}")
                if dec.tags:
                    st.write(f"Tags: {', '.join(dec.tags)}")
                if dec.sources:
                    _render_source_refs([s.model_dump() for s in dec.sources])
                _render_transcript_refs(dec.transcript_refs, audio_path, f"{wkey}dec{i}")
    else:
        st.info("No se identificaron decisiones.")

    if data.insights.action_items:
        st.subheader("Tareas")
        for i, action in enumerate(data.insights.action_items):
            label = (
                action.description[:60] + "…"
                if len(action.description) > 60
                else action.description
            )
            with st.expander(label):
                st.write(action.description)
                if action.assignee:
                    st.write(f"Asignado a: {action.assignee}")
                if action.deadline:
                    st.write(f"Plazo: {action.deadline}")
                if action.sources:
                    _render_source_refs([s.model_dump() for s in action.sources])
                _render_transcript_refs(action.transcript_refs, audio_path, f"{wkey}act{i}")
    else:
        st.info("No se identificaron tareas.")


def _render_chat(data: MeetingData, meeting_dir: Path) -> None:
    """Tab Preguntar: chat de Q&A sobre la reunión con citas al minuto de audio (UX-11)."""
    st.caption(
        "Pregunta en lenguaje natural sobre esta reunión. Las respuestas se basan en el resumen, "
        "las decisiones/tareas y los fragmentos relevantes del transcript."
    )
    try:
        transcript = meeting_store.load_transcript(meeting_dir)
    except (OSError, ValueError):
        st.warning("Transcript no disponible; el chat no puede responder.")
        return

    audio_path = _meeting_audio_path(data)
    hist_key = f"chat_{meeting_dir.name}"
    cost_key = f"chatcost_{meeting_dir.name}"
    history = st.session_state.setdefault(hist_key, [])

    total_cost = st.session_state.get(cost_key, 0.0)
    top = st.columns([3, 1])
    if total_cost:
        top[1].metric("Coste sesión", f"${total_cost:.4f}")
    if history and top[0].button("🧹 Limpiar conversación"):
        st.session_state[hist_key] = []
        st.session_state[cost_key] = 0.0
        st.rerun()

    for msg in history:
        with st.chat_message(msg.role):
            st.markdown(msg.content)
            if msg.role == "assistant" and msg.cited_segments:
                cites = " · ".join(
                    f"`{_fmt_timestamp(transcript.segments[i].start)}` [S{i}]"
                    for i in msg.cited_segments
                    if 0 <= i < len(transcript.segments)
                )
                if cites:
                    st.caption(f"🎧 {cites}")
                if audio_path is not None and msg.cited_segments:
                    first = msg.cited_segments[0]
                    if 0 <= first < len(transcript.segments):
                        st.audio(str(audio_path), start_time=int(transcript.segments[first].start))

    if not check_llm_key().ok:
        st.info("Configura la API key del proveedor LLM para chatear (ver Estado del sistema).")
        return

    question = st.chat_input("Pregunta sobre la reunión")
    if not question:
        return
    from meeting_forge.analysis.llm_client import get_provider
    from meeting_forge.chat import ChatMessage, answer_question
    from meeting_forge.observability import TelemetryCollector

    collector = TelemetryCollector()
    try:
        provider = get_provider(collector=collector)
        answer = answer_question(provider, transcript, data.insights, question, history)
    except Exception as exc:
        st.error(f"Error al responder: {exc}")
        return
    history.append(ChatMessage(role="user", content=question))
    history.append(
        ChatMessage(role="assistant", content=answer.text, cited_segments=answer.cited_segments)
    )
    st.session_state[hist_key] = history
    st.session_state[cost_key] = total_cost + collector.build().total_cost_usd
    st.rerun()


def _render_evidencia(data: MeetingData) -> None:
    """Tab Evidencia: rodajas de los archivos fuente citados por decisiones y tareas."""
    items = [
        ("Decisión", dec.title, dec.sources) for dec in data.insights.decisions if dec.sources
    ] + [
        (
            "Tarea",
            action.description[:60] + ("…" if len(action.description) > 60 else ""),
            action.sources,
        )
        for action in data.insights.action_items
        if action.sources
    ]

    if not items:
        st.info(
            "Ninguna decisión ni tarea tiene fuentes de evidencia. "
            "El RAG puede estar desactivado o no recuperó chunks relevantes."
        )
        return

    labels = [f"{kind}: {title}" for kind, title, _ in items]
    idx_raw = st.selectbox(
        "Selecciona decisión o tarea",
        range(len(labels)),
        format_func=lambda i: labels[i],
    )
    idx = int(idx_raw) if idx_raw is not None else 0
    _, _, sources = items[idx]

    st.divider()
    for src in sources:
        breadcrumb = " > ".join(src.section_path) if src.section_path else "sin sección"
        st.markdown(
            f"**`{src.source_path}`** — Líneas {src.line_start}–{src.line_end} — _{breadcrumb}_"
        )
        result = read_source_slice(
            source_path=src.source_path,
            line_start=src.line_start,
            line_end=src.line_end,
            base_dir=_PROJECT_ROOT,
        )
        if result.found:
            st.code(result.text, language="markdown")
        else:
            st.warning(result.warning)
        st.divider()


def _render_documentos(docs: list[GeneratedDocView]) -> None:
    """Tab Documentos: ADRs y actas generados con opción de descarga."""
    if not docs:
        st.info(
            "No hay documentos generados. "
            "La generación puede estar desactivada o aún no se ha ejecutado."
        )
        return

    for doc in docs:
        kind_label = _KIND_LABELS.get(doc.kind, doc.kind.upper())
        with st.expander(f"[{kind_label}] {doc.filename}"):
            if doc.diff:
                with st.expander("Cambios propuestos (diff)"):
                    st.code(doc.diff, language="diff")
            st.markdown(doc.markdown_content)
            st.download_button(
                label=f"Descargar {doc.filename}",
                data=doc.markdown_content,
                file_name=doc.filename,
                mime="text/markdown",
                key=f"dl_{doc.kind}_{doc.filename}",
            )


# ---------------------------------------------------------------------------
# Tab Validación (Fase 4)
# ---------------------------------------------------------------------------

_STATUS_ICON: dict[str, str] = {
    ValidationStatus.PENDING.value: "⏳",
    ValidationStatus.APPROVED.value: "✅",
    ValidationStatus.REJECTED.value: "❌",
    ValidationStatus.EDITED.value: "✏️",
}


def _render_validacion(data: MeetingData, docs: list[GeneratedDocView], meeting_dir: Path) -> None:
    """Tab Validación: aprobación/rechazo de documentos y publicación a Git."""
    published = load_publish_state(meeting_dir)
    if published:
        if published.pr_url:
            pr_link = f" · [Abrir PR]({published.pr_url})"
        elif published.compare_url:
            pr_link = f" · [Abrir PR (compare)]({published.compare_url})"
        else:
            pr_link = ""
        st.success(
            f"Publicado — Rama: `{published.branch}` · Commit: `{published.commit_sha}`{pr_link}"
        )
        st.divider()

    if not docs:
        st.info("No hay documentos generados para validar.")
        return

    state_key = f"val_state_{meeting_dir}"
    if state_key not in st.session_state:
        st.session_state[state_key] = val_store.initialize_pending(meeting_dir, docs)

    # Las claves de widget incluyen la reunión: filenames repetidos entre reuniones (p.ej.
    # roadmap.md) compartirían estado y "Aprobar" podría arrastrar la edición de otra reunión.
    wkey = f"{meeting_dir.name}_"

    state: MeetingValidationState = st.session_state[state_key]

    col1, col2, col3 = st.columns(3)
    col1.metric("Aprobados", state.approved_count())
    col2.metric("Rechazados", state.rejected_count())
    col3.metric("Pendientes", state.pending_count())
    st.divider()

    for doc in docs:
        record = state.records.get(doc.filename)
        if record is None:
            continue
        icon = _STATUS_ICON.get(record.status.value, "?")
        kind_label = _KIND_LABELS.get(doc.kind, doc.kind.upper())
        expanded = record.status == ValidationStatus.PENDING
        with st.expander(f"{icon} [{kind_label}] {doc.filename}", expanded=expanded):
            effective = val_store.get_effective_content(state, doc.filename, doc.markdown_content)
            prev_tab, edit_tab = st.tabs(["Preview", "Editar"])
            with prev_tab:
                if doc.diff:
                    st.caption("Cambios propuestos vs documento existente:")
                    st.code(doc.diff, language="diff")
                st.markdown(effective)
            with edit_tab:
                edited_text = st.text_area(
                    "Contenido Markdown",
                    value=effective,
                    height=400,
                    key=f"edit_{wkey}{doc.filename}",
                    label_visibility="collapsed",
                )
                if edited_text.strip() != doc.markdown_content.strip():
                    with st.expander("Diferencias vs original generado"):
                        st.code(
                            unified_md_diff(doc.markdown_content, edited_text, doc.filename),
                            language="diff",
                        )
                if st.button("Guardar edición y aprobar", key=f"save_{wkey}{doc.filename}"):
                    state = val_store.mark_approved(state, doc.filename, edited_content=edited_text)
                    val_store.save_state(meeting_dir, state)
                    st.session_state[state_key] = state
                    st.rerun()

            btn_col, reason_col, reset_col = st.columns([1, 2, 1])
            with btn_col:
                if st.button("Aprobar", key=f"approve_{wkey}{doc.filename}", type="primary"):
                    # F11: si el usuario tiene una edición en curso, se aprueba CON ella (antes se
                    # perdía silenciosamente al pulsar Aprobar en vez de "Guardar edición").
                    current_edit = st.session_state.get(
                        f"edit_{wkey}{doc.filename}", doc.markdown_content
                    )
                    if current_edit.strip() != doc.markdown_content.strip():
                        state = val_store.mark_approved(
                            state, doc.filename, edited_content=current_edit
                        )
                    else:
                        state = val_store.mark_approved(state, doc.filename)
                    val_store.save_state(meeting_dir, state)
                    st.session_state[state_key] = state
                    st.rerun()
            with reason_col:
                reason = st.text_input(
                    "Motivo",
                    key=f"reason_{wkey}{doc.filename}",
                    placeholder="Motivo de rechazo (opcional)",
                    label_visibility="collapsed",
                )
                if st.button("Rechazar", key=f"reject_{wkey}{doc.filename}"):
                    state = val_store.mark_rejected(state, doc.filename, reason=reason)
                    val_store.save_state(meeting_dir, state)
                    st.session_state[state_key] = state
                    st.rerun()
            with reset_col:
                if st.button("Reset", key=f"reset_{wkey}{doc.filename}"):
                    state = val_store.reset_record(state, doc.filename)
                    val_store.save_state(meeting_dir, state)
                    st.session_state[state_key] = state
                    st.rerun()

            if record.auto_approved:
                st.caption("🤖 Auto-aprobado (modo automático)")
            if record.validated_at:
                st.caption(f"Validado: {record.validated_at.strftime('%Y-%m-%d %H:%M UTC')}")
            if record.rejection_reason:
                st.caption(f"Motivo: {record.rejection_reason}")

    st.divider()

    gh_available = pr_module.is_gh_available(settings.gh_executable)
    gh_auth = gh_available and pr_module.is_gh_authenticated(settings.gh_executable)
    gh_ok = gh_available and gh_auth
    git_enabled = settings.git_integration_enabled
    n_approved = state.approved_count()

    if not git_enabled:
        st.warning(
            "La integración Git está desactivada. "
            "Actívala con `GIT_INTEGRATION_ENABLED=true` en `.env`."
        )
    elif not gh_available:
        st.warning(
            "El CLI `gh` no está instalado o no se encuentra en el PATH. "
            "Instálalo para crear Pull Requests automáticamente."
        )
    elif not gh_auth:
        st.warning("El CLI `gh` no está autenticado. Ejecuta `gh auth login`.")

    publish_disabled = not git_enabled or not gh_ok or n_approved == 0
    btn_label = f"Publicar a Git ({n_approved} doc{'s' if n_approved != 1 else ''})"

    if st.button(btn_label, disabled=publish_disabled, type="primary"):
        # F3: usa la metadata persistida (fecha/título/audio) si está disponible, en vez de
        # reconstruirla con date=None (que perdía la fecha en la rama y el PR).
        meeting_meta_raw = data.result.get("meeting_metadata")
        if isinstance(meeting_meta_raw, dict):
            metadata = MeetingMetadata.model_validate(meeting_meta_raw)
        else:
            metadata = MeetingMetadata(
                meeting_id=data.meeting_id,
                title=data.meeting_id,
                date=None,
                source_audio=None,
            )
        with st.spinner("Publicando en Git..."):
            try:
                result = pub_module.publish_meeting(
                    meeting_dir=meeting_dir,
                    metadata=metadata,
                    validation_state=state,
                    docs=docs,
                )
                if result.pr_url:
                    st.success(f"Publicado — [Abrir PR]({result.pr_url})")
                elif result.compare_url:
                    st.success(
                        f"Publicado — Rama: `{result.branch}` · "
                        f"[Abrir PR (compare)]({result.compare_url})"
                    )
                else:
                    st.success(
                        f"Publicado — Rama: `{result.branch}` · Commit: `{result.commit_sha}`"
                    )
                st.balloons()
            except pub_module.NothingToPublishError:
                st.info(
                    "Nada que publicar: el contenido aprobado ya coincide con el del repositorio "
                    "destino."
                )
            except pub_module.PublishError as exc:
                st.error(f"Error al publicar: {exc}")


# ---------------------------------------------------------------------------
# Procesar nueva reunión (F4)
# ---------------------------------------------------------------------------


def _process_uploaded(
    uploaded: Any,
    use_rag: bool,
    use_gen: bool,
    title: str,
    attendees_csv: str = "",
    vocabulary: str = "",
    target_name: str | None = None,
) -> None:
    """Guarda el audio subido y ejecuta el pipeline con progreso por fase.

    `target_name` permite renombrar la entrada (UX-12: las grabaciones de micrófono llegan
    siempre con el mismo nombre genérico y pisarían la reunión anterior).
    """
    # import perezoso (dependencias pesadas)
    from meeting_forge.pipeline import parse_attendees, run_pipeline

    raw_dir = settings.data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    # BUG-5: usar solo el nombre base del fichero subido evita que un nombre con separadores o
    # `..` escriba fuera de data/raw (defensa contra path traversal vía nombre de archivo).
    safe_name = Path(target_name or uploaded.name).name
    audio_path = (raw_dir / safe_name).resolve()
    if not audio_path.is_relative_to(raw_dir.resolve()):
        st.error(f"Nombre de archivo no válido: {uploaded.name}")
        return
    audio_path.write_bytes(uploaded.getbuffer())

    with st.status("Procesando reunión…", expanded=True) as status:

        def _progress(message: str) -> None:
            status.write(message)

        try:
            result = run_pipeline(
                audio_path,
                use_rag=use_rag,
                use_generation=use_gen,
                meeting_title=title.strip(),
                attendees=parse_attendees(attendees_csv),
                vocabulary=vocabulary,
                progress=_progress,
            )
        except Exception as exc:
            status.update(label="Error al procesar", state="error")
            st.error(f"Error al procesar la reunión: {exc}")
            return
        status.update(
            label=(
                f"Listo: {result.n_decisions} decisiones · "
                f"{result.n_actions} tareas · {result.n_documents} documentos"
            ),
            state="complete",
        )

    # B-N2: los documentos se han regenerado; invalida la validación previa (en memoria y en disco)
    # para no arrastrar aprobaciones/ediciones que apuntaban al contenido anterior.
    val_store.clear_state(result.out_dir)
    st.session_state.pop(f"val_state_{result.out_dir}", None)

    st.cache_data.clear()
    st.session_state["selected_meeting_id"] = result.meeting_id
    st.rerun()


def _render_run_panel() -> None:
    """Panel en el sidebar para subir un audio (o grabarlo) y ejecutar el pipeline desde la UI."""
    with st.sidebar.expander("➕ Procesar nueva reunión"):
        uploaded = st.file_uploader(
            "Audio o vídeo de la reunión",
            # UX-13: acepta también grabaciones de Meet/Teams/Zoom (se extrae la pista de audio).
            type=["wav", "mp3", "m4a", "flac", "ogg", "mp4", "webm", "mkv", "mov", "avi"],
        )
        # UX-12: alternativa rápida sin salir de la app (notas de voz, reuniones improvisadas).
        recorded = st.audio_input("…o graba desde el micrófono")
        target_name: str | None = None
        source = uploaded
        if source is None and recorded is not None:
            source = recorded
            # El micrófono siempre entrega el mismo nombre genérico: sin renombrar, cada
            # grabación pisaría la reunión anterior.
            target_name = f"grabacion-{datetime.now():%Y%m%d-%H%M%S}.wav"

        use_rag = st.checkbox("Usar RAG", value=settings.rag_enabled)
        use_gen = st.checkbox("Generar documentos", value=settings.generation_enabled)
        title = st.text_input("Título (opcional)")
        attendees_csv = st.text_input("Asistentes (opcional)", placeholder="Ana, Luis, Marta")
        vocabulary = st.text_input(
            "Vocabulario del proyecto (opcional)",
            placeholder="ChromaDB, faster-whisper, MeetingForge…",
            help="Términos y nombres propios que Whisper suele transcribir mal (UX-1). "
            "Para un glosario permanente, crea data/glossary.txt.",
        )

        llm_check = check_llm_key()
        if not llm_check.ok:
            st.caption(f"⚠️ {llm_check.detail}. {llm_check.remedy}.")
        if st.button("Procesar", type="primary", disabled=source is None or not llm_check.ok):
            _process_uploaded(
                source,
                use_rag,
                use_gen,
                title,
                attendees_csv=attendees_csv,
                vocabulary=vocabulary,
                target_name=target_name,
            )


def _render_system_status() -> None:
    """Expander de prerequisitos en el sidebar (UX-18): ✅/⚠️ por check con remedio accionable."""
    with st.sidebar.expander("⚙️ Estado del sistema"):
        results = [check_llm_key(), check_ffmpeg()]
        if settings.rag_enabled:
            results.append(_cached_rag_check())
        if settings.git_integration_enabled:
            results.append(check_gh())
        for res in results:
            icon = "✅" if res.ok else "⚠️"
            st.markdown(f"{icon} **{res.name}** — {res.detail}")
            if not res.ok and res.remedy:
                st.caption(res.remedy)


# ---------------------------------------------------------------------------
# Vistas globales: Inicio (UX-10), Tareas (UX-7), Búsqueda (UX-8)
# ---------------------------------------------------------------------------


def _select_meeting(meeting_id: str) -> None:
    """Selecciona una reunión y vuelve a la vista de reunión (usado por búsqueda y recientes)."""
    st.session_state["selected_meeting_id"] = meeting_id
    st.session_state["nav"] = "Reunión"
    st.rerun()


def _render_dashboard() -> None:
    """Pantalla de inicio: tarjetas de conjunto + reuniones recientes (UX-10)."""
    from meeting_forge.dashboard import compute_stats

    st.title("Inicio")
    stats = compute_stats(_OUTPUTS_DIR)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Reuniones", stats.n_meetings)
    c2.metric("Docs por validar", stats.n_pending_docs)
    c3.metric("Tareas abiertas", stats.n_open_tasks)
    c4.metric("Tareas totales", stats.n_total_tasks)
    st.divider()

    st.subheader("Reuniones recientes")
    if not stats.recent:
        st.info("No hay reuniones procesadas todavía. Súbelas en el panel lateral.")
        return
    for summary in stats.recent:
        col_info, col_btn = st.columns([4, 1])
        col_info.markdown(
            f"**{summary.meeting_id}** — {summary.n_decisions} decisiones · "
            f"{summary.n_actions} tareas"
        )
        if col_btn.button("Abrir", key=f"open_{summary.meeting_id}"):
            _select_meeting(summary.meeting_id)


def _render_tasks() -> None:
    """Panel global de tareas pendientes de todas las reuniones (UX-7)."""
    from meeting_forge import tasks as tasks_mod

    st.title("Tareas")
    all_tasks = tasks_mod.aggregate_tasks(_OUTPUTS_DIR)
    if not all_tasks:
        st.info("No hay tareas extraídas todavía.")
        return

    assignees = tasks_mod.distinct_assignees(all_tasks)
    col_f, col_h = st.columns([3, 1])
    selected_assignee = col_f.selectbox("Asignado", ["(todos)", *assignees])
    hide_done = col_h.checkbox("Ocultar hechas", value=True)

    shown = all_tasks
    if selected_assignee != "(todos)":
        shown = tasks_mod.filter_by_assignee(shown, selected_assignee)
    if hide_done:
        shown = [t for t in shown if not t.done]

    n_open = sum(1 for t in all_tasks if not t.done)
    st.caption(f"{n_open} abiertas de {len(all_tasks)} totales")
    st.download_button(
        "Descargar CSV",
        data=tasks_mod.tasks_to_csv(all_tasks),
        file_name="tareas.csv",
        mime="text/csv",
    )
    st.divider()

    for task in shown:
        col_chk, col_desc, col_meta = st.columns([1, 5, 3])
        done = col_chk.checkbox(
            "Hecha", value=task.done, key=f"task_{task.key}", label_visibility="collapsed"
        )
        if done != task.done:
            tasks_mod.set_task_done(_OUTPUTS_DIR, task.key, done)
            st.rerun()
        text = f"~~{task.description}~~" if task.done else task.description
        col_desc.markdown(text)
        meta_bits = []
        if task.assignee:
            meta_bits.append(f"@{task.assignee}")
        if task.deadline:
            meta_bits.append(f"📅 {task.deadline}")
        meta_bits.append(f"_{task.meeting_id}_")
        col_meta.caption(" · ".join(meta_bits))


def _render_search_box() -> None:
    """Caja de búsqueda semántica entre reuniones en el sidebar (UX-8)."""
    with st.sidebar.expander("🔎 Buscar en reuniones"):
        query = st.text_input("Consulta", key="search_query", label_visibility="collapsed")
        if not query.strip():
            return
        from meeting_forge import search as search_mod

        hits: list[tuple[str, str]] = []  # (meeting_id, snippet)
        try:
            for hit in search_mod.search_meetings(query, top_k=5):
                hits.append((hit.meeting_id, hit.snippet))
        except Exception:
            # Sin embeddings/Chroma disponibles: fallback por subcadena.
            for meeting_id in search_mod.substring_search(_OUTPUTS_DIR, query):
                hits.append((meeting_id, ""))

        if not hits:
            st.caption("Sin resultados.")
            return
        for meeting_id, snippet in hits:
            if st.button(meeting_id, key=f"search_hit_{meeting_id}"):
                _select_meeting(meeting_id)
            if snippet:
                st.caption(snippet)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------


def main() -> None:
    configure_logging()
    st.set_page_config(page_title="MeetingForge", layout="wide")

    st.sidebar.title("MeetingForge")
    st.sidebar.caption("Procesa y revisa reuniones")
    _render_run_panel()
    _render_search_box()
    _render_system_status()

    nav = st.sidebar.radio("Vista", ["Inicio", "Reunión", "Tareas"], key="nav")
    st.sidebar.divider()

    if nav == "Inicio":
        _render_dashboard()
        return
    if nav == "Tareas":
        _render_tasks()
        return

    meetings = list_meetings(_OUTPUTS_DIR)

    if not meetings:
        st.info(
            "No hay reuniones procesadas todavía. "
            "Sube un audio en la barra lateral (**➕ Procesar nueva reunión**) para empezar, "
            "o usa el CLI: `uv run python scripts/run_e2e.py data/raw/<audio.wav>`."
        )
        return

    selected = _render_sidebar(meetings)
    data = _cached_load_meeting(str(selected.meeting_dir))
    docs = _cached_load_docs(str(selected.meeting_dir))

    _render_sidebar_metadata(data.metadata)

    st.title(f"Reunión: {selected.meeting_id}")

    tab_resumen, tab_transcript, tab_insights, tab_evidencia, tab_chat, tab_docs, tab_val = st.tabs(
        [
            "Resumen",
            "Transcript",
            "Insights",
            "Evidencia",
            "Preguntar",
            "Documentos",
            "Validación",
        ]
    )

    with tab_resumen:
        _render_resumen(data)

    with tab_transcript:
        _render_transcript(data, selected.meeting_dir)

    with tab_insights:
        _render_insights(data, selected.meeting_dir)

    with tab_evidencia:
        _render_evidencia(data)

    with tab_chat:
        _render_chat(data, selected.meeting_dir)

    with tab_docs:
        _render_documentos(docs)

    with tab_val:
        _render_validacion(data, docs, selected.meeting_dir)


if __name__ == "__main__":
    main()
