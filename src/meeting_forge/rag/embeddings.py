"""Modelo de embeddings para RAG."""

from __future__ import annotations

from typing import Protocol

from loguru import logger
from sentence_transformers import SentenceTransformer

from ..config import settings


class EmbeddingModel(Protocol):
    """Protocolo común para modelos de embeddings."""

    @property
    def dimension(self) -> int:
        """Dimensionalidad del embedding."""
        ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embedding por batch."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embedding de una sola query."""
        ...


_model_cache: dict[str, SentenceTransformer] = {}


def _load_sentence_transformer(name: str) -> SentenceTransformer:
    """Carga (con cache) un modelo de sentence-transformers."""
    if name not in _model_cache:
        logger.info("Cargando modelo de embeddings: {n}", n=name)
        _model_cache[name] = SentenceTransformer(name)
        logger.info("Modelo de embeddings cargado")
    return _model_cache[name]


class SentenceTransformerEmbeddings:
    """Implementación basada en sentence-transformers (local, gratis)."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.embedding_model
        self._model = _load_sentence_transformer(self.model_name)

    @property
    def dimension(self) -> int:
        dim = self._model.get_sentence_embedding_dimension()
        if dim is None:
            raise RuntimeError(f"No se pudo determinar la dimensión de {self.model_name}")
        return int(dim)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return [vec.tolist() for vec in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]
