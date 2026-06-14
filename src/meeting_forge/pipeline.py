"""Servicio de orquestación del pipeline E2E, reutilizable por el CLI y la UI (F4).

Antes esta lógica vivía en `scripts/run_e2e.py`; extraerla aquí permite que tanto el CLI como la
interfaz Streamlit ejecuten el mismo pipeline (audio → transcripción → RAG → insights → documentos)
sin duplicar código, con un callback opcional de progreso por fase.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from loguru import logger

from .analysis.extractor import InsightsExtractor
from .analysis.llm_client import get_provider
from .config import ensure_data_dirs, settings
from .generation import DocumentGenerator, DocumentKind, GenerationMode, MeetingMetadata
from .ingestion.transcriber import WhisperTranscriber
from .observability import TelemetryCollector
from .rag.embeddings import SentenceTransformerEmbeddings
from .rag.retriever import Retriever
from .rag.vector_store import ChromaVectorStore

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


def run_pipeline(
    audio_path: Path,
    *,
    output_dir: Path | None = None,
    use_rag: bool = True,
    use_generation: bool = True,
    modes: list[GenerationMode] | None = None,
    meeting_title: str = "",
    meeting_date: str = "",
    progress: ProgressCallback | None = None,
) -> PipelineResult:
    """Ejecuta el pipeline E2E y persiste `result.json`. Devuelve un `PipelineResult`.

    `modes=None` usa `settings.generation_modes`. `progress` recibe un mensaje por fase.
    """
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
        date=meeting_date.strip() or audio_date(audio_path),
        source_audio=str(audio_path),
    )

    provider = get_provider(collector=collector)

    # [1/4] Transcripción
    _notify(progress, "Transcribiendo audio con Whisper…")
    with collector.phase("transcription"):
        transcriber = WhisperTranscriber()
        transcript = transcriber.transcribe(audio_path)
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

    # [3/4] Extracción de insights
    _notify(progress, "Extrayendo insights con el LLM…")
    extractor = InsightsExtractor(provider=provider, retriever=retriever)
    with collector.phase("extraction"):
        insights = extractor.extract(transcript)

    result: dict[str, object] = {
        "audio_file": str(audio_path),
        "transcript": transcript.model_dump(),
        "insights": insights.model_dump(),
        "metadata": {
            "provider": settings.llm_provider,
            "whisper_model": settings.whisper_model_size,
            "rag_enabled": retriever is not None,
            "embedding_model": settings.embedding_model if retriever else None,
        },
        "meeting_metadata": metadata.model_dump(mode="json"),
        "retrieved_evidence": [r.model_dump(mode="json") for r in extractor.last_context],
        "generated_documents": [],
    }

    output_path = out_dir / f"{meeting_id}_result.json"

    # [4/4] Generación de documentos
    n_documents = 0
    if use_generation and settings.generation_enabled:
        active_modes = (
            modes if modes is not None else parse_modes(",".join(settings.generation_modes))
        )
        if not active_modes:
            logger.warning("No hay modos de generación válidos — se salta la generación")
        else:
            _notify(progress, "Generando documentos…")
            existing_docs = _load_existing_docs()
            try:
                with collector.phase("generation"):
                    gen = DocumentGenerator(
                        provider=provider,
                        adr_prompt_version=settings.adr_prompt_version,
                    )
                    docs = gen.generate(
                        insights, metadata, modes=active_modes, existing_docs=existing_docs or None
                    )

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
                result["generated_documents"] = generated_summary
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
