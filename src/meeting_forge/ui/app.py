"""Interfaz Streamlit de MeetingForge — visor de reuniones procesadas."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, cast

import streamlit as st

from meeting_forge.config import settings
from meeting_forge.generation.diffing import unified_md_diff
from meeting_forge.generation.schemas import MeetingMetadata
from meeting_forge.git_integration import pr as pr_module
from meeting_forge.git_integration import publisher as pub_module
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


def _render_transcript(data: MeetingData) -> None:
    """Tab Transcript: tabla de segmentos con timestamps."""
    segments = data.transcript_segments
    if not segments:
        st.info("No hay segmentos de transcripción disponibles.")
        return

    rows = [
        {
            "Inicio (s)": seg.get("start", ""),
            "Fin (s)": seg.get("end", ""),
            "Texto": str(seg.get("text", "")),
            "Speaker": str(seg.get("speaker") or ""),
        }
        for seg in segments
    ]
    st.dataframe(rows, use_container_width=True)


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


def _render_insights(data: MeetingData) -> None:
    """Tab Insights: decisiones y tareas con sus fuentes."""
    if data.insights.decisions:
        st.subheader("Decisiones")
        for dec in data.insights.decisions:
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
    else:
        st.info("No se identificaron decisiones.")

    if data.insights.action_items:
        st.subheader("Tareas")
        for action in data.insights.action_items:
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
    else:
        st.info("No se identificaron tareas.")


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
                key=f"dl_{doc.filename}",
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
                    key=f"edit_{doc.filename}",
                    label_visibility="collapsed",
                )
                if edited_text.strip() != doc.markdown_content.strip():
                    with st.expander("Diferencias vs original generado"):
                        st.code(
                            unified_md_diff(doc.markdown_content, edited_text, doc.filename),
                            language="diff",
                        )
                if st.button("Guardar edición y aprobar", key=f"save_{doc.filename}"):
                    state = val_store.mark_approved(state, doc.filename, edited_content=edited_text)
                    val_store.save_state(meeting_dir, state)
                    st.session_state[state_key] = state
                    st.rerun()

            btn_col, reason_col, reset_col = st.columns([1, 2, 1])
            with btn_col:
                if st.button("Aprobar", key=f"approve_{doc.filename}", type="primary"):
                    # F11: si el usuario tiene una edición en curso, se aprueba CON ella (antes se
                    # perdía silenciosamente al pulsar Aprobar en vez de "Guardar edición").
                    current_edit = st.session_state.get(
                        f"edit_{doc.filename}", doc.markdown_content
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
                    key=f"reason_{doc.filename}",
                    placeholder="Motivo de rechazo (opcional)",
                    label_visibility="collapsed",
                )
                if st.button("Rechazar", key=f"reject_{doc.filename}"):
                    state = val_store.mark_rejected(state, doc.filename, reason=reason)
                    val_store.save_state(meeting_dir, state)
                    st.session_state[state_key] = state
                    st.rerun()
            with reset_col:
                if st.button("Reset", key=f"reset_{doc.filename}"):
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
            except pub_module.PublishError as exc:
                st.error(f"Error al publicar: {exc}")


# ---------------------------------------------------------------------------
# Procesar nueva reunión (F4)
# ---------------------------------------------------------------------------


def _process_uploaded(uploaded: Any, use_rag: bool, use_gen: bool, title: str) -> None:
    """Guarda el audio subido y ejecuta el pipeline con progreso por fase."""
    from meeting_forge.pipeline import run_pipeline  # import perezoso (dependencias pesadas)

    raw_dir = settings.data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    audio_path = raw_dir / uploaded.name
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

    st.cache_data.clear()
    st.session_state["selected_meeting_id"] = result.meeting_id
    st.rerun()


def _render_run_panel() -> None:
    """Panel en el sidebar para subir un audio y ejecutar el pipeline desde la UI."""
    with st.sidebar.expander("➕ Procesar nueva reunión"):
        uploaded = st.file_uploader(
            "Audio de la reunión",
            type=["wav", "mp3", "m4a", "flac", "ogg"],
        )
        use_rag = st.checkbox("Usar RAG", value=settings.rag_enabled)
        use_gen = st.checkbox("Generar documentos", value=settings.generation_enabled)
        title = st.text_input("Título (opcional)")
        if st.button("Procesar", type="primary", disabled=uploaded is None):
            _process_uploaded(uploaded, use_rag, use_gen, title)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="MeetingForge", layout="wide")

    st.sidebar.title("MeetingForge")
    st.sidebar.caption("Procesa y revisa reuniones")
    _render_run_panel()

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

    tab_resumen, tab_transcript, tab_insights, tab_evidencia, tab_docs, tab_val = st.tabs(
        ["Resumen", "Transcript", "Insights", "Evidencia", "Documentos", "Validación"]
    )

    with tab_resumen:
        _render_resumen(data)

    with tab_transcript:
        _render_transcript(data)

    with tab_insights:
        _render_insights(data)

    with tab_evidencia:
        _render_evidencia(data)

    with tab_docs:
        _render_documentos(docs)

    with tab_val:
        _render_validacion(data, docs, selected.meeting_dir)


if __name__ == "__main__":
    main()
