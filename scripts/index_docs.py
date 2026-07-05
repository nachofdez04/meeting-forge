#!/usr/bin/env python3
"""CLI para indexar documentación Markdown en el vector store."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from loguru import logger

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from meeting_forge.config import ensure_data_dirs, settings  # noqa: E402
from meeting_forge.rag.embeddings import SentenceTransformerEmbeddings  # noqa: E402
from meeting_forge.rag.indexer import DocumentIndexer, resolve_corpus_paths  # noqa: E402
from meeting_forge.rag.vector_store import ChromaVectorStore  # noqa: E402

app = typer.Typer(add_completion=False, help="Indexa Markdown en ChromaDB")


@app.command()
def main(
    path: list[Path] = typer.Option(
        None,
        "--path",
        "-p",
        help="Rutas adicionales a indexar (puede repetirse)",
    ),
    clear: bool = typer.Option(
        False,
        "--clear",
        help="Limpia la colección antes de indexar",
    ),
    sync: bool = typer.Option(
        False,
        "--sync",
        help="Tras indexar, poda los chunks de documentos que ya no existen (borrados/renombrados)",
    ),
    include_repo: bool = typer.Option(
        False,
        "--include-repo",
        help="Incluye TODO el repo en el corpus (por defecto solo DOCS_PATH/--path)",
    ),
) -> None:
    """Indexa documentación Markdown.

    Por defecto indexa el corpus de documentación del producto:
      - El directorio apuntado por `DOCS_PATH` si está definido.
      - Las rutas extra pasadas con `--path`.
    Usa `--include-repo` para añadir además todo el repo. Si no se configura nada, se cae al repo
    como último recurso (conviene definir `DOCS_PATH` para una provenance limpia · M1/B1).
    """
    logger.info("=" * 80)
    logger.info("MeetingForge - Indexación de documentación")
    logger.info("=" * 80)

    ensure_data_dirs()

    paths = resolve_corpus_paths(
        settings.docs_path, path, settings.project_root, include_repo=include_repo
    )
    if not include_repo and settings.docs_path is None and not path:
        logger.warning(
            "Sin DOCS_PATH ni --path: se indexa el repo entero como último recurso. "
            "Define DOCS_PATH (o usa --include-repo) para un corpus de documentación limpio."
        )

    logger.info("Rutas a indexar:")
    for p in paths:
        logger.info("  - {p}", p=p)

    store = ChromaVectorStore()
    if clear:
        logger.info("Limpiando colección existente...")
        store.clear()

    embeddings = SentenceTransformerEmbeddings()
    indexer = DocumentIndexer(store=store, embeddings=embeddings)

    if sync:
        total = indexer.sync_paths(paths, root=settings.project_root)
    else:
        total = indexer.index_paths(paths, root=settings.project_root)
    logger.info("Indexación completada: {n} chunks añadidos", n=total)
    logger.info("Total en store: {n}", n=store.count())


if __name__ == "__main__":
    app()
