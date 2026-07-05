"""Servicio de orquestación del pipeline E2E, reutilizable por el CLI y la UI (F4).

Antes esta lógica vivía en `scripts/run_e2e.py`; extraerla aquí permite que tanto el CLI como la
interfaz Streamlit ejecuten el mismo pipeline (audio → transcripción → RAG → insights → documentos)
sin duplicar código, con un callback opcional de progreso por fase.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from loguru import logger

from . import meeting_store
from .analysis.extractor import InsightsExtractor
from .analysis.llm_client import LLMProvider, get_provider
from .analysis.schemas import MeetingInsights
from .config import configure_logging, ensure_data_dirs, settings
from .generation import (
    DocumentGenerator,
    DocumentKind,
    GeneratedDocument,
    GenerationMode,
    MeetingMetadata,
)
from .ingestion.transcriber import WhisperTranscriber
from .observability import TelemetryCollector
from .rag.embeddings import SentenceTransformerEmbeddings
from .rag.retriever import Retriever
from .rag.vector_store import ChromaVectorStore
from .validation import store as validation_store

# Callback de progreso: recibe un mensaje legible por fase (la UI lo muestra; el CLI usa el log).
ProgressCallback = Callable[[str], None]


@dataclass
class PipelineResult:
    """Resumen del resultado de una ejecución del pipeline."""

    meeting_id: str
    out_dir: Path
    result_path: Path
    n_decisions: int
    n_actions: int
    n_documents: int
    run_id: str


def parse_modes(modes_str: str) -> list[GenerationMode]:
    """Parsea un CSV de modos a lista de GenerationMode. Ignora los inválidos con warning."""
    valid = {m.value: m for m in GenerationMode}
    result: list[GenerationMode] = []
    for raw_token in modes_str.split(","):
        token = raw_token.strip()
        if not token:
            continue
        if token in valid:
            result.append(valid[token])
        else:
            logger.warning("Modo de generación desconocido ignorado: '{}'", token)
    return result


def audio_date(audio_path: Path) -> str:
    """Devuelve la fecha de modificación del audio como ISO YYYY-MM-DD."""
    try:
        mtime = audio_path.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except OSError:
        return datetime.now().strftime("%Y-%m-%d")


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_meeting_date(meeting_date: str, audio_path: Path) -> str:
    """Valida que la fecha sea ISO `YYYY-MM-DD`; si no, cae a la fecha del audio con warning.

    La fecha acaba en el nombre del acta y en la rama git de publicación: una fecha libre con
    espacios o `:` produciría un ref inválido y un nombre de fichero ilegal en Windows.
    """
    value = meeting_date.strip()
    if not value:
        return audio_date(audio_path)
    if _ISO_DATE_RE.match(value):
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            pass
    logger.warning(
        "Fecha de reunión inválida '{d}' (se espera YYYY-MM-DD); se usa la fecha del audio",
        d=value,
    )
    return audio_date(audio_path)


def parse_attendees(raw: str) -> list[str]:
    """Parsea el CSV de asistentes ("Ana, Luis") a lista limpia (UX-4)."""
    return [item.strip() for item in raw.split(",") if item.strip()]


def _build_retriever() -> Retriever | None:
    """Intenta construir un Retriever. Devuelve None si el índice está vacío o falla."""
    try:
        store = ChromaVectorStore()
        if store.count() == 0:
            logger.warning(
                "Vector store vacío. Ejecuta `scripts/index_docs.py` primero o desactiva RAG."
            )
            return None
        embeddings = SentenceTransformerEmbeddings()
        return Retriever(store=store, embeddings=embeddings)
    except Exception as exc:  # pragma: no cover - defensivo
        logger.warning("No se pudo inicializar el retriever: {e}", e=exc)
        return None


def _load_existing_docs() -> dict[DocumentKind, str]:
    """Lee los documentos existentes a actualizar (roadmap / doc técnica), si están configurados."""
    existing: dict[DocumentKind, str] = {}
    if settings.roadmap_path and settings.roadmap_path.exists():
        existing[DocumentKind.ROADMAP] = settings.roadmap_path.read_text(encoding="utf-8")
    if settings.tech_doc_path and settings.tech_doc_path.exists():
        existing[DocumentKind.TECHNICAL_DOC] = settings.tech_doc_path.read_text(encoding="utf-8")
    return existing


def _notify(progress: ProgressCallback | None, message: str) -> None:
    logger.info(message)
    if progress is not None:
        progress(message)


def _resolve_modes(modes: list[GenerationMode] | None) -> list[GenerationMode]:
    """Modos explícitos, o los de settings si no se pasan."""
    return modes if modes is not None else parse_modes(",".join(settings.generation_modes))


# Qué kind produce cada modo (para limpiar solo los subdirs que se regeneran).
_KIND_BY_MODE: dict[GenerationMode, DocumentKind] = {
    GenerationMode.ADR_PER_DECISION: DocumentKind.ADR,
    GenerationMode.ADR_CONSOLIDATED: DocumentKind.ADR,
    GenerationMode.ACTA: DocumentKind.ACTA,
    GenerationMode.ROADMAP_UPDATE: DocumentKind.ROADMAP,
    GenerationMode.TECHNICAL_DOC_UPDATE: DocumentKind.TECHNICAL_DOC,
}


def _clear_generated_dirs(out_dir: Path, active_modes: list[GenerationMode]) -> None:
    """Borra los subdirs de los kinds a (re)escribir, para no dejar documentos huérfanos.

    Sin esto, regenerar tras editar insights (menos decisiones, otra fecha…) dejaría ADRs o
    actas antiguos conviviendo con los nuevos.
    """
    for kind in {_KIND_BY_MODE[m] for m in active_modes}:
        shutil.rmtree(out_dir / kind.value, ignore_errors=True)


def _generate_docs(
    insights: MeetingInsights,
    metadata: MeetingMetadata,
    provider: LLMProvider,
    collector: TelemetryCollector,
    active_modes: list[GenerationMode],
) -> list[GeneratedDocument]:
    """Genera los documentos en memoria (sin escribir aún) midiendo la fase."""
    existing_docs = _load_existing_docs()
    with collector.phase("generation"):
        gen = DocumentGenerator(
            provider=provider,
            adr_prompt_version=settings.adr_prompt_version,
        )
        return gen.generate(
            insights, metadata, modes=active_modes, existing_docs=existing_docs or None
        )


def _write_docs(docs: list[GeneratedDocument], out_dir: Path) -> list[dict[str, object]]:
    """Escribe los documentos en `out_dir/<kind>/` y devuelve el resumen para result.json."""
    generated_summary: list[dict[str, object]] = []
    for doc in docs:
        saved_path = doc.write_to(out_dir / doc.kind.value)
        logger.info("Documento generado [{k}]: {p}", k=doc.kind.value, p=saved_path)
        generated_summary.append(
            {
                "filename": doc.filename,
                "kind": doc.kind.value,
                "mode": doc.mode.value,
                "sources_count": len(doc.sources_used),
            }
        )
    return generated_summary


def _index_for_search(meeting_id: str, result: dict[str, object]) -> None:
    """Indexa la reunión en la colección de búsqueda (UX-8). Best-effort: nunca rompe el run."""
    if not settings.search_index_enabled:
        return
    try:
        from .search import index_meeting

        index_meeting(meeting_id, result)
    except Exception as exc:  # pragma: no cover - defensivo (depende de Chroma/embeddings)
        logger.warning("No se pudo indexar la reunión para búsqueda: {e}", e=exc)


def _load_metadata(result: dict[str, object], meeting_dir: Path) -> MeetingMetadata:
    """Reconstruye la metadata persistida en result.json (con fallback mínimo)."""
    meta_raw = result.get("meeting_metadata")
    if isinstance(meta_raw, dict):
        return MeetingMetadata.model_validate(meta_raw)
    return MeetingMetadata(
        meeting_id=meeting_dir.name, title=meeting_dir.name, date=None, source_audio=None
    )


def run_pipeline(
    audio_path: Path,
    *,
    output_dir: Path | None = None,
    use_rag: bool = True,
    use_generation: bool = True,
    modes: list[GenerationMode] | None = None,
    meeting_title: str = "",
    meeting_date: str = "",
    attendees: list[str] | None = None,
    vocabulary: str = "",
    progress: ProgressCallback | None = None,
) -> PipelineResult:
    """Ejecuta el pipeline E2E y persiste `result.json`. Devuelve un `PipelineResult`.

    `modes=None` usa `settings.generation_modes`. `progress` recibe un mensaje por fase.
    `attendees` se refleja en el acta (UX-4); `vocabulary` guía a Whisper en este run (UX-1).
    """
    configure_logging()
    ensure_data_dirs()
    if not audio_path.exists():
        raise FileNotFoundError(f"Archivo de audio no encontrado: {audio_path}")

    base_dir = output_dir or (settings.data_dir / "outputs")
    meeting_id = audio_path.stem
    out_dir = base_dir / meeting_id
    out_dir.mkdir(parents=True, exist_ok=True)

    collector = TelemetryCollector(
        config={
            "provider": settings.llm_provider,
            "whisper_model": settings.whisper_model_size,
            "embedding_model": settings.embedding_model,
            "adr_prompt_version": settings.adr_prompt_version,
        }
    )
    logger.info("Run ID: {r}", r=collector.run_id)

    metadata = MeetingMetadata(
        meeting_id=meeting_id,
        title=meeting_title.strip() or meeting_id,
        date=normalize_meeting_date(meeting_date, audio_path),
        attendees=attendees or [],
        source_audio=str(audio_path),
    )

    provider = get_provider(collector=collector)

    # [1/4] Transcripción
    _notify(progress, "Transcribiendo audio con Whisper…")
    with collector.phase("transcription"):
        transcriber = WhisperTranscriber()
        transcript = transcriber.transcribe(audio_path, vocabulary=vocabulary)
    transcript_path = out_dir / f"{meeting_id}_transcript.json"
    transcript_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")

    # [2/4] Retriever (opcional)
    retriever: Retriever | None = None
    if use_rag and settings.rag_enabled:
        _notify(progress, "Construyendo retriever (RAG)…")
        with collector.phase("retrieval_setup"):
            retriever = _build_retriever()
    else:
        _notify(progress, "RAG desactivado")

    metadata_block: dict[str, object] = {
        "provider": settings.llm_provider,
        "whisper_model": settings.whisper_model_size,
        "rag_enabled": retriever is not None,
        "embedding_model": settings.embedding_model if retriever else None,
    }
    output_path = out_dir / f"{meeting_id}_result.json"

    # [3/4] Extracción de insights
    _notify(progress, "Extrayendo insights con el LLM…")
    extractor = InsightsExtractor(provider=provider, retriever=retriever)
    try:
        with collector.phase("extraction"):
            insights = extractor.extract(transcript)
    except Exception as exc:
        # BUG-2: una extracción fallida (error del LLM tras reintentos o JSON inválido) no debe
        # tirar el trabajo ya hecho. Persistimos un result.json parcial (transcript + evidencia +
        # telemetría + el error) antes de propagar, para no dejar la transcripción huérfana.
        logger.error("Fase de extracción fallida: {e}. Se guarda un resultado parcial.", e=exc)
        partial: dict[str, object] = {
            "audio_file": str(audio_path),
            "transcript": transcript.model_dump(),
            "insights": MeetingInsights().model_dump(),
            "metadata": metadata_block,
            "meeting_metadata": metadata.model_dump(mode="json"),
            "retrieved_evidence": [r.model_dump(mode="json") for r in extractor.last_context],
            "generated_documents": [],
            "error": {"phase": "extraction", "message": str(exc)},
            "run_meta": collector.build().model_dump(mode="json"),
        }
        output_path.write_text(json.dumps(partial, indent=2, ensure_ascii=False), encoding="utf-8")
        raise

    result: dict[str, object] = {
        "audio_file": str(audio_path),
        "transcript": transcript.model_dump(),
        "insights": insights.model_dump(),
        "metadata": metadata_block,
        "meeting_metadata": metadata.model_dump(mode="json"),
        "retrieved_evidence": [r.model_dump(mode="json") for r in extractor.last_context],
        "generated_documents": [],
    }

    # [4/4] Generación de documentos
    n_documents = 0
    if use_generation and settings.generation_enabled:
        active_modes = _resolve_modes(modes)
        if not active_modes:
            logger.warning("No hay modos de generación válidos — se salta la generación")
        else:
            _notify(progress, "Generando documentos…")
            try:
                docs = _generate_docs(insights, metadata, provider, collector, active_modes)
                # Limpia los kinds a escribir DESPUÉS de generar con éxito: si se reprocesa la
                # misma reunión, los documentos del run anterior no deben quedar huérfanos.
                _clear_generated_dirs(out_dir, active_modes)
                result["generated_documents"] = _write_docs(docs, out_dir)
                n_documents = len(docs)

                # F8: modo automático opcional (auto-aprobar / auto-publicar) sobre lo generado.
                if settings.auto_approve_enabled:
                    try:
                        from .automation import run_auto_mode

                        _notify(progress, "Modo automático: auto-aprobando…")
                        auto = run_auto_mode(out_dir, docs, metadata)
                        if auto.auto_approved:
                            logger.info(
                                "Modo automático: {n} doc(s) auto-aprobados",
                                n=len(auto.auto_approved),
                            )
                    except Exception as exc:
                        logger.error("Modo automático falló: {e}", e=exc)
            except Exception as exc:
                logger.error(
                    "Error en la fase de generación: {e}. El resultado JSON se guarda igualmente.",
                    e=exc,
                )

    telemetry = collector.build()
    result["run_meta"] = telemetry.model_dump(mode="json")
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    _index_for_search(meeting_id, result)
    _notify(progress, "Pipeline completado")
    logger.info(
        "Telemetría: {calls} llamada(s) LLM · {tin}+{tout} tokens · {lat:.1f}s LLM · ~${cost:.4f}",
        calls=len(telemetry.llm_calls),
        tin=telemetry.total_input_tokens,
        tout=telemetry.total_output_tokens,
        lat=telemetry.total_llm_latency_s,
        cost=telemetry.total_cost_usd,
    )

    return PipelineResult(
        meeting_id=meeting_id,
        out_dir=out_dir,
        result_path=output_path,
        n_decisions=len(insights.decisions),
        n_actions=len(insights.action_items),
        n_documents=n_documents,
        run_id=collector.run_id,
    )


def regenerate_documents(
    meeting_dir: Path,
    *,
    modes: list[GenerationMode] | None = None,
    progress: ProgressCallback | None = None,
) -> PipelineResult:
    """Regenera SOLO los documentos de una reunión ya procesada (UX-5 · base PROD-9).

    Usa los insights y la metadata persistidos en result.json: ni re-transcribe ni re-extrae.
    Limpia los subdirs de los kinds regenerados (sin documentos huérfanos), invalida la
    validación previa (B-N2) y NO aplica el modo automático (F8): regenerar es un flujo de
    revisión humana. El `run_meta` original se conserva (refleja el run completo).
    """
    configure_logging()
    result = meeting_store.load_result(meeting_dir)
    insights = MeetingInsights.model_validate(result.get("insights", {}))
    metadata = _load_metadata(result, meeting_dir)
    active_modes = _resolve_modes(modes)
    if not active_modes:
        raise ValueError("No hay modos de generación válidos para regenerar")

    collector = TelemetryCollector(
        config={"provider": settings.llm_provider, "kind": "regeneration"}
    )
    provider = get_provider(collector=collector)

    _notify(progress, "Regenerando documentos…")
    docs = _generate_docs(insights, metadata, provider, collector, active_modes)
    _clear_generated_dirs(meeting_dir, active_modes)
    result["generated_documents"] = _write_docs(docs, meeting_dir)
    meeting_store.save_result(meeting_dir, result)

    # B-N2: los documentos cambiaron → la validación previa deja de ser válida.
    validation_store.clear_state(meeting_dir)

    _notify(progress, "Documentos regenerados")
    return PipelineResult(
        meeting_id=meeting_dir.name,
        out_dir=meeting_dir,
        result_path=meeting_store.find_result_path(meeting_dir),
        n_decisions=len(insights.decisions),
        n_actions=len(insights.action_items),
        n_documents=len(docs),
        run_id=collector.run_id,
    )


def rerun_extraction(
    meeting_dir: Path,
    *,
    use_rag: bool = True,
    use_generation: bool = True,
    modes: list[GenerationMode] | None = None,
    progress: ProgressCallback | None = None,
) -> PipelineResult:
    """Re-ejecuta extracción (+ generación) sobre el transcript persistido (UX-2).

    No re-transcribe: parte del transcript canónico (posiblemente corregido en la UI) y le
    aplica los nombres de speaker guardados (UX-3) antes de llamar al LLM. Sustituye insights
    y evidencia en result.json, regenera los documentos e invalida la validación previa.
    """
    configure_logging()
    result = meeting_store.load_result(meeting_dir)
    transcript = meeting_store.load_transcript(meeting_dir)
    names = meeting_store.load_speaker_names(meeting_dir)
    if names:
        renamed = transcript.rename_speakers(names)
        logger.info("Nombres de speaker aplicados a {n} segmentos", n=renamed)
    metadata = _load_metadata(result, meeting_dir)

    collector = TelemetryCollector(
        config={"provider": settings.llm_provider, "kind": "re-extraction"}
    )
    provider = get_provider(collector=collector)

    retriever: Retriever | None = None
    if use_rag and settings.rag_enabled:
        _notify(progress, "Construyendo retriever (RAG)…")
        with collector.phase("retrieval_setup"):
            retriever = _build_retriever()

    _notify(progress, "Re-extrayendo insights con el LLM…")
    extractor = InsightsExtractor(provider=provider, retriever=retriever)
    with collector.phase("extraction"):
        insights = extractor.extract(transcript)

    result["insights"] = insights.model_dump()
    # La re-extracción sustituye cualquier edición manual previa de insights.
    result["insights_edited"] = False
    result["retrieved_evidence"] = [r.model_dump(mode="json") for r in extractor.last_context]

    n_documents = 0
    if use_generation and settings.generation_enabled:
        active_modes = _resolve_modes(modes)
        if active_modes:
            _notify(progress, "Regenerando documentos…")
            # Igual que en run_pipeline: un fallo de generación no debe perder los insights
            # nuevos, que se persisten igualmente.
            try:
                docs = _generate_docs(insights, metadata, provider, collector, active_modes)
                _clear_generated_dirs(meeting_dir, active_modes)
                result["generated_documents"] = _write_docs(docs, meeting_dir)
                n_documents = len(docs)
            except Exception as exc:
                logger.error(
                    "Error regenerando documentos tras la re-extracción: {e}. "
                    "Los insights nuevos se guardan igualmente.",
                    e=exc,
                )

    meeting_store.save_result(meeting_dir, result)
    validation_store.clear_state(meeting_dir)
    _index_for_search(meeting_dir.name, result)

    _notify(progress, "Re-extracción completada")
    return PipelineResult(
        meeting_id=meeting_dir.name,
        out_dir=meeting_dir,
        result_path=meeting_store.find_result_path(meeting_dir),
        n_decisions=len(insights.decisions),
        n_actions=len(insights.action_items),
        n_documents=n_documents,
        run_id=collector.run_id,
    )
