#!/usr/bin/env python3
"""CLI del pipeline end-to-end: audio → transcripción → insights → documentos generados.

La orquestación vive en `meeting_forge.pipeline.run_pipeline` (reutilizada por la UI · F4); este
script solo parsea los argumentos de línea de comandos.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from loguru import logger

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from meeting_forge.pipeline import parse_modes, run_pipeline  # noqa: E402

app = typer.Typer(add_completion=False, help="MeetingForge E2E pipeline")


@app.command()
def main(
    audio_path: Path = typer.Argument(..., help="Path al archivo de audio"),
    output_dir: Path = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Directorio base donde escribir los outputs (default: data/outputs)",
    ),
    no_rag: bool = typer.Option(False, "--no-rag", help="Desactiva RAG aunque esté habilitado"),
    no_generation: bool = typer.Option(
        False, "--no-generation", help="Salta la generación de documentos"
    ),
    generate_modes: str = typer.Option(
        "",
        "--generate-modes",
        help=(
            "Modos separados por coma: adr-per-decision, adr-consolidated, acta, "
            "roadmap-update, technical-doc-update. Default: GENERATION_MODES del settings."
        ),
    ),
    meeting_title: str = typer.Option("", "--meeting-title", help="Título de la reunión"),
    meeting_date: str = typer.Option(
        "", "--meeting-date", help="Fecha ISO YYYY-MM-DD (default: mtime del audio)"
    ),
) -> None:
    """Ejecuta el pipeline E2E: transcripción + extracción + generación de documentos."""
    logger.info("=" * 80)
    logger.info("MeetingForge - E2E Pipeline")
    logger.info("=" * 80)

    if not audio_path.exists():
        logger.error("Archivo no encontrado: {p}", p=audio_path)
        raise typer.Exit(code=1)

    modes = parse_modes(generate_modes) if generate_modes.strip() else None
    result = run_pipeline(
        audio_path,
        output_dir=output_dir,
        use_rag=not no_rag,
        use_generation=not no_generation,
        modes=modes,
        meeting_title=meeting_title,
        meeting_date=meeting_date,
    )

    logger.info("Resultado guardado en: {p}", p=result.result_path)
    logger.info(
        "Decisiones: {d} · Tareas: {a} · Documentos: {n} · Run: {r}",
        d=result.n_decisions,
        a=result.n_actions,
        n=result.n_documents,
        r=result.run_id,
    )


if __name__ == "__main__":
    app()
