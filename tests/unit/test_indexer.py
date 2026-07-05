"""Tests del indexador RAG: exclusión de directorios (B1) y poda de chunks obsoletos (B2)."""

from __future__ import annotations

from pathlib import Path

from meeting_forge.rag.indexer import DocumentIndexer, resolve_corpus_paths
from meeting_forge.rag.schemas import DocumentChunk, RetrievalResult


class _FakeEmbeddings:
    """EmbeddingModel mínimo para tests (sin descargar modelos)."""

    @property
    def dimension(self) -> int:
        return 3

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class _FakeStore:
    """VectorStore en memoria que registra las llamadas a delete_by_source."""

    def __init__(self) -> None:
        self.chunks: dict[str, DocumentChunk] = {}
        self.deleted_sources: list[str] = []

    def add(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        for chunk in chunks:
            self.chunks[chunk.chunk_id] = chunk

    def query(self, embedding: list[float], top_k: int) -> list[RetrievalResult]:
        return []

    def count(self) -> int:
        return len(self.chunks)

    def clear(self) -> None:
        self.chunks.clear()

    def delete_by_source(self, source_path: str) -> int:
        to_delete = [cid for cid, c in self.chunks.items() if c.source_path == source_path]
        for cid in to_delete:
            del self.chunks[cid]
        self.deleted_sources.append(source_path)
        return len(to_delete)

    def list_sources(self) -> set[str]:
        return {c.source_path for c in self.chunks.values()}


def _make_indexer() -> tuple[DocumentIndexer, _FakeStore]:
    store = _FakeStore()
    indexer = DocumentIndexer(store=store, embeddings=_FakeEmbeddings())
    return indexer, store


# ---------------------------------------------------------------------------
# B1 · _collect_markdown excluye .venv y ruido del repo
# ---------------------------------------------------------------------------


class TestCollectMarkdown:
    def test_excludes_venv_hidden_and_noise_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text("# Guide", encoding="utf-8")
        # Ruido que NO debe indexarse
        (tmp_path / ".venv" / "lib").mkdir(parents=True)
        (tmp_path / ".venv" / "lib" / "dep.md").write_text("# Dep", encoding="utf-8")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg.md").write_text("# Pkg", encoding="utf-8")
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "x.md").write_text("# X", encoding="utf-8")
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "out.md").write_text("# Out", encoding="utf-8")

        found = DocumentIndexer._collect_markdown([tmp_path])

        assert {p.name for p in found} == {"guide.md"}

    def test_explicit_md_file_is_collected(self, tmp_path: Path) -> None:
        f = tmp_path / "readme.md"
        f.write_text("# R", encoding="utf-8")
        found = DocumentIndexer._collect_markdown([f])
        assert [p.name for p in found] == ["readme.md"]

    def test_custom_exclude_overrides_default(self, tmp_path: Path) -> None:
        (tmp_path / "keep").mkdir()
        (tmp_path / "keep" / "a.md").write_text("# A", encoding="utf-8")
        (tmp_path / "skipme").mkdir()
        (tmp_path / "skipme" / "b.md").write_text("# B", encoding="utf-8")
        found = DocumentIndexer._collect_markdown([tmp_path], exclude={"skipme"})
        assert {p.name for p in found} == {"a.md"}

    def test_excludes_project_noise_dirs(self, tmp_path: Path) -> None:
        # BUG-1: prompts/, tests/, evaluation/, notebooks/, scripts/ y planes/ no son
        # documentación citable y no deben contaminar el corpus del RAG.
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "real.md").write_text("# Real", encoding="utf-8")
        for noise_dir, fname in [
            ("prompts", "v1.md"),
            ("tests", "fixture.md"),
            ("evaluation", "report.md"),
            ("notebooks", "nb.md"),
            ("scripts", "x.md"),
            ("planes", "roadmap.md"),
        ]:
            (tmp_path / noise_dir).mkdir()
            (tmp_path / noise_dir / fname).write_text("# noise", encoding="utf-8")

        found = DocumentIndexer._collect_markdown([tmp_path])

        assert {p.name for p in found} == {"real.md"}


