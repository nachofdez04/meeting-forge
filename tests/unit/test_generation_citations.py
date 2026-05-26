"""Tests del módulo generation/citations.py."""

from __future__ import annotations

from meeting_forge.generation.citations import (
    CitationRegistry,
    escape_user_text,
    render_footnote_block,
    rewrite_markers,
)
from meeting_forge.rag.schemas import SourceRef


def _ref(path: str, start: int, end: int, section: list[str] | None = None) -> SourceRef:
    return SourceRef(
        source_path=path,
        line_start=start,
        line_end=end,
        section_path=section or [],
    )


# ---------------------------------------------------------------------------
# CitationRegistry
# ---------------------------------------------------------------------------


class TestCitationRegistry:
    def test_register_assigns_sequential_indices(self) -> None:
        reg = CitationRegistry()
        assert reg.register(_ref("a.md", 1, 5)) == 1
        assert reg.register(_ref("b.md", 10, 20)) == 2
        assert reg.register(_ref("c.md", 1, 1)) == 3

    def test_register_deduplicates_by_path_start_end(self) -> None:
        reg = CitationRegistry()
        ref = _ref("a.md", 1, 5)
        idx1 = reg.register(ref)
        # Mismo source path + líneas → mismo índice
        idx2 = reg.register(_ref("a.md", 1, 5, section=["Diferente sección"]))
        assert idx1 == idx2
        assert reg.size == 1

    def test_register_all_returns_indices_in_order(self) -> None:
        reg = CitationRegistry()
        refs = [_ref("a.md", 1, 5), _ref("b.md", 1, 5)]
        indices = reg.register_all(refs)
        assert indices == [1, 2]

    def test_get_returns_correct_ref(self) -> None:
        reg = CitationRegistry()
        ref = _ref("a.md", 3, 7)
        reg.register(ref)
        retrieved = reg.get(1)
        assert retrieved is not None
        assert retrieved.source_path == "a.md"
        assert retrieved.line_start == 3

    def test_get_returns_none_for_out_of_range(self) -> None:
        reg = CitationRegistry()
        assert reg.get(0) is None
        assert reg.get(1) is None
        reg.register(_ref("a.md", 1, 1))
        assert reg.get(2) is None

    def test_build_sources_block_format(self) -> None:
        reg = CitationRegistry()
        reg.register(_ref("docs/adr.md", 10, 20, ["Contexto"]))
        reg.register(_ref("docs/glossary.md", 5, 8))
        block = reg.build_sources_block()
        assert "[#1] docs/adr.md:10-20  (Contexto)" in block
        assert "[#2] docs/glossary.md:5-8" in block

    def test_build_sources_block_empty(self) -> None:
        reg = CitationRegistry()
        assert reg.build_sources_block() == ""


# ---------------------------------------------------------------------------
# rewrite_markers
# ---------------------------------------------------------------------------


class TestRewriteMarkers:
    def test_rewrites_single_marker(self) -> None:
        reg = CitationRegistry()
        reg.register(_ref("a.md", 1, 5))
        text, used = rewrite_markers("Se decidió adoptar ChromaDB #1 por su rendimiento.", reg)
        assert "[^1]" in text
        assert "#1" not in text
        assert used == {1}

    def test_rewrites_multiple_distinct_markers(self) -> None:
        reg = CitationRegistry()
        reg.register(_ref("a.md", 1, 5))
        reg.register(_ref("b.md", 1, 5))
        text, used = rewrite_markers("Ver #1 y también #2 para más contexto.", reg)
        assert "[^1]" in text
        assert "[^2]" in text
        assert used == {1, 2}

    def test_out_of_range_marker_kept_as_is(self) -> None:
        reg = CitationRegistry()
        reg.register(_ref("a.md", 1, 5))
        text, used = rewrite_markers("Referencia inválida #99.", reg)
        assert "#99" in text  # se mantiene, no se convierte
        assert 99 not in used

    def test_markers_inside_code_fence_not_rewritten(self) -> None:
        reg = CitationRegistry()
        reg.register(_ref("a.md", 1, 5))
        text, used = rewrite_markers("Fuera #1\n```\nDentro #1 no se toca\n```", reg)
        assert "[^1]" in text          # el de fuera sí se reescribe
        assert "Dentro #1" in text     # el de dentro se preserva
        assert 1 in used

    def test_no_markers_returns_text_unchanged(self) -> None:
        reg = CitationRegistry()
        original = "Texto sin ningún marcador."
        text, used = rewrite_markers(original, reg)
        assert text == original
        assert used == set()

    def test_empty_registry_keeps_markers(self) -> None:
        reg = CitationRegistry()
        text, used = rewrite_markers("Referencia #1 en registry vacío.", reg)
        assert "#1" in text
        assert used == set()


# ---------------------------------------------------------------------------
# render_footnote_block
# ---------------------------------------------------------------------------


class TestRenderFootnoteBlock:
    def test_renders_used_footnotes(self) -> None:
        reg = CitationRegistry()
        reg.register(_ref("docs/adr.md", 10, 20, ["Contexto"]))
        reg.register(_ref("docs/b.md", 1, 3))
        block = render_footnote_block(reg, {1, 2})
        assert "[^1]:" in block
        assert "[^2]:" in block
        assert "docs/adr.md" in block
        assert "líneas 10–20" in block
        assert "Contexto" in block

    def test_renders_only_used_indices(self) -> None:
        reg = CitationRegistry()
        reg.register(_ref("a.md", 1, 1))
        reg.register(_ref("b.md", 1, 1))
        reg.register(_ref("c.md", 1, 1))
        block = render_footnote_block(reg, {1, 3})  # 2 no se usa
        assert "[^1]:" in block
        assert "[^3]:" in block
        assert "[^2]:" not in block

    def test_empty_used_indices_returns_empty_string(self) -> None:
        reg = CitationRegistry()
        reg.register(_ref("a.md", 1, 5))
        block = render_footnote_block(reg, set())
        assert block == ""

    def test_no_section_path_omits_em_dash(self) -> None:
        reg = CitationRegistry()
        reg.register(_ref("a.md", 1, 5, section=[]))
        block = render_footnote_block(reg, {1})
        assert "—" not in block

    def test_footnotes_ordered_by_index(self) -> None:
        reg = CitationRegistry()
        reg.register(_ref("a.md", 1, 1))
        reg.register(_ref("b.md", 1, 1))
        reg.register(_ref("c.md", 1, 1))
        block = render_footnote_block(reg, {3, 1})
        lines = [line for line in block.splitlines() if line.strip()]
        assert lines[0].startswith("[^1]:")
        assert lines[1].startswith("[^3]:")


# ---------------------------------------------------------------------------
# escape_user_text
# ---------------------------------------------------------------------------


class TestEscapeUserText:
    def test_escapes_footnote_sequences(self) -> None:
        result = escape_user_text("Ver [^1] y [^abc] en el doc.")
        # La función reemplaza `[^` por `\[^` — el backslash es el escape Markdown
        assert r"\[^1]" in result
        assert r"\[^abc]" in result
        # La secuencia original sin backslash ya no aparece sin escapar
        assert result.startswith("Ver \\[^")

    def test_no_footnote_sequences_unchanged(self) -> None:
        text = "Texto normal sin footnotes."
        assert escape_user_text(text) == text

    def test_empty_string(self) -> None:
        assert escape_user_text("") == ""
