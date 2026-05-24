#!/usr/bin/env python3
"""Walking skeleton: ejecuta el pipeline end-to-end audio → JSON estructurado."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from loguru import logger

# Permite ejecutar `python scripts/run_e2e.py ...` sin haber instalado el paquete.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from meeting_forge.analysis.extractor import InsightsExtractor  # noqa: E402
from meeting_forge.config import settings  # noqa: E402
from meeting_forge.ingestion.transcriber import WhisperTranscriber  # noqa: E402

app = typer.Typer(add_completion=False, help="MeetingForge E2E pipeline")


@app.command()
def main(
    audio_path: Path = typer.Argument(..., help="Path al archivo de audio"),
    output_dir: Path = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Directorio donde escribir los JSON (default: data/outputs)",
    ),
) -> None:
    """Ejecuta el pipeline E2E: transcripción + extracción de insights."""
    logger.info("=" * 80)
    logger.info("MeetingForge - Walking Skeleton E2E")
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
    transcript_path.write_text(
        transcript.model_dump_json(indent=2), encoding="utf-8"
    )
    logger.info("Transcripción guardada en: {p}", p=transcript_path)

    # Paso 2: Extracción de insights
    logger.info("[2/3] Extracción de insights con LLM")
    extractor = InsightsExtractor()
    insights = extractor.extract(transcript)

    # Paso 3: Resultado final
    logger.info("[3/3] Persistiendo resultado final")
    result = {
        "audio_file": str(audio_path),
        "transcript": transcript.model_dump(),
        "insights": insights.model_dump(),
        "metadata": {
            "provider": settings.llm_provider,
            "whisper_model": settings.whisper_model_size,
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
