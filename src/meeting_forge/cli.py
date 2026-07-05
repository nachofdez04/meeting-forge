"""CLI unificado de MeetingForge (entrypoint `meeting-forge`) · F10.

Subcomandos: `run`, `index`, `eval`, `demo`, `check`. Reutiliza los servicios del paquete
(pipeline, evaluación, demo) para que el mismo código sirva al CLI y a la UI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from loguru import logger

from .config import configure_logging, ensure_data_dirs, settings
from .demo import build_demo_meeting
from .evaluation.runner import evaluate, render_markdown
from .evaluation.schemas import EvalDataset

app = typer.Typer(
    add_completion=False, help="MeetingForge — pipeline, indexación, evaluación y demo"
)


@app.callback()
def _main() -> None:
    """Configura el logging (respetando LOG_LEVEL) antes de cualquier subcomando."""
    configure_logging()


@app.command()
def run(
    audio_path: Path = typer.Argument(..., help="Path al archivo de audio"),
    no_rag: bool = typer.Option(False, "--no-rag", help="Desactiva RAG"),
    no_generation: bool = typer.Option(False, "--no-generation", help="Salta la generación"),
    generate_modes: str = typer.Option("", "--generate-modes", help="CSV de modos de generación"),
    meeting_title: str = typer.Option("", "--meeting-title", help="Título de la reunión"),
    meeting_date: str = typer.Option("", "--meeting-date", help="Fecha ISO YYYY-MM-DD"),
    attendees: str = typer.Option(
        "", "--attendees", help="Asistentes separados por comas (aparecen en el acta)"
    ),
    vocabulary: str = typer.Option(
        "",
        "--vocabulary",
        help="Términos/nombres del proyecto para guiar a Whisper (además del glosario)",
    ),
) -> None:
    """Ejecuta el pipeline E2E sobre un audio (o un vídeo del que se extrae la pista de audio)."""
    # import perezoso (dependencias pesadas)
    from .pipeline import parse_attendees, parse_modes, run_pipeline

    if not audio_path.exists():
        logger.error("Archivo no encontrado: {p}", p=audio_path)
        raise typer.Exit(code=1)
    modes = parse_modes(generate_modes) if generate_modes.strip() else None
    result = run_pipeline(
        audio_path,
        use_rag=not no_rag,
        use_generation=not no_generation,
        modes=modes,
        meeting_title=meeting_title,
        meeting_date=meeting_date,
        attendees=parse_attendees(attendees),
        vocabulary=vocabulary,
    )
    logger.info(
        "Resultado en {p} · {d} decisiones · {a} tareas · {n} documentos",
        p=result.result_path,
        d=result.n_decisions,
        a=result.n_actions,
        n=result.n_documents,
    )


@app.command()
def index(
    path: list[Path] = typer.Option(None, "--path", "-p", help="Rutas adicionales a indexar"),
    clear: bool = typer.Option(False, "--clear", help="Limpia la colección antes de indexar"),
    sync: bool = typer.Option(False, "--sync", help="Poda los chunks de ficheros ya inexistentes"),
    include_repo: bool = typer.Option(
        False,
        "--include-repo",
        help="Incluye TODO el repo en el corpus (por defecto solo DOCS_PATH/--path)",
    ),
) -> None:
    """Indexa la documentación Markdown en el vector store."""
    from .rag.embeddings import SentenceTransformerEmbeddings
    from .rag.indexer import DocumentIndexer, resolve_corpus_paths
    from .rag.vector_store import ChromaVectorStore

    ensure_data_dirs()
    paths = resolve_corpus_paths(
        settings.docs_path, path, settings.project_root, include_repo=include_repo
    )
    if not include_repo and settings.docs_path is None and not path:
        logger.warning(
            "Sin DOCS_PATH ni --path: se indexa el repo entero como último recurso. "
            "Define DOCS_PATH (o usa --include-repo) para un corpus de documentación limpio."
        )

    store = ChromaVectorStore()
    if clear:
        store.clear()
    indexer = DocumentIndexer(store=store, embeddings=SentenceTransformerEmbeddings())
    total = (
        indexer.sync_paths(paths, root=settings.project_root)
        if sync
        else indexer.index_paths(paths, root=settings.project_root)
    )
    logger.info("Indexación completada: {n} chunks (total en store={s})", n=total, s=store.count())


@app.command("eval")
def eval_cmd(
    dataset: Path = typer.Argument(..., help="Dataset JSON de evaluación"),
    k: int = typer.Option(5, "--k", help="k para precision@k / recall@k"),
    output_dir: Path = typer.Option(None, "--output-dir", "-o", help="Directorio del reporte"),
    from_run: list[Path] = typer.Option(
        None,
        "--from-run",
        help="result.json de runs para añadir coste/latencia al reporte (repetible)",
    ),
) -> None:
    """Calcula métricas (WER, P/R/F1, precision@k) y escribe el reporte.

    Con `--from-run <result.json>` (repetible) agrega las métricas de coste y latencia desde la
    telemetría (`run_meta`) de ejecuciones reales del pipeline.
    """
    if not dataset.exists():
        logger.error("Dataset no encontrado: {p}", p=dataset)
        raise typer.Exit(code=1)
    data = EvalDataset.model_validate_json(dataset.read_text(encoding="utf-8"))

    run_metas: list[dict[str, object]] = []
    for run_path in from_run or []:
        if not run_path.exists():
            logger.warning("Run ignorado (no existe): {p}", p=run_path)
            continue
        raw = json.loads(run_path.read_text(encoding="utf-8"))
        meta = raw.get("run_meta") if isinstance(raw, dict) else None
        if isinstance(meta, dict):
            run_metas.append(meta)
        else:
            logger.warning("Run sin 'run_meta' utilizable: {p}", p=run_path)

    report = evaluate(data, k=k, run_metas=run_metas or None)
    markdown = render_markdown(report)
    typer.echo(markdown)
    out_dir = output_dir or (settings.project_root / "evaluation" / "results")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "report.md").write_text(markdown + "\n", encoding="utf-8")
    logger.info("Reporte escrito en {d}", d=out_dir)


@app.command()
def demo() -> None:
    """Crea una reunión de demostración (sin LLM ni audio) para explorar la UI."""
    ensure_data_dirs()
    meeting_dir = build_demo_meeting(settings.data_dir / "outputs")
    typer.echo(f"Demo creada en: {meeting_dir}")
    typer.echo("Lanza la UI: uv run --group ui streamlit run src/meeting_forge/ui/app.py")


@app.command("search")
def search_cmd(
    query: str = typer.Argument(..., help="Consulta de búsqueda semántica entre reuniones"),
    top_k: int = typer.Option(5, "--top-k", help="Número de resultados"),
    reindex: bool = typer.Option(
        False, "--reindex", help="Reindexa todas las reuniones antes de buscar (UX-8)"
    ),
) -> None:
    """Busca reuniones relevantes para una consulta (UX-8).

    Con `--reindex` reconstruye el índice de búsqueda con todas las reuniones de `data/outputs/`
    (necesario la primera vez para reuniones procesadas antes de activar la búsqueda).
    """
    from .search import index_all_meetings, search_meetings

    ensure_data_dirs()
    outputs_dir = settings.data_dir / "outputs"
    if reindex:
        n = index_all_meetings(outputs_dir)
        typer.echo(f"Reindexadas {n} reunión(es).")

    hits = search_meetings(query, top_k=top_k)
    if not hits:
        typer.echo("Sin resultados. Prueba con --reindex si es la primera búsqueda.")
        return
    for hit in hits:
        typer.echo(f"[{hit.score:.3f}] {hit.meeting_id}")
        if hit.snippet:
            typer.echo(f"        {hit.snippet}")


@app.command()
def check() -> None:
    """Verifica prerequisitos: Python, ffmpeg, gh, API keys e índice RAG."""
    from .system_status import check_ffmpeg, check_gh, check_llm_key

    typer.echo(f"Python         : {sys.version.split()[0]}")
    for res in (check_ffmpeg(), check_gh(), check_llm_key()):
        suffix = f" — {res.remedy}" if not res.ok and res.remedy else ""
        typer.echo(f"{res.name:<15}: {res.detail}{suffix}")
    typer.echo(f"Proveedor LLM  : {settings.llm_provider}")
    typer.echo(f"RAG habilitado : {settings.rag_enabled}")


if __name__ == "__main__":
    app()
