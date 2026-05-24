#!/usr/bin/env python3
"""Walking skeleton: pipeline end-to-end audio → JSON estructurado (con RAG opcional)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from loguru import logger

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from meeting_forge.analysis.extractor import InsightsExtractor  # noqa: E402
from meeting_forge.config import settings  # noqa: E402
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


@app.command()
def main(
    audio_path: Path = typer.Argument(..., help="Path al archivo de audio"),
    output_dir: Path = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Directorio donde escribir los JSON (default: data/outputs)",
    ),
    no_rag: bool = typer.Option(
        False,
        "--no-rag",
        help="Desactiva RAG aunque settings.rag_enabled sea True",
    ),
) -> None:
    """Ejecuta el pipeline E2E: transcripción + extracción de insights."""
    logger.info("=" * 80)
    logger.info("MeetingForge - E2E Pipeline")
    logger.info("=" * 80)

    if not audio_path.exists():
        logger.error("Archivo no encontrado: {p}", p=audio_path)
        raise typer.Exit(code=1)

    out_dir = output_dir or (settings.data_dir / "outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Paso 1: Transcripción
    logger.info("[1/3] Transcripción con Whisper")
    transcriber = WhisperTranscriber()
    transcript = transcriber.transcribe(audio_path)

    transcript_path = out_dir / f"{audio_path.stem}_transcript.json"
    transcript_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Transcripción guardada en: {p}", p=transcript_path)

    # Paso 2: (Opcional) Retriever
    retriever: Retriever | None = None
    use_rag = settings.rag_enabled and not no_rag
    if use_rag:
        logger.info("[2/3] Construyendo retriever (RAG activado)")
        retriever = _build_retriever()
    else:
        logger.info("[2/3] RAG desactivado")

    # Paso 3: Extracción
    logger.info("[3/3] Extracción de insights con LLM")
    extractor = InsightsExtractor(retriever=retriever)
    insights = extractor.extract(transcript)

    # Resultado final
    result = {
        "audio_file": str(audio_path),
        "transcript": transcript.model_dump(),
        "insights": insights.model_dump(),
        "metadata": {
            "provider": settings.llm_provider,
            "whisper_model": settings.whisper_model_size,
            "rag_enabled": retriever is not None,
            "embedding_model": settings.embedding_model if retriever else None,
        },
    }
    output_path = out_dir / f"{audio_path.stem}_result.json"
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    logger.info("Pipeline completado")
    logger.info("Resultado guardado en: {p}", p=output_path)
    logger.info("Decisiones encontradas: {n}", n=len(insights.decisions))
    logger.info("Tareas identificadas: {n}", n=len(insights.action_items))
    if insights.summary:
        logger.info("Resumen: {s}", s=insights.summary)


if __name__ == "__main__":
    app()
