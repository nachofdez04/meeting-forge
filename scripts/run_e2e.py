#!/usr/bin/env python3
"""Pipeline end-to-end: audio → transcripción → insights → documentos generados."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import typer
from loguru import logger

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from meeting_forge.analysis.extractor import InsightsExtractor  # noqa: E402
from meeting_forge.config import settings  # noqa: E402
from meeting_forge.generation import (  # noqa: E402
    DocumentGenerator,
    GenerationMode,
    MeetingMetadata,
)
from meeting_forge.ingestion.transcriber import WhisperTranscriber  # noqa: E402
from meeting_forge.rag.embeddings import SentenceTransformerEmbeddings  # noqa: E402
from meeting_forge.rag.retriever import Retriever  # noqa: E402
from meeting_forge.rag.vector_store import ChromaVectorStore  # noqa: E402

app = typer.Typer(add_completion=False, help="MeetingForge E2E pipeline")


def _build_retriever() -> Retriever | None:
    """Intenta construir un Retriever. Devuelve None si el índice está vacío o falla."""
    try:
        store = ChromaVectorStore()
        if store.count() == 0:
            logger.warning(
                "Vector store vacío. Ejecuta `scripts/index_docs.py` primero o "
                "usa --no-rag para saltarte el contexto."
            )
            return None
        embeddings = SentenceTransformerEmbeddings()
        return Retriever(store=store, embeddings=embeddings)
    except Exception as exc:  # pragma: no cover - defensivo
        logger.warning("No se pudo inicializar el retriever: {e}", e=exc)
        return None


def _parse_modes(modes_str: str) -> list[GenerationMode]:
    """Parsea CSV de modos a lista de GenerationMode. Ignora los inválidos con warning."""
    valid = {m.value: m for m in GenerationMode}
    result: list[GenerationMode] = []
    for token in modes_str.split(","):
        token = token.strip()
        if not token:
            continue
        if token in valid:
            result.append(valid[token])
        else:
            logger.warning("Modo de generación desconocido ignorado: '{}'", token)
    return result


def _audio_date(audio_path: Path) -> str:
    """Devuelve la fecha de modificación del audio como ISO YYYY-MM-DD."""
    try:
        mtime = audio_path.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except OSError:
        return datetime.now().strftime("%Y-%m-%d")


@app.command()
def main(
    audio_path: Path = typer.Argument(..., help="Path al archivo de audio"),
    output_dir: Path = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Directorio base donde escribir los outputs (default: data/outputs)",
    ),
    no_rag: bool = typer.Option(
        False,
        "--no-rag",
        help="Desactiva RAG aunque settings.rag_enabled sea True",
    ),
    no_generation: bool = typer.Option(
        False,
        "--no-generation",
        help="Salta la Fase 2 (generación de ADRs/actas)",
    ),
    generate_modes: str = typer.Option(
        "",
        "--generate-modes",
        help=(
            "Modos de generación separados por coma: "
            "adr-per-decision, adr-consolidated, acta. "
            "Default: usa GENERATION_MODES del settings."
        ),
    ),
    meeting_title: str = typer.Option(
        "",
        "--meeting-title",
        help="Título de la reunión para los documentos generados",
    ),
    meeting_date: str = typer.Option(
        "",
        "--meeting-date",
        help="Fecha ISO YYYY-MM-DD (default: mtime del audio)",
    ),
) -> None:
    """Ejecuta el pipeline E2E: transcripción + extracción + generación de documentos."""
    logger.info("=" * 80)
    logger.info("MeetingForge - E2E Pipeline")
    logger.info("=" * 80)

    if not audio_path.exists():
        logger.error("Archivo no encontrado: {p}", p=audio_path)
        raise typer.Exit(code=1)

    base_dir = output_dir or (settings.data_dir / "outputs")
    meeting_id = audio_path.stem
    out_dir = base_dir / meeting_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # [1/4] Transcripción
    # ------------------------------------------------------------------
    logger.info("[1/4] Transcripción con Whisper")
    transcriber = WhisperTranscriber()
    transcript = transcriber.transcribe(audio_path)

    transcript_path = out_dir / f"{meeting_id}_transcript.json"
    transcript_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Transcripción guardada en: {p}", p=transcript_path)

    # ------------------------------------------------------------------
    # [2/4] Retriever (opcional)
    # ------------------------------------------------------------------
    retriever: Retriever | None = None
    use_rag = settings.rag_enabled and not no_rag
    if use_rag:
        logger.info("[2/4] Construyendo retriever (RAG activado)")
        retriever = _build_retriever()
    else:
        logger.info("[2/4] RAG desactivado")

    # ------------------------------------------------------------------
    # [3/4] Extracción de insights
    # ------------------------------------------------------------------
    logger.info("[3/4] Extracción de insights con LLM")
    extractor = InsightsExtractor(retriever=retriever)
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
        "generated_documents": [],
    }

    output_path = out_dir / f"{meeting_id}_result.json"

    # ------------------------------------------------------------------
    # [4/4] Generación de documentos
    # ------------------------------------------------------------------
    use_generation = settings.generation_enabled and not no_generation
    if use_generation:
        logger.info("[4/4] Generación de documentos (Fase 2)")

        # Modos: flag CLI > settings
        modes_str = generate_modes.strip() or ",".join(settings.generation_modes)
        modes = _parse_modes(modes_str)

        if not modes:
            logger.warning("No hay modos de generación válidos — se salta el paso [4/4]")
        else:
            # Metadatos de la reunión
            date = meeting_date.strip() or _audio_date(audio_path)
            metadata = MeetingMetadata(
                meeting_id=meeting_id,
                title=meeting_title.strip() or meeting_id,
                date=date,
                source_audio=str(audio_path),
            )

            try:
                gen = DocumentGenerator(
                    provider=extractor.provider,
                    adr_prompt_version=settings.adr_prompt_version,
                )
                docs = gen.generate(insights, metadata, modes=modes)

                generated_summary = []
                for doc in docs:
                    target_dir = out_dir / doc.kind.value
                    saved_path = doc.write_to(target_dir)
                    logger.info(
                        "Documento generado [{kind}]: {p}",
                        kind=doc.kind.value,
                        p=saved_path,
                    )
                    generated_summary.append(
                        {
                            "filename": doc.filename,
                            "kind": doc.kind.value,
                            "mode": doc.mode.value,
                            "sources_count": len(doc.sources_used),
                        }
                    )
                result["generated_documents"] = generated_summary

            except Exception as exc:
                logger.error(
                    "Error en la fase de generación: {e}. "
                    "El resultado JSON se guarda de todas formas.",
                    e=exc,
                )
    else:
        logger.info("[4/4] Generación desactivada (--no-generation o GENERATION_ENABLED=false)")

    # ------------------------------------------------------------------
    # Guardar resultado JSON
    # ------------------------------------------------------------------
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("Pipeline completado")
    logger.info("Resultado guardado en: {p}", p=output_path)
    logger.info("Decisiones encontradas: {n}", n=len(insights.decisions))
    logger.info("Tareas identificadas: {n}", n=len(insights.action_items))
    if insights.summary:
        logger.info("Resumen: {s}", s=insights.summary)


if __name__ == "__main__":
    app()
