#!/usr/bin/env python3
"""CLI de evaluación (F1): calcula métricas a partir de un dataset y emite JSON + Markdown.

Uso::

    uv run python scripts/evaluate.py evaluation/datasets/example.json
    uv run python scripts/evaluate.py evaluation/datasets/example.json --k 3 -o evaluation/results
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from loguru import logger

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from meeting_forge.evaluation.runner import evaluate, render_markdown  # noqa: E402
from meeting_forge.evaluation.schemas import EvalDataset  # noqa: E402

app = typer.Typer(
    add_completion=False, help="Evaluación de MeetingForge (WER, P/R/F1, precision@k)"
)


@app.command()
def main(
    dataset: Path = typer.Argument(..., help="Ruta al dataset JSON de evaluación"),
    k: int = typer.Option(5, "--k", help="k para precision@k / recall@k"),
    output_dir: Path = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Directorio donde escribir el reporte (default: evaluation/results)",
    ),
) -> None:
    """Calcula las métricas del dataset y escribe `report.json` y `report.md`."""
    if not dataset.exists():
        logger.error("Dataset no encontrado: {p}", p=dataset)
        raise typer.Exit(code=1)

    data = EvalDataset.model_validate_json(dataset.read_text(encoding="utf-8"))
    report = evaluate(data, k=k)
    markdown = render_markdown(report)

    print(markdown)

    out_dir = output_dir or (Path(__file__).resolve().parent.parent / "evaluation" / "results")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "report.md").write_text(markdown + "\n", encoding="utf-8")
    logger.info("Reporte escrito en {d}", d=out_dir)


if __name__ == "__main__":
    app()
