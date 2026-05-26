"""Tests del módulo ui/loader.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meeting_forge.ui.loader import (
    GeneratedDocView,
    MeetingData,
    list_meetings,
    load_generated_docs,
    load_meeting,
)

_FIXTURES = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write_result(meeting_dir: Path, result: dict[str, object]) -> Path:
    meeting_dir.mkdir(parents=True, exist_ok=True)
    path = meeting_dir / f"{meeting_dir.name}_result.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    return path


def _minimal_result(n_decisions: int = 1, n_actions: int = 0) -> dict[str, object]:
    return {
        "audio_file": "data/raw/test.wav",
        "transcript": {"segments": [], "duration_seconds": 0.0, "language": "es"},
        "insights": {
            "decisions": [
                {
                    "title": f"Decision {i}",
                    "description": "desc",
                    "rationale": None,
                    "owners": [],
                    "tags": [],
                    "sources": [],
                }
                for i in range(n_decisions)
            ],
            "action_items": [
                {
                    "description": f"Action {i}",
                    "assignee": None,
                    "deadline": None,
                    "sources": [],
                }
                for i in range(n_actions)
            ],
            "topics": [],
            "summary": "",
        },
        "metadata": {"provider": "anthropic", "whisper_model": "base", "rag_enabled": False},
        "generated_documents": [],
    }


# ---------------------------------------------------------------------------
# list_meetings()
# ---------------------------------------------------------------------------


class TestListMeetings:
    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        assert list_meetings(tmp_path) == []

    def test_nonexistent_dir_returns_empty(self, tmp_path: Path) -> None:
        assert list_meetings(tmp_path / "no_existe") == []

    def test_ignores_subdirs_without_result_json(self, tmp_path: Path) -> None:
        (tmp_path / "sin_resultado").mkdir()
        assert list_meetings(tmp_path) == []

    def test_detects_meeting_with_result_json(self, tmp_path: Path) -> None:
        meeting_dir = tmp_path / "mi_reunion"
        _write_result(meeting_dir, _minimal_result())
        summaries = list_meetings(tmp_path)
        assert len(summaries) == 1
        assert summaries[0].meeting_id == "mi_reunion"

    def test_counts_decisions_and_actions(self, tmp_path: Path) -> None:
        meeting_dir = tmp_path / "reunion"
        _write_result(meeting_dir, _minimal_result(n_decisions=3, n_actions=2))
        summary = list_meetings(tmp_path)[0]
        assert summary.n_decisions == 3
        assert summary.n_actions == 2

    def test_has_generated_docs_true_when_adr_subdir_exists(self, tmp_path: Path) -> None:
        meeting_dir = tmp_path / "reunion"
        _write_result(meeting_dir, _minimal_result())
        (meeting_dir / "adr").mkdir()
        summary = list_meetings(tmp_path)[0]
        assert summary.has_generated_docs is True

    def test_has_generated_docs_false_without_subdirs(self, tmp_path: Path) -> None:
        meeting_dir = tmp_path / "reunion"
        _write_result(meeting_dir, _minimal_result())
        summary = list_meetings(tmp_path)[0]
        assert summary.has_generated_docs is False

    def test_sorted_most_recent_first(self, tmp_path: Path) -> None:
        import os

        dir_a = tmp_path / "antigua"
        dir_b = tmp_path / "reciente"
        path_a = _write_result(dir_a, _minimal_result())
        path_b = _write_result(dir_b, _minimal_result())
        # Set explicit timestamps to avoid mtime resolution issues on Windows
        os.utime(path_a, (1_000_000, 1_000_000))
        os.utime(path_b, (2_000_000, 2_000_000))
        summaries = list_meetings(tmp_path)
        assert summaries[0].meeting_id == "reciente"

    def test_ignores_malformed_json(self, tmp_path: Path) -> None:
        meeting_dir = tmp_path / "roto"
        meeting_dir.mkdir()
        (meeting_dir / "roto_result.json").write_text("NOT_JSON", encoding="utf-8")
        assert list_meetings(tmp_path) == []


# ---------------------------------------------------------------------------
# load_meeting()
# ---------------------------------------------------------------------------


class TestLoadMeeting:
    def test_loads_sample_result_fixture(self, tmp_path: Path) -> None:
        fixture = _FIXTURES / "sample_result.json"
        result = json.loads(fixture.read_text(encoding="utf-8"))
        meeting_dir = tmp_path / "test_meeting"
        _write_result(meeting_dir, result)
        data = load_meeting(meeting_dir)
        assert isinstance(data, MeetingData)
        assert data.meeting_id == "test_meeting"
        assert len(data.insights.decisions) == 2
        assert len(data.insights.action_items) == 1
        assert data.metadata.get("provider") == "anthropic"
        assert len(data.transcript_segments) == 3

    def test_raises_when_no_result_json(self, tmp_path: Path) -> None:
        meeting_dir = tmp_path / "vacio"
        meeting_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            load_meeting(meeting_dir)

    def test_segments_are_list_of_dicts(self, tmp_path: Path) -> None:
        meeting_dir = tmp_path / "reunion"
        _write_result(
            meeting_dir,
            {
                **_minimal_result(),
                "transcript": {
                    "segments": [{"start": 0.0, "end": 1.0, "text": "Hola", "speaker": None}]
                },
            },
        )
        data = load_meeting(meeting_dir)
        assert data.transcript_segments[0]["text"] == "Hola"

    def test_empty_transcript_gives_empty_segments(self, tmp_path: Path) -> None:
        meeting_dir = tmp_path / "reunion"
        _write_result(meeting_dir, _minimal_result())
        data = load_meeting(meeting_dir)
        assert data.transcript_segments == []


# ---------------------------------------------------------------------------
# load_generated_docs()
# ---------------------------------------------------------------------------


class TestLoadGeneratedDocs:
    def test_returns_empty_when_no_subdirs(self, tmp_path: Path) -> None:
        assert load_generated_docs(tmp_path) == []

    def test_reads_adr_markdown(self, tmp_path: Path) -> None:
        (tmp_path / "adr").mkdir()
        (tmp_path / "adr" / "adr-0001-test.md").write_text("# ADR", encoding="utf-8")
        docs = load_generated_docs(tmp_path)
        assert len(docs) == 1
        assert docs[0].kind == "adr"
        assert docs[0].filename == "adr-0001-test.md"
        assert docs[0].markdown_content == "# ADR"

    def test_reads_acta_markdown(self, tmp_path: Path) -> None:
        (tmp_path / "acta").mkdir()
        (tmp_path / "acta" / "acta-2026-05-25-reunion.md").write_text("# Acta", encoding="utf-8")
        docs = load_generated_docs(tmp_path)
        assert len(docs) == 1
        assert docs[0].kind == "acta"

    def test_reads_both_adr_and_acta(self, tmp_path: Path) -> None:
        (tmp_path / "adr").mkdir()
        (tmp_path / "acta").mkdir()
        (tmp_path / "adr" / "adr-0001.md").write_text("adr", encoding="utf-8")
        (tmp_path / "acta" / "acta.md").write_text("acta", encoding="utf-8")
        docs = load_generated_docs(tmp_path)
        kinds = {d.kind for d in docs}
        assert kinds == {"adr", "acta"}

    def test_tolerates_missing_adr_subdir(self, tmp_path: Path) -> None:
        (tmp_path / "acta").mkdir()
        (tmp_path / "acta" / "acta.md").write_text("acta", encoding="utf-8")
        docs = load_generated_docs(tmp_path)
        assert len(docs) == 1

    def test_returns_list_of_generated_doc_view(self, tmp_path: Path) -> None:
        (tmp_path / "adr").mkdir()
        (tmp_path / "adr" / "x.md").write_text("content", encoding="utf-8")
        docs = load_generated_docs(tmp_path)
        assert isinstance(docs[0], GeneratedDocView)
