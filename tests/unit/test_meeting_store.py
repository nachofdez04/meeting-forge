"""Tests del almacén de estado por reunión (meeting_store · paso 2 UX-2/UX-3/UX-5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meeting_forge import meeting_store
from meeting_forge.analysis.schemas import Decision, MeetingInsights
from meeting_forge.ingestion.schemas import Transcript, TranscriptSegment


def _transcript_dict() -> dict[str, object]:
    return {
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "hola", "speaker": "SPEAKER_00"},
            {"start": 1.0, "end": 2.0, "text": "mundo", "speaker": None},
        ],
        "duration_seconds": 2.0,
        "language": "es",
    }


def _make_meeting_dir(tmp_path: Path, *, with_transcript_file: bool = True) -> Path:
    meeting_dir = tmp_path / "m1"
    meeting_dir.mkdir()
    result = {
        "audio_file": "m1.wav",
        "transcript": _transcript_dict(),
        "insights": {"decisions": [], "action_items": [], "topics": [], "summary": "inicial"},
        "meeting_metadata": {
            "meeting_id": "m1",
            "title": "Reunión 1",
            "date": "2026-07-01",
            "attendees": [],
            "source_audio": None,
        },
        "generated_documents": [],
    }
    (meeting_dir / "m1_result.json").write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8"
    )
    if with_transcript_file:
        (meeting_dir / "m1_transcript.json").write_text(
            json.dumps(_transcript_dict()), encoding="utf-8"
        )
    return meeting_dir


class TestResultIO:
    def test_find_result_path_missing_raises(self, tmp_path: Path) -> None:
        empty = tmp_path / "vacio"
        empty.mkdir()
        with pytest.raises(FileNotFoundError):
            meeting_store.find_result_path(empty)

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        meeting_dir = _make_meeting_dir(tmp_path)
        result = meeting_store.load_result(meeting_dir)
        result["extra"] = "señal única á"
        meeting_store.save_result(meeting_dir, result)
        assert meeting_store.load_result(meeting_dir)["extra"] == "señal única á"

    def test_save_result_leaves_no_tmp_files(self, tmp_path: Path) -> None:
        meeting_dir = _make_meeting_dir(tmp_path)
        meeting_store.save_result(meeting_dir, meeting_store.load_result(meeting_dir))
        assert not list(meeting_dir.glob(".result_*.tmp"))


class TestTranscriptIO:
    def test_load_prefers_canonical_file(self, tmp_path: Path) -> None:
        meeting_dir = _make_meeting_dir(tmp_path)
        transcript = meeting_store.load_transcript(meeting_dir)
        assert [s.text for s in transcript.segments] == ["hola", "mundo"]

    def test_load_falls_back_to_result_json(self, tmp_path: Path) -> None:
        # Reuniones sin fichero canónico (p.ej. la demo) usan el bloque de result.json.
        meeting_dir = _make_meeting_dir(tmp_path, with_transcript_file=False)
        transcript = meeting_store.load_transcript(meeting_dir)
        assert len(transcript.segments) == 2

    def test_save_updates_both_files(self, tmp_path: Path) -> None:
        meeting_dir = _make_meeting_dir(tmp_path)
        updated = Transcript(
            segments=[TranscriptSegment(start=0.0, end=1.0, text="corregido", speaker=None)],
            duration_seconds=1.0,
            language="es",
        )
        meeting_store.save_transcript(meeting_dir, updated)

        canonical = Transcript.model_validate_json(
            (meeting_dir / "m1_transcript.json").read_text(encoding="utf-8")
        )
        assert canonical.segments[0].text == "corregido"
        result = meeting_store.load_result(meeting_dir)
        transcript_block = result["transcript"]
        assert isinstance(transcript_block, dict)
        assert transcript_block["segments"][0]["text"] == "corregido"


class TestSpeakerNames:
    def test_roundtrip_drops_blank_names(self, tmp_path: Path) -> None:
        meeting_dir = _make_meeting_dir(tmp_path)
        meeting_store.save_speaker_names(meeting_dir, {"SPEAKER_00": " Ana ", "SPEAKER_01": "   "})
        assert meeting_store.load_speaker_names(meeting_dir) == {"SPEAKER_00": "Ana"}

    def test_missing_key_returns_empty(self, tmp_path: Path) -> None:
        meeting_dir = _make_meeting_dir(tmp_path)
        assert meeting_store.load_speaker_names(meeting_dir) == {}


class TestSaveInsights:
    def test_save_marks_edited_flag(self, tmp_path: Path) -> None:
        meeting_dir = _make_meeting_dir(tmp_path)
        insights = MeetingInsights(
            decisions=[Decision(title="Nueva", description="editada a mano")]
        )
        meeting_store.save_insights(meeting_dir, insights)

        result = meeting_store.load_result(meeting_dir)
        assert result["insights_edited"] is True
        insights_block = result["insights"]
        assert isinstance(insights_block, dict)
        assert insights_block["decisions"][0]["title"] == "Nueva"
