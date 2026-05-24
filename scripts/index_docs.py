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

from meeting_forge.config import settings  # noqa: E402
from meeting_forge.rag.embeddings import SentenceTransformerEmbeddings  # noqa: E402
from meeting_forge.rag.indexer import DocumentIndexer  # noqa: E402
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
) -> None:
    """Indexa documentación Markdown.

    Por defecto indexa:
      - El root del repo (`*.md` recursivo)
      - El directorio apuntado por `DOCS_PATH` si está definido.
    """
    logger.info("=" * 80)
    logger.info("MeetingForge - Indexación de documentación")
    logger.info("=" * 80)

    paths: list[Path] = []
    paths.append(settings.project_root)
    if settings.docs_path is not None:
        paths.append(settings.docs_path)
    if path:
        paths.extend(path)

    logger.info("Rutas a indexar:")
    for p in paths:
        logger.info("  - {p}", p=p)

    store = ChromaVectorStore()
    if clear:
        logger.info("Limpiando colección existente...")
        store.clear()

    embeddings = SentenceTransformerEmbeddings()
    indexer = DocumentIndexer(store=store, embeddings=embeddings)

    total = indexer.index_paths(paths, root=settings.project_root)
    logger.info("Indexación completada: {n} chunks añadidos", n=total)
    logger.info("Total en store: {n}", n=store.count())


if __name__ == "__main__":
    app()
