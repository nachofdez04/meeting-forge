"""Vector store abstraction y backend ChromaDB."""

from __future__ import annotations

from typing import Any, Protocol

import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger

from ..config import settings
from .schemas import DocumentChunk, RetrievalResult


class VectorStore(Protocol):
    """Protocolo común para vector stores."""

    def add(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None: ...

    def query(self, embedding: list[float], top_k: int) -> list[RetrievalResult]: ...

    def count(self) -> int: ...

    def clear(self) -> None: ...

    def delete_by_source(self, source_path: str) -> int: ...

    def list_sources(self) -> set[str]: ...


def _chunk_to_metadata(chunk: DocumentChunk) -> dict[str, Any]:
    """Convierte un DocumentChunk a metadata serializable de Chroma."""
    return {
        "source_path": chunk.source_path,
        "section_path": "/".join(chunk.section_path),
        "line_start": chunk.line_start,
        "line_end": chunk.line_end,
    }


def _metadata_to_chunk(chunk_id: str, text: str, metadata: dict[str, Any]) -> DocumentChunk:
    """Reconstruye un DocumentChunk desde metadata."""
    section_str = metadata.get("section_path") or ""
    section_path = section_str.split("/") if section_str else []
    return DocumentChunk(
        chunk_id=chunk_id,
        source_path=str(metadata.get("source_path", "")),
        section_path=section_path,
        text=text,
        line_start=int(metadata.get("line_start", 0)),
        line_end=int(metadata.get("line_end", 0)),
    )


class ChromaVectorStore:
    """Persistencia vectorial sobre ChromaDB local."""

    def __init__(self, collection_name: str | None = None) -> None:
        self.collection_name = collection_name or settings.chroma_collection
        self._client = chromadb.PersistentClient(
            path=str(settings.chromadb_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaVectorStore listo (collection={c}, path={p})",
            c=self.collection_name,
            p=settings.chromadb_path,
        )

    def add(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        if len(chunks) != len(embeddings):
            raise ValueError("chunks y embeddings deben tener la misma longitud")
        self._collection.upsert(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[_chunk_to_metadata(c) for c in chunks],
            embeddings=embeddings,  # type: ignore[arg-type]
        )

    def query(self, embedding: list[float], top_k: int) -> list[RetrievalResult]:
        res = self._collection.query(
            query_embeddings=[embedding],  # type: ignore[arg-type]
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        results: list[RetrievalResult] = []
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for chunk_id, text, meta, dist in zip(ids, docs, metas, dists, strict=False):
            chunk = _metadata_to_chunk(chunk_id, text or "", dict(meta or {}))
            # Chroma usa distancia coseno (0=idéntico). Convertimos a score [0..1], con clamp (B8):
            # la distancia coseno cae en [0, 2], por lo que 1 - dist podría ser negativo.
            score = max(0.0, min(1.0, 1.0 - float(dist))) if dist is not None else 0.0
            results.append(RetrievalResult(chunk=chunk, score=score))
        return results

    def count(self) -> int:
        return int(self._collection.count())

    def clear(self) -> None:
        """Elimina todos los chunks de la colección."""
        existing = self._collection.get()
        ids = existing.get("ids") or []
        if ids:
            self._collection.delete(ids=ids)
            logger.info("Vector store limpiado ({n} chunks eliminados)", n=len(ids))

    def delete_by_source(self, source_path: str) -> int:
        """Elimina todos los chunks asociados a un `source_path`. Devuelve cuántos borró.

        Evita chunks huérfanos al reindexar un documento editado, vaciado o renombrado.
        """
        existing = self._collection.get(where={"source_path": source_path})
        ids = existing.get("ids") or []
        if ids:
            self._collection.delete(ids=ids)
        return len(ids)

    def list_sources(self) -> set[str]:
        """Devuelve el conjunto de `source_path` distintos presentes en la colección."""
        existing = self._collection.get(include=["metadatas"])
        metas = existing.get("metadatas") or []
        return {str(m.get("source_path", "")) for m in metas if m}