# ---------------------------------------------------------------------------
# B2 · reindexar un documento editado no deja chunks obsoletos
# ---------------------------------------------------------------------------


class TestResolveCorpusPaths:
    def test_docs_path_and_extra_exclude_repo_by_default(self, tmp_path: Path) -> None:
        # M1: por defecto el corpus es docs_path + --path, NO el repo entero.
        docs = tmp_path / "docs"
        extra = tmp_path / "more"
        root = tmp_path / "repo"
        assert resolve_corpus_paths(docs, [extra], root, include_repo=False) == [docs, extra]

    def test_include_repo_appends_root(self, tmp_path: Path) -> None:
        docs = tmp_path / "docs"
        root = tmp_path / "repo"
        assert resolve_corpus_paths(docs, None, root, include_repo=True) == [docs, root]

    def test_falls_back_to_repo_when_nothing_configured(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        assert resolve_corpus_paths(None, None, root, include_repo=False) == [root]


class TestReindexPrunesStale:
    def test_editing_a_doc_removes_old_chunks(self, tmp_path: Path) -> None:
        doc = tmp_path / "doc.md"
        doc.write_text("# Titulo\n\nprimera version del contenido\n", encoding="utf-8")
        indexer, store = _make_indexer()

        indexer.index_paths([tmp_path], root=tmp_path)
        first_ids = set(store.chunks)
        assert first_ids, "esperaba al menos un chunk tras la primera indexación"

        # Editar el documento → contenido distinto → nuevos chunk_id
        doc.write_text(
            "# Titulo\n\nsegunda version totalmente distinta del texto\n", encoding="utf-8"
        )
        indexer.index_paths([tmp_path], root=tmp_path)

        assert "doc.md" in store.deleted_sources
        assert first_ids.isdisjoint(set(store.chunks)), "los chunks viejos no deben sobrevivir"
        assert all(c.source_path == "doc.md" for c in store.chunks.values())


class TestExternalPathsDoNotCollide:
    def test_same_basename_outside_root_keeps_both_sources(self, tmp_path: Path) -> None:
        # Ficheros fuera de `root` (DOCS_PATH externo) no deben colapsar a su basename:
        # dos README.md homónimos se borraban mutuamente los chunks vía delete_by_source.
        docs = tmp_path / "docs"
        (docs / "a").mkdir(parents=True)
        (docs / "b").mkdir(parents=True)
        (docs / "a" / "README.md").write_text("# A\n\ncontenido a\n", encoding="utf-8")
        (docs / "b" / "README.md").write_text("# B\n\ncontenido b\n", encoding="utf-8")
        indexer, store = _make_indexer()

        # root apunta a OTRO directorio: ninguno de los dos ficheros es relativo a él.
        root = tmp_path / "repo"
        root.mkdir()
        indexer.index_paths([docs], root=root)

        sources = {c.source_path for c in store.chunks.values()}
        assert len(sources) == 2, "cada fichero externo debe conservar un source_path único"
        assert all(s.endswith("README.md") for s in sources)


class TestSyncPrunesDeletedFiles:
    def test_sync_removes_chunks_of_deleted_files(self, tmp_path: Path) -> None:
        # F6: sync debe podar los chunks de ficheros que ya no existen.
        (tmp_path / "a.md").write_text("# A\n\ncontenido a\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("# B\n\ncontenido b\n", encoding="utf-8")
        indexer, store = _make_indexer()

        indexer.sync_paths([tmp_path], root=tmp_path)
        assert {c.source_path for c in store.chunks.values()} == {"a.md", "b.md"}

        (tmp_path / "b.md").unlink()
        indexer.sync_paths([tmp_path], root=tmp_path)
        assert {c.source_path for c in store.chunks.values()} == {"a.md"}
