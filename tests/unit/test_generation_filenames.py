"""Tests del módulo generation/filenames.py."""

from __future__ import annotations

import pytest

from meeting_forge.generation.filenames import (
    build_adr_filename,
    build_acta_filename,
    build_consolidated_adr_filename,
    slug,
)
from meeting_forge.generation.schemas import MeetingMetadata


# ---------------------------------------------------------------------------
# slug()
# ---------------------------------------------------------------------------


class TestSlug:
    def test_basic_ascii(self) -> None:
        assert slug("Adoptar ChromaDB") == "adoptar-chromadb"

    def test_strips_backticks_and_brackets(self) -> None:
        assert slug("Usar `eval()` para [tests]") == "usar-eval-para-tests"

    def test_unicode_normalization(self) -> None:
        assert slug("Diseño de API") == "diseno-de-api"
        assert slug("Decisión final") == "decision-final"
        assert slug("Revisión · Aprobación") == "revision-aprobacion"

    def test_strips_parentheses_and_angles(self) -> None:
        assert slug("Fase <2> (generación)") == "fase-2-generacion"

    def test_max_length_truncates_at_word_boundary(self) -> None:
        long = "palabra " * 20  # 160 chars
        result = slug(long, max_length=60)
        assert len(result) <= 60
        assert not result.endswith("-")

    def test_empty_string_returns_untitled(self) -> None:
        assert slug("") == "untitled"
        assert slug("   ") == "untitled"

    def test_only_special_chars_returns_untitled(self) -> None:
        assert slug("[`<>{}]") == "untitled"

    def test_collapses_multiple_spaces_and_dashes(self) -> None:
        assert slug("uno  dos---tres") == "uno-dos-tres"

    def test_numbers_preserved(self) -> None:
        assert slug("Fase 2 de 4") == "fase-2-de-4"

    def test_no_leading_or_trailing_dashes(self) -> None:
        result = slug("  -hola-  ")
        assert not result.startswith("-")
        assert not result.endswith("-")


# ---------------------------------------------------------------------------
# build_adr_filename()
# ---------------------------------------------------------------------------


class TestBuildAdrFilename:
    def test_zero_padded_counter(self) -> None:
        name = build_adr_filename("Adoptar ChromaDB", 1)
        assert name.startswith("adr-0001-")

    def test_counter_99_pads_to_4_digits(self) -> None:
        name = build_adr_filename("Algo", 99)
        assert name.startswith("adr-0099-")

    def test_counter_10000_uses_5_digits(self) -> None:
        name = build_adr_filename("Algo", 10000)
        assert name.startswith("adr-10000-")

    def test_title_is_slugified(self) -> None:
        name = build_adr_filename("Usar `eval()` para [algo]", 3)
        assert "`" not in name
        assert "[" not in name

    def test_ends_with_md(self) -> None:
        assert build_adr_filename("Título", 1).endswith(".md")


# ---------------------------------------------------------------------------
# build_consolidated_adr_filename()
# ---------------------------------------------------------------------------


class TestBuildConsolidatedAdrFilename:
    def _meta(self, meeting_id: str) -> MeetingMetadata:
        return MeetingMetadata(meeting_id=meeting_id)

    def test_basic(self) -> None:
        name = build_consolidated_adr_filename(self._meta("sprint-planning"))
        assert name == "adr-sprint-planning-consolidated.md"

    def test_meeting_id_slugified(self) -> None:
        name = build_consolidated_adr_filename(self._meta("Sprint Planning 2026"))
        assert " " not in name
        assert name.endswith("-consolidated.md")

    def test_ends_with_md(self) -> None:
        assert build_consolidated_adr_filename(self._meta("foo")).endswith(".md")


# ---------------------------------------------------------------------------
# build_acta_filename()
# ---------------------------------------------------------------------------


class TestBuildActaFilename:
    def _meta(
        self, meeting_id: str, date: str | None = None
    ) -> MeetingMetadata:
        return MeetingMetadata(meeting_id=meeting_id, date=date)

    def test_with_date(self) -> None:
        name = build_acta_filename(self._meta("planning", date="2026-05-25"))
        assert name == "acta-2026-05-25-planning.md"

    def test_without_date_omits_date_prefix(self) -> None:
        name = build_acta_filename(self._meta("planning", date=None))
        assert name == "acta-planning.md"

    def test_meeting_id_slugified(self) -> None:
        name = build_acta_filename(self._meta("Sprint Review Q2", date="2026-05-25"))
        assert " " not in name
        assert name.startswith("acta-2026-05-25-")

    def test_ends_with_md(self) -> None:
        assert build_acta_filename(self._meta("x")).endswith(".md")
