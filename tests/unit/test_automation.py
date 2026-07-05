"""Tests del modo automático opcional (F8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from meeting_forge import automation
from meeting_forge.automation import run_auto_mode
from meeting_forge.generation.schemas import (
    DocumentKind,
    GeneratedDocument,
    GeneratedDocView,
    GenerationMode,
    MeetingMetadata,
)
from meeting_forge.validation import store
from meeting_forge.validation.schemas import ValidationStatus


def _doc(filename: str, kind: DocumentKind, mode: GenerationMode) -> GeneratedDocument:
    return GeneratedDocument(filename=filename, kind=kind, mode=mode, markdown_content="# X\n")


def _metadata() -> MeetingMetadata:
    return MeetingMetadata(meeting_id="m1", title="M", date="2026-05-25", source_audio=None)


class TestRunAutoMode:
    def test_disabled_is_noop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(automation.settings, "auto_approve_enabled", False)
        docs = [_doc("acta.md", DocumentKind.ACTA, GenerationMode.ACTA)]
        result = run_auto_mode(tmp_path, docs, _metadata())
        assert result.auto_approved == []

    def test_auto_approves_allowed_kinds_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(automation.settings, "auto_approve_enabled", True)
        monkeypatch.setattr(automation.settings, "auto_approve_kinds", ["acta"])
        monkeypatch.setattr(automation.settings, "auto_publish_enabled", False)

        docs = [
            _doc("acta.md", DocumentKind.ACTA, GenerationMode.ACTA),
            _doc("adr-0001.md", DocumentKind.ADR, GenerationMode.ADR_PER_DECISION),
        ]
        result = run_auto_mode(tmp_path, docs, _metadata())

        assert result.auto_approved == ["acta.md"]
        assert result.published is False
        # Persistido en validation.json: solo el acta aprobada (y marcada como auto).
        state = store.load_state(tmp_path)
        assert state.records["acta.md"].status == ValidationStatus.APPROVED
        assert state.records["acta.md"].auto_approved is True
        assert state.records["adr-0001.md"].status == ValidationStatus.PENDING


class TestAutoPublishNothingToPublish:
    def test_nothing_to_publish_is_benign(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # NothingToPublishError (contenido ya publicado) no debe tratarse como fallo:
        # el modo automático termina sin lanzar y sin marcar published.
        from meeting_forge.git_integration import publisher

        monkeypatch.setattr(automation.settings, "auto_approve_enabled", True)
        monkeypatch.setattr(automation.settings, "auto_approve_kinds", ["acta"])
        monkeypatch.setattr(automation.settings, "auto_publish_enabled", True)
        monkeypatch.setattr(automation.settings, "git_integration_enabled", True)

        def _boom(*args: object, **kwargs: object) -> None:
            raise publisher.NothingToPublishError("ya coincide")

        monkeypatch.setattr(publisher, "publish_meeting", _boom)

        docs = [_doc("acta.md", DocumentKind.ACTA, GenerationMode.ACTA)]
        result = run_auto_mode(tmp_path, docs, _metadata())

        assert result.auto_approved == ["acta.md"]
        assert result.published is False
        assert result.pr_url == ""


class TestAutoApproveStore:
    def test_marks_only_allowed_kinds(self, tmp_path: Path) -> None:
        docs = [
            GeneratedDocView("acta.md", "acta", "x"),
            GeneratedDocView("adr.md", "adr", "y"),
        ]
        state = store.initialize_pending(tmp_path, docs)
        approved = store.auto_approve(state, docs, ["acta"])
        assert approved == ["acta.md"]
        assert state.records["acta.md"].status == ValidationStatus.APPROVED
        assert state.records["acta.md"].auto_approved is True
        assert state.records["adr.md"].status == ValidationStatus.PENDING
