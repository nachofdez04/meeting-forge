"""Tests del MarkdownChunker."""

from pathlib import Path

from meeting_forge.rag.chunker import MarkdownChunker

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "sample_docs"


def test_chunks_have_section_path_for_each_header() -> None:
    chunker = MarkdownChunker()
    content = (FIXTURES / "adr-001.md").read_text(encoding="utf-8")
    chunks = chunker.chunk_file("adr-001.md", content)

    assert len(chunks) >= 3  # Contexto, Decisión, Consecuencias
    titles = {tuple(c.section_path) for c in chunks}
    assert ("ADR-001: Adopción de uv", "Contexto") in titles
    assert ("ADR-001: Adopción de uv", "Decisión") in titles
    assert ("ADR-001: Adopción de uv", "Consecuencias") in titles


def test_chunk_ids_are_deterministic() -> None:
    chunker = MarkdownChunker()
    content = (FIXTURES / "adr-001.md").read_text(encoding="utf-8")
    a = chunker.chunk_file("adr-001.md", content)
    b = chunker.chunk_file("adr-001.md", content)
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]


def test_long_section_is_split_with_overlap() -> None:
    chunker = MarkdownChunker(max_chars=120, overlap_chars=20)
    long_body = " ".join(["palabra"] * 200)  # > 120 chars
    content = f"# Título\n\n## Sección larga\n\n{long_body}\n"
    chunks = chunker.chunk_file("doc.md", content)

    long_section_chunks = [c for c in chunks if c.section_path == ["Título", "Sección larga"]]
    assert len(long_section_chunks) > 1
    # Texto total recubierto incluso con overlap
    joined = "".join(c.text for c in long_section_chunks)
    assert "palabra" in joined


def test_file_without_headers_produces_one_chunk() -> None:
    chunker = MarkdownChunker()
    content = "Solo texto plano, sin headers.\nOtra línea."
    chunks = chunker.chunk_file("plain.md", content)
    assert len(chunks) == 1
    assert chunks[0].section_path == []
    assert "Solo texto plano" in chunks[0].text


def test_glossary_nested_headers_keep_hierarchy() -> None:
    chunker = MarkdownChunker()
    content = (FIXTURES / "glossary.md").read_text(encoding="utf-8")
    chunks = chunker.chunk_file("glossary.md", content)

    rag_chunks = [c for c in chunks if c.section_path[-1:] == ["RAG"]]
    assert rag_chunks, "Esperaba al menos un chunk para la sección RAG"
    assert rag_chunks[0].section_path[:2] == ["Glosario del proyecto", "Términos técnicos"]
