"""Tests de la memoria RAG de documentos aprobados (UX-9) con store/embeddings falsos."""

from __future__ import annotations

from meeting_forge import memory
from meeting_forge.generation.schemas import GeneratedDocView
from meeting_forge.rag.schemas import DocumentChunk, RetrievalResult
from meeting_forge.validation import store as val_store


class _FakeEmbeddings:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class _FakeStore:
    def __init__(self) -> None:
        self.chunks: dict[str, DocumentChunk] = {}
        self.deleted: list[str] = []

    def add(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        for c in chunks:
            self.chunks[c.chunk_id] = c

    def query(self, embedding: list[float], top_k: int) -> list[RetrievalResult]:
        return []

    def count(self) -> int:
        return len(self.chunks)

    def clear(self) -> None:
        self.chunks.clear()

    def delete_by_source(self, source_path: str) -> int:
        self.deleted.append(source_path)
        to_del = [cid for cid, c in self.chunks.items() if c.source_path == source_path]
        for cid in to_del:
            del self.chunks[cid]
        return len(to_del)

    def list_sources(self) -> set[str]:
        return {c.source_path for c in self.chunks.values()}


def _doc(filename: str, kind: str = "acta") -> GeneratedDocView:
    return GeneratedDocView(
        filename=filename,
        kind=kind,
        markdown_content=f"# {filename}\n\nContenido del documento {filename}.\n",
    )


def test_source_path_is_stable_and_prefixed() -> None:
    assert memory.memory_source_path("m1", "acta", "acta-1.md") == "meetings/m1/acta/acta-1.md"


def test_indexes_only_approved_docs() -> None:
    from meeting_forge.validation.schemas import MeetingValidationState

    docs = [_doc("acta-1.md"), _doc("adr-1.md", kind="adr")]
    # Aprueba solo el acta; el ADR queda pendiente.
    state = val_store.mark_approved(MeetingValidationState(), "acta-1.md")

    store = _FakeStore()
    n = memory.index_approved_documents(
        "m1", docs, state, store=store, embeddings=_FakeEmbeddings()
    )

    assert n > 0
    sources = store.list_sources()
    assert "meetings/m1/acta/acta-1.md" in sources
    assert "meetings/m1/adr/adr-1.md" not in sources


def test_no_approved_docs_indexes_nothing() -> None:
    from meeting_forge.validation.schemas import MeetingValidationState

    docs = [_doc("acta-1.md")]
    store = _FakeStore()
    n = memory.index_approved_documents(
        "m1", docs, MeetingValidationState(), store=store, embeddings=_FakeEmbeddings()
    )
    assert n == 0
    assert store.count() == 0


def test_uses_edited_content_and_reindexes_clean() -> None:
    from meeting_forge.validation.schemas import MeetingValidationState

    docs = [_doc("acta-1.md")]
    state = MeetingValidationState()
    state = val_store.mark_approved(
        state, "acta-1.md", edited_content="# Editado\n\nTexto nuevo.\n"
    )

    store = _FakeStore()
    memory.index_approved_documents("m1", docs, state, store=store, embeddings=_FakeEmbeddings())

    # delete_by_source se llama antes de insertar (reindexado limpio).
    assert "meetings/m1/acta/acta-1.md" in store.deleted
    indexed_text = " ".join(c.text for c in store.chunks.values())
    assert "Texto nuevo" in indexed_text
