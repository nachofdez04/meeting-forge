"""Tests de UpdateStrategy: roadmap / doc técnica con diff (F5)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from meeting_forge.analysis.schemas import Decision, MeetingInsights
from meeting_forge.generation.generator import DocumentGenerator
from meeting_forge.generation.schemas import (
    DocumentKind,
    GeneratedDocument,
    GenerationMode,
    MeetingMetadata,
)
from meeting_forge.generation.update_strategy import UpdateStrategy


def _insights() -> MeetingInsights:
    return MeetingInsights(
        decisions=[Decision(title="Adoptar Postgres", description="Migrar de SQLite a Postgres.")],
        summary="Reunión de planificación.",
        topics=["base de datos"],
    )


def _metadata() -> MeetingMetadata:
    return MeetingMetadata(meeting_id="m1", title="Sprint", date="2026-05-25")


def _provider(text: str) -> MagicMock:
    provider = MagicMock()
    provider.complete.return_value = text
    return provider


class TestUpdateStrategy:
    def test_creates_new_roadmap_without_diff(self) -> None:
        strategy = UpdateStrategy(provider=_provider("# Roadmap\n\n- Migrar a Postgres\n"))
        doc = strategy.generate(_insights(), _metadata(), kind=DocumentKind.ROADMAP)
        assert doc.kind == DocumentKind.ROADMAP
        assert doc.mode == GenerationMode.ROADMAP_UPDATE
        assert doc.filename == "roadmap.md"
        assert "Postgres" in doc.markdown_content
        assert doc.diff is None  # sin documento existente → sin diff

    def test_update_existing_produces_diff(self) -> None:
        existing = "# Roadmap\n\n- Seguir con SQLite\n"
        revised = "# Roadmap\n\n- Migrar a Postgres\n"
        strategy = UpdateStrategy(provider=_provider(revised))
        doc = strategy.generate(
            _insights(), _metadata(), kind=DocumentKind.ROADMAP, existing_content=existing
        )
        assert doc.diff is not None
        assert "Postgres" in doc.diff
        assert "SQLite" in doc.diff

    def test_strips_bare_markdown_fences(self) -> None:
        strategy = UpdateStrategy(provider=_provider("```\n# Doc\n\ncuerpo\n```"))
        doc = strategy.generate(_insights(), _metadata(), kind=DocumentKind.TECHNICAL_DOC)
        assert doc.markdown_content.startswith("# Doc")
        assert "```" not in doc.markdown_content

    def test_unsupported_kind_raises(self) -> None:
        strategy = UpdateStrategy(provider=_provider("x"))
        with pytest.raises(ValueError, match="no soporta"):
            strategy.generate(_insights(), _metadata(), kind=DocumentKind.ADR)


class TestGeneratorUpdateRouting:
    def test_roadmap_and_tech_doc_modes(self) -> None:
        provider = _provider("# Documento\n\ncontenido generado\n")
        gen = DocumentGenerator(provider=provider)
        docs = gen.generate(
            _insights(),
            _metadata(),
            modes=[GenerationMode.ROADMAP_UPDATE, GenerationMode.TECHNICAL_DOC_UPDATE],
        )
        assert {d.kind for d in docs} == {DocumentKind.ROADMAP, DocumentKind.TECHNICAL_DOC}

    def test_existing_docs_threaded_for_diff(self) -> None:
        provider = _provider("# Roadmap\n\n- nuevo plan\n")
        gen = DocumentGenerator(provider=provider)
        docs = gen.generate(
            _insights(),
            _metadata(),
            modes=[GenerationMode.ROADMAP_UPDATE],
            existing_docs={DocumentKind.ROADMAP: "# Roadmap\n\n- plan viejo\n"},
        )
        assert len(docs) == 1
        assert docs[0].diff is not None
        assert "nuevo plan" in docs[0].diff


class TestWriteToWithDiff:
    def test_writes_md_and_diff_sibling(self, tmp_path: Path) -> None:
        doc = GeneratedDocument(
            filename="roadmap.md",
            kind=DocumentKind.ROADMAP,
            mode=GenerationMode.ROADMAP_UPDATE,
            markdown_content="# Roadmap\n",
            diff="--- a/roadmap.md\n+++ b/roadmap.md\n+nuevo\n",
        )
        path = doc.write_to(tmp_path)
        assert path.read_text(encoding="utf-8") == "# Roadmap\n"
        diff_text = (tmp_path / "roadmap.md.diff").read_text(encoding="utf-8")
        assert diff_text.startswith("--- a/roadmap.md")

    def test_no_diff_file_when_diff_none(self, tmp_path: Path) -> None:
        doc = GeneratedDocument(
            filename="acta.md",
            kind=DocumentKind.ACTA,
            mode=GenerationMode.ACTA,
            markdown_content="# Acta\n",
        )
        doc.write_to(tmp_path)
        assert not (tmp_path / "acta.md.diff").exists()
