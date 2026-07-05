"""Tests de la diarización opcional (M7): asignación por solape + tolerancia a fallos."""

from __future__ import annotations

from pathlib import Path

import pytest

from meeting_forge.ingestion import diarization
from meeting_forge.ingestion.diarization import (
    SpeakerTurn,
    assign_speakers,
    diarize_audio,
)
from meeting_forge.ingestion.schemas import TranscriptSegment


def _seg(start: float, end: float) -> TranscriptSegment:
    return TranscriptSegment(start=start, end=end, text="x", speaker=None)


class TestAssignSpeakers:
    def test_assigns_by_max_overlap(self) -> None:
        segments = [_seg(0.0, 2.0), _seg(2.0, 4.0)]
        turns = [
            SpeakerTurn(start=0.0, end=2.1, speaker="SPEAKER_00"),
            SpeakerTurn(start=2.1, end=4.0, speaker="SPEAKER_01"),
        ]
        assigned = assign_speakers(segments, turns)
        assert assigned == 2
        assert segments[0].speaker == "SPEAKER_00"
        assert segments[1].speaker == "SPEAKER_01"

    def test_segment_without_overlap_stays_none(self) -> None:
        segments = [_seg(10.0, 12.0)]
        turns = [SpeakerTurn(start=0.0, end=2.0, speaker="SPEAKER_00")]
        assert assign_speakers(segments, turns) == 0
        assert segments[0].speaker is None

    def test_empty_turns_returns_zero(self) -> None:
        segments = [_seg(0.0, 2.0)]
        assert assign_speakers(segments, []) == 0
        assert segments[0].speaker is None

    def test_picks_turn_with_largest_overlap(self) -> None:
        # El segmento solapa más con SPEAKER_01 (1.5s) que con SPEAKER_00 (0.5s).
        segments = [_seg(1.5, 3.5)]
        turns = [
            SpeakerTurn(start=0.0, end=2.0, speaker="SPEAKER_00"),
            SpeakerTurn(start=2.0, end=4.0, speaker="SPEAKER_01"),
        ]
        assign_speakers(segments, turns)
        assert segments[0].speaker == "SPEAKER_01"


class TestDiarizeAudio:
    def test_disabled_returns_none(self, tmp_path: Path) -> None:
        assert diarize_audio(tmp_path / "a.wav", enabled=False) is None

    def test_pipeline_unavailable_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Passthrough: si el pipeline no carga (dependencia/token/licencia), devuelve None.
        monkeypatch.setattr(diarization, "_load_pipeline", lambda model, hf_token: None)
        assert diarize_audio(tmp_path / "a.wav", enabled=True) is None

    def test_returns_turns_from_pipeline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _FakeSeg:
            def __init__(self, start: float, end: float) -> None:
                self.start = start
                self.end = end

        class _FakeAnnotation:
            def itertracks(self, yield_label: bool = False) -> list[tuple[object, str, str]]:
                return [
                    (_FakeSeg(0.0, 2.0), "_", "SPEAKER_00"),
                    (_FakeSeg(2.0, 4.0), "_", "SPEAKER_01"),
                ]

        class _FakePipeline:
            def __call__(self, _path: str) -> _FakeAnnotation:
                return _FakeAnnotation()

        monkeypatch.setattr(diarization, "_load_pipeline", lambda model, hf_token: _FakePipeline())
        turns = diarize_audio(tmp_path / "a.wav", enabled=True)
        assert turns is not None
        assert [t.speaker for t in turns] == ["SPEAKER_00", "SPEAKER_01"]
        assert turns[0].start == 0.0 and turns[1].end == 4.0
