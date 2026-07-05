"""Retriever que consulta el vector store y agrega resultados."""

from __future__ import annotations

from loguru import logger

from ..config import settings
from ..ingestion.schemas import Transcript
from .embeddings import EmbeddingModel
from .schemas import RetrievalResult
from .vector_store import VectorStore


def _sliding_windows(text: str, window: int, overlap: int) -> list[str]:
    """Divide text en ventanas de `window` chars con solapamiento `overlap`."""
    if window <= 0:
        return [text] if text else []
    if not text:
        return []
    if len(text) <= window:
        return [text]
    step = max(1, window - overlap)
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + window, len(text))
        out.append(text[start:end])
        if end == len(text):
            break
        start += step
    return out


class Retriever:
    """Recupera chunks relevantes para una transcripción."""

    def __init__(self, store: VectorStore, embeddings: EmbeddingModel) -> None:
        self.store = store
        self.embeddings = embeddings

    def retrieve(
        self, query: str, top_k: int | None = None, min_score: float | None = None
    ) -> list[RetrievalResult]:
        """Lookup de un único query, descartando chunks por debajo de `min_score` (M2)."""
        k = top_k or settings.retrieval_top_k
        threshold = settings.retrieval_min_score if min_score is None else min_score
        vec = self.embeddings.embed_query(query)
        results = self.store.query(vec, k)
        if threshold > 0.0:
            results = [r for r in results if r.score >= threshold]
        return results

    def retrieve_for_transcript(
        self,
        transcript: Transcript,
        k_total: int | None = None,
        per_query_k: int | None = None,
        min_score: float | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve por ventanas del transcript, agregando y deduplicando.

        Aplica el umbral `min_score` (M2/F6) por ventana, descartando chunks poco afines antes de
        agregar; así el contexto y la provenance solo incluyen evidencia con relevancia suficiente.
        """
        text = transcript.to_text()
        if not text.strip():
            return []

        windows = _sliding_windows(
            text,
            window=settings.transcript_query_chars,
            overlap=settings.chunk_overlap_chars,
        )
        per_q = per_query_k or settings.retrieval_per_query_k
        k_final = k_total or settings.retrieval_top_k

        best: dict[str, RetrievalResult] = {}
        for w in windows:
            results = self.retrieve(w, top_k=per_q, min_score=min_score)
            for r in results:
                existing = best.get(r.chunk.chunk_id)
                if existing is None or r.score > existing.score:
                    best[r.chunk.chunk_id] = r

        ordered = sorted(best.values(), key=lambda r: r.score, reverse=True)
        top = ordered[:k_final]
        logger.info(
            "Retrieved {n} chunks únicos a partir de {w} ventanas (top-{k})",
            n=len(top),
            w=len(windows),
            k=k_final,
        )
        return top
