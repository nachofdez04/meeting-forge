"""Tests de la utilidad de diff Markdown (F5)."""

from __future__ import annotations

from meeting_forge.generation.diffing import unified_md_diff


class TestUnifiedMdDiff:
    def test_identical_returns_empty(self) -> None:
        assert unified_md_diff("a\nb\n", "a\nb\n") == ""

    def test_shows_added_and_removed_lines(self) -> None:
        diff = unified_md_diff("linea uno\nlinea dos\n", "linea uno\nlinea tres\n", "roadmap.md")
        assert "a/roadmap.md" in diff
        assert "b/roadmap.md" in diff
        assert "-linea dos" in diff
        assert "+linea tres" in diff

    def test_creation_from_empty(self) -> None:
        diff = unified_md_diff("", "nuevo contenido\n")
        assert "+nuevo contenido" in diff
