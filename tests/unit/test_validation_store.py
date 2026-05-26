"""Tests unitarios del módulo validation/store.py."""

from __future__ import annotations

from pathlib import Path

from meeting_forge.ui.loader import GeneratedDocView
from meeting_forge.validation import store as val_store
from meeting_forge.validation.schemas import MeetingValidationState, ValidationStatus


def _doc(filename: str, kind: str = "adr") -> GeneratedDocView:
    return GeneratedDocView(filename=filename, kind=kind, markdown_content=f"# {filename}")


class TestLoadSave:
    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        state = val_store.load_state(tmp_path)
        assert state.records == {}

    def test_save_and_reload(self, tmp_path: Path) -> None:
        state = MeetingValidationState()
        state.records["foo.md"] = val_store.mark_approved(state, "foo.md").records["foo.md"]
        val_store.save_state(tmp_path, state)
        loaded = val_store.load_state(tmp_path)
        assert "foo.md" in loaded.records
        assert loaded.records["foo.md"].status == ValidationStatus.APPROVED

    def test_save_atomic_via_tmp(self, tmp_path: Path) -> None:
        state = MeetingValidationState()
        val_store.save_state(tmp_path, state)
        # No deben quedar archivos .tmp
        tmp_files = list(tmp_path.glob(".validation_*.tmp"))
        assert tmp_files == []

    def test_load_corrupt_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "validation.json").write_text("not json", encoding="utf-8")
        state = val_store.load_state(tmp_path)
        assert state.records == {}


class TestInitializePending:
    def test_creates_pending_records(self, tmp_path: Path) -> None:
        docs = [_doc("adr-0001.md"), _doc("acta.md", "acta")]
        state = val_store.initialize_pending(tmp_path, docs)
        assert len(state.records) == 2
        for rec in state.records.values():
            assert rec.status == ValidationStatus.PENDING

    def test_idempotent(self, tmp_path: Path) -> None:
        docs = [_doc("adr-0001.md")]
        val_store.initialize_pending(tmp_path, docs)
        val_store.initialize_pending(tmp_path, docs)
        state = val_store.load_state(tmp_path)
        assert len(state.records) == 1

    def test_does_not_overwrite_existing(self, tmp_path: Path) -> None:
        docs = [_doc("adr-0001.md")]
        state = val_store.initialize_pending(tmp_path, docs)
        state = val_store.mark_approved(state, "adr-0001.md")
        val_store.save_state(tmp_path, state)
        val_store.initialize_pending(tmp_path, docs)
        reloaded = val_store.load_state(tmp_path)
        assert reloaded.records["adr-0001.md"].status == ValidationStatus.APPROVED


class TestMutations:
    def test_mark_approved(self) -> None:
        state = MeetingValidationState()
        state.records["f.md"] = val_store.mark_approved(
            MeetingValidationState(), "f.md"
        ).records["f.md"]
        assert state.records["f.md"].status == ValidationStatus.APPROVED
        assert state.records["f.md"].edited_content is None
        assert state.records["f.md"].validated_at is not None

    def test_mark_approved_with_edit(self) -> None:
        state = MeetingValidationState()
        state = val_store.mark_approved(state, "f.md", edited_content="# editado")
        rec = state.records["f.md"]
        assert rec.status == ValidationStatus.EDITED
        assert rec.edited_content == "# editado"

    def test_mark_rejected(self) -> None:
        state = MeetingValidationState()
        state = val_store.mark_rejected(state, "f.md", reason="No cumple estándares")
        rec = state.records["f.md"]
        assert rec.status == ValidationStatus.REJECTED
        assert rec.rejection_reason == "No cumple estándares"
        assert rec.edited_content is None

    def test_reset_record(self) -> None:
        state = MeetingValidationState()
        state = val_store.mark_approved(state, "f.md")
        state = val_store.reset_record(state, "f.md")
        rec = state.records["f.md"]
        assert rec.status == ValidationStatus.PENDING
        assert rec.validated_at is None

    def test_get_effective_content_returns_edit(self) -> None:
        state = MeetingValidationState()
        state = val_store.mark_approved(state, "f.md", edited_content="# edit")
        result = val_store.get_effective_content(state, "f.md", "# original")
        assert result == "# edit"

    def test_get_effective_content_fallback(self) -> None:
        state = MeetingValidationState()
        result = val_store.get_effective_content(state, "missing.md", "# original")
        assert result == "# original"


class TestCounters:
    def test_counts(self) -> None:
        state = MeetingValidationState()
        docs = [_doc(f"{i}.md") for i in range(4)]
        state = val_store.initialize_pending(Path("."), docs)
        state = val_store.mark_approved(state, "0.md")
        state = val_store.mark_approved(state, "1.md", edited_content="x")
        state = val_store.mark_rejected(state, "2.md")
        assert state.approved_count() == 2
        assert state.rejected_count() == 1
        assert state.pending_count() == 1
        assert len(state.approved_records()) == 2
