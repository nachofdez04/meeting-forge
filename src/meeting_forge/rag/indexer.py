"""Orquestador de indexación de documentos: chunk + embed + store."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from loguru import logger

from .chunker import MarkdownChunker
from .embeddings import EmbeddingModel
from .schemas import DocumentChunk
from .vector_store import VectorStore

# Directorios que NUNCA deben indexarse al recorrer un repo (B1): entornos virtuales,
# control de versiones, datos, cachés y artefactos de build. Los dirs ocultos (".algo")
# también se podan automáticamente.
_DEFAULT_EXCLUDE_DIRS = frozenset(
    {
        ".venv",
        "venv",
        "env",
        ".git",
        "node_modules",
        "data",
        "site-packages",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        "build",
        "dist",
    }
)


def _walk_markdown(root: Path, exclude: set[str]) -> Iterator[Path]:
    """Itera los ``*.md`` bajo *root*, podando dirs excluidos y ocultos.

    Usa ``os.walk`` con poda in-place de ``dirnames`` para no descender siquiera en
    ``.venv``/``.git``/etc. (evita recorrer miles de ficheros de dependencias).
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude and not d.startswith(".")]
        for filename in filenames:
            if filename.lower().endswith(".md"):
                yield Path(dirpath) / filename


class DocumentIndexer:
    """Indexa Markdown en un VectorStore."""

    def __init__(
        self,
        store: VectorStore,
        embeddings: EmbeddingModel,
        chunker: MarkdownChunker | None = None,
    ) -> None:
        self.store = store
        self.embeddings = embeddings
        self.chunker = chunker or MarkdownChunker()

    def index_paths(
        self,
        paths: list[Path],
        root: Path | None = None,
        exclude: set[str] | None = None,
    ) -> int:
        """Indexa todos los `.md` bajo las rutas dadas.

        Args:
            paths: directorios o archivos.
            root: si se da, las source_path se almacenan relativas a este root.
            exclude: nombres de directorios a excluir (default: `_DEFAULT_EXCLUDE_DIRS`).

        Returns:
            Número total de chunks indexados.
        """
        md_files = self._collect_markdown(paths, exclude)
        logger.info("Encontrados {n} archivos .md", n=len(md_files))

        total_chunks = 0
        for md_file in md_files:
            rel = self._relative_path(md_file, root)
            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("No se pudo leer {p}: {e}", p=md_file, e=exc)
                continue

            chunks = self.chunker.chunk_file(rel, content)
            # B2: elimina los chunks previos de este source antes de reinsertar, para que
            # editar/vaciar un documento no deje chunks obsoletos huérfanos en el store.
            removed = self.store.delete_by_source(rel)
            if removed:
                logger.debug("Eliminados {n} chunks obsoletos de {p}", n=removed, p=rel)
            if not chunks:
                logger.debug("Sin chunks útiles en {p}", p=rel)
                continue

            self._index_chunks(chunks)
            total_chunks += len(chunks)
            logger.info("Indexado {p} → {n} chunks", p=rel, n=len(chunks))

        logger.info("Total: {n} chunks (store={s})", n=total_chunks, s=self.store.count())
        return total_chunks

    def sync_paths(
        self,
        paths: list[Path],
        root: Path | None = None,
        exclude: set[str] | None = None,
    ) -> int:
        """Indexa y además **poda los chunks de documentos que ya no existen** (F6).

        Tras (re)indexar, elimina del store los chunks cuyo `source_path` no esté entre los ficheros
        actualmente presentes, cerrando el ciclo de B2 también para ficheros borrados o renombrados.
        """
        md_files = self._collect_markdown(paths, exclude)
        present = {self._relative_path(f, root) for f in md_files}

        total = self.index_paths(paths, root=root, exclude=exclude)

        for source in self.store.list_sources():
            if source not in present:
                removed = self.store.delete_by_source(source)
                if removed:
                    logger.info("Podados {n} chunks de fuente ausente: {p}", n=removed, p=source)
        return total

    def _index_chunks(self, chunks: list[DocumentChunk], batch_size: int = 32) -> None:
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = self.embeddings.embed_texts([c.text for c in batch])
            self.store.add(batch, vectors)

    @staticmethod
    def _collect_markdown(paths: list[Path], exclude: set[str] | None = None) -> list[Path]:
        excluded = exclude if exclude is not None else set(_DEFAULT_EXCLUDE_DIRS)
        files: list[Path] = []
        seen: set[Path] = set()
        for path in paths:
            if not path.exists():
                logger.warning("Ruta inexistente: {p}", p=path)
                continue
            if path.is_file() and path.suffix.lower() == ".md":
                resolved = path.resolve()
                if resolved not in seen:
                    files.append(resolved)
                    seen.add(resolved)
            elif path.is_dir():
                for md in _walk_markdown(path, excluded):
                    resolved = md.resolve()
                    if resolved not in seen:
                        files.append(resolved)
                        seen.add(resolved)
        return sorted(files)

    @staticmethod
    def _relative_path(md_file: Path, root: Path | None) -> str:
        if root is None:
            return md_file.name
        try:
            return str(md_file.relative_to(root.resolve())).replace("\\", "/")
        except ValueError:
            return md_file.name
