"""Tests de la búsqueda entre reuniones (UX-8) con store/embeddings falsos."""

from __future__ import annotations

import json
from pathlib import Path

from meeting_forge import search as search_mod
from meeting_forge.rag.schemas import DocumentChunk, RetrievalResult


class _FakeEmbeddings:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t)), 0.0, 0.0] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 0.0, 0.0]


class _FakeStore:
    """VectorStore en memoria: un chunk por reunión, con delete_by_source."""

    def __init__(self) -> None:
        self.chunks: dict[str, DocumentChunk] = {}

    def add(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        for c in chunks:
            self.chunks[c.chunk_id] = c

    def query(self, embedding: list[float], top_k: int) -> list[RetrievalResult]:
        # Orden determinista por chunk_id; score fijo.
        results = [RetrievalResult(chunk=c, score=0.9) for c in self.chunks.values()]
        return results[:top_k]

    def count(self) -> int:
        return len(self.chunks)

    def clear(self) -> None:
        self.chunks.clear()

    def delete_by_source(self, source_path: str) -> int:
        to_del = [cid for cid, c in self.chunks.items() if c.source_path == source_path]
        for cid in to_del:
            del self.chunks[cid]
        return len(to_del)

    def list_sources(self) -> set[str]:
        return {c.source_path for c in self.chunks.values()}


def _result(summary: str = "", decisions: list[str] | None = None) -> dict[str, object]:
    return {
        "insights": {
            "summary": summary,
            "topics": ["migración"],
            "decisions": [{"title": d, "description": f"desc {d}"} for d in (decisions or [])],
            "action_items": [{"description": "Preparar el despliegue"}],
        },
        "transcript": {"segments": [{"text": "hablamos de la migración a microservicios"}]},
    }


class TestBuildIndexText:
    def test_includes_summary_topics_decisions_and_transcript(self) -> None:
        text = search_mod.build_index_text(_result("resumen ejecutivo", ["Adoptar ChromaDB"]))
        assert "resumen ejecutivo" in text
        assert "migración" in text
        assert "Adoptar ChromaDB" in text
        assert "Preparar el despliegue" in text
        assert "microservicios" in text

    def test_empty_result_returns_empty(self) -> None:
        assert search_mod.build_index_text({}) == ""

    def test_truncates_to_max(self) -> None:
        big = {"insights": {"summary": "x" * 10000}}
        assert len(search_mod.build_index_text(big)) == search_mod._INDEX_TEXT_MAX_CHARS


class TestIndexAndSearch:
    def test_index_meeting_stores_one_chunk_per_meeting(self) -> None:
        store = _FakeStore()
        emb = _FakeEmbeddings()
        assert search_mod.index_meeting("m1", _result("hola"), store=store, embeddings=emb)
        assert store.count() == 1
        assert "m1" in store.chunks

    def test_reindex_does_not_duplicate(self) -> None:
        store = _FakeStore()
        emb = _FakeEmbeddings()
        search_mod.index_meeting("m1", _result("v1"), store=store, embeddings=emb)
        search_mod.index_meeting("m1", _result("v2 distinta"), store=store, embeddings=emb)
        assert store.count() == 1
        assert "v2 distinta" in store.chunks["m1"].text

    def test_index_empty_meeting_returns_false(self) -> None:
        store = _FakeStore()
        assert (
            search_mod.index_meeting("m1", {}, store=store, embeddings=_FakeEmbeddings()) is False
        )
        assert store.count() == 0

    def test_search_maps_source_path_to_meeting_id(self) -> None:
        store = _FakeStore()
        emb = _FakeEmbeddings()
        search_mod.index_meeting("reunion-abc", _result("algo"), store=store, embeddings=emb)
        hits = search_mod.search_meetings("algo", top_k=5, store=store, embeddings=emb)
        assert hits[0].meeting_id == "reunion-abc"
        assert hits[0].snippet

    def test_empty_query_returns_no_hits(self) -> None:
        store = _FakeStore()
        assert search_mod.search_meetings("  ", store=store, embeddings=_FakeEmbeddings()) == []


class TestIndexAllAndSubstring:
    def _write(self, outputs_dir: Path, meeting_id: str, result: dict[str, object]) -> None:
        d = outputs_dir / meeting_id
        d.mkdir(parents=True)
        (d / f"{meeting_id}_result.json").write_text(json.dumps(result), encoding="utf-8")

    def test_index_all_meetings(self, tmp_path: Path) -> None:
        self._write(tmp_path, "m1", _result("uno"))
        self._write(tmp_path, "m2", _result("dos"))
        store = _FakeStore()
        n = search_mod.index_all_meetings(tmp_path, store=store, embeddings=_FakeEmbeddings())
        assert n == 2
        assert store.count() == 2

    def test_substring_search(self, tmp_path: Path) -> None:
        self._write(tmp_path, "m1", _result("hablamos de presupuesto"))
        self._write(tmp_path, "m2", _result("otra cosa"))
        assert search_mod.substring_search(tmp_path, "presupuesto") == ["m1"]
        assert search_mod.substring_search(tmp_path, "  ") == []
