"""Tests del Retriever con fakes (sin descarga de modelos ni Chroma)."""

from __future__ import annotations

from meeting_forge.ingestion.schemas import Transcript, TranscriptSegment
from meeting_forge.rag.retriever import Retriever, _sliding_windows
from meeting_forge.rag.schemas import DocumentChunk, RetrievalResult


class _FakeEmbeddings:
    """Embedding determinista: hash de la primera letra."""

    @property
    def dimension(self) -> int:
        return 4

    def embed_query(self, text: str) -> list[float]:
        h = ord(text[0]) if text else 0
        return [float((h >> i) & 1) for i in range(4)]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]


class _FakeStore:
    """Store que devuelve un guion preconfigurado para cada query."""

    def __init__(self, scripted: list[list[RetrievalResult]]) -> None:
        self._scripted = scripted
        self._idx = 0

    def add(self, chunks, embeddings) -> None:  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def query(self, embedding: list[float], top_k: int) -> list[RetrievalResult]:
        if self._idx >= len(self._scripted):
            return []
        results = self._scripted[self._idx][:top_k]
        self._idx += 1
        return results

    def count(self) -> int:
        return sum(len(s) for s in self._scripted)

    def clear(self) -> None:
        self._scripted = []


def _chunk(chunk_id: str, path: str = "x.md") -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        source_path=path,
        section_path=["root"],
        text=f"texto de {chunk_id}",
        line_start=1,
        line_end=10,
    )


def test_sliding_windows_short_text_returns_single_window() -> None:
    assert _sliding_windows("hola", window=10, overlap=2) == ["hola"]


def test_sliding_windows_long_text_overlaps() -> None:
    text = "abcdefghij" * 10  # 100 chars
    windows = _sliding_windows(text, window=30, overlap=10)
    assert len(windows) > 1
    # Sin gaps: el inicio de la siguiente ventana debe estar antes del fin de la anterior
    assert all(len(w) <= 30 for w in windows)
    assert windows[0].endswith(text[20:30])


def test_retriever_dedupes_and_keeps_highest_score() -> None:
    chunk_a = _chunk("a")
    chunk_b = _chunk("b")
    scripted = [
        [RetrievalResult(chunk=chunk_a, score=0.5), RetrievalResult(chunk=chunk_b, score=0.3)],
        [RetrievalResult(chunk=chunk_a, score=0.9)],  # mismo id, mejor score
        [RetrievalResult(chunk=chunk_b, score=0.4)],
    ]
    store = _FakeStore(scripted)
    retriever = Retriever(store=store, embeddings=_FakeEmbeddings())

    transcript = Transcript(
        segments=[TranscriptSegment(start=0, end=1, text="x" * 1500)],
        duration_seconds=1.0,
    )
    # Forzar varias ventanas con transcript_query_chars por defecto (500)
    results = retriever.retrieve_for_transcript(transcript, k_total=5, per_query_k=2)

    by_id = {r.chunk.chunk_id: r for r in results}
    assert "a" in by_id and "b" in by_id
    assert by_id["a"].score == 0.9  # se quedó con el mejor
    assert by_id["b"].score == 0.4
    # Orden por score descendente
    assert results[0].chunk.chunk_id == "a"


def test_retriever_empty_transcript_returns_empty() -> None:
    retriever = Retriever(store=_FakeStore([]), embeddings=_FakeEmbeddings())
    transcript = Transcript(segments=[], duration_seconds=0.0)
    assert retriever.retrieve_for_transcript(transcript) == []


def test_retrieve_filters_below_min_score() -> None:
    # M2: con min_score se descartan los chunks poco afines.
    scripted = [
        [
            RetrievalResult(chunk=_chunk("a"), score=0.8),
            RetrievalResult(chunk=_chunk("b"), score=0.2),
        ]
    ]
    retriever = Retriever(store=_FakeStore(scripted), embeddings=_FakeEmbeddings())
    results = retriever.retrieve("consulta", top_k=5, min_score=0.5)
    assert [r.chunk.chunk_id for r in results] == ["a"]


def test_retrieve_no_filter_when_min_score_zero() -> None:
    scripted = [
        [
            RetrievalResult(chunk=_chunk("a"), score=0.8),
            RetrievalResult(chunk=_chunk("b"), score=0.2),
        ]
    ]
    retriever = Retriever(store=_FakeStore(scripted), embeddings=_FakeEmbeddings())
    results = retriever.retrieve("consulta", top_k=5, min_score=0.0)
    assert {r.chunk.chunk_id for r in results} == {"a", "b"}
