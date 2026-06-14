"""Tests de helpers puros del servicio de pipeline (F4)."""

from __future__ import annotations

from pathlib import Path

from meeting_forge.generation import GenerationMode
from meeting_forge.pipeline import audio_date, parse_modes


class TestParseModes:
    def test_valid_modes(self) -> None:
        assert parse_modes("acta,adr-per-decision") == [
            GenerationMode.ACTA,
            GenerationMode.ADR_PER_DECISION,
        ]

    def test_ignores_invalid_and_blank(self) -> None:
        assert parse_modes("acta, , bogus") == [GenerationMode.ACTA]

    def test_empty_string_returns_empty(self) -> None:
        assert parse_modes("") == []


class TestAudioDate:
    def test_returns_iso_date(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"x")
        date = audio_date(audio)
        assert len(date) == 10
        assert date[4] == "-" and date[7] == "-"

    def test_missing_file_falls_back_to_today(self, tmp_path: Path) -> None:
        date = audio_date(tmp_path / "nope.wav")
        assert len(date) == 10
