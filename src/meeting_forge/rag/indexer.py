"""Orquestador de indexación de documentos: chunk + embed + store."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from .chunker import MarkdownChunker
from .embeddings import EmbeddingModel
from .schemas import DocumentChunk
from .vector_store import VectorStore


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

    def index_paths(self, paths: list[Path], root: Path | None = None) -> int:
        """Indexa todos los `.md` bajo las rutas dadas.

        Args:
            paths: directorios o archivos.
            root: si se da, las source_path se almacenan relativas a este root.

        Returns:
            Número total de chunks indexados.
        """
        md_files = self._collect_markdown(paths)
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
            if not chunks:
                logger.debug("Sin chunks útiles en {p}", p=rel)
                continue

            self._index_chunks(chunks)
            total_chunks += len(chunks)
            logger.info("Indexado {p} → {n} chunks", p=rel, n=len(chunks))

        logger.info("Total: {n} chunks (store={s})", n=total_chunks, s=self.store.count())
        return total_chunks

    def _index_chunks(self, chunks: list[DocumentChunk], batch_size: int = 32) -> None:
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = self.embeddings.embed_texts([c.text for c in batch])
            self.store.add(batch, vectors)

    @staticmethod
    def _collect_markdown(paths: list[Path]) -> list[Path]:
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
                for md in path.rglob("*.md"):
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
