"""Tests del transcriptor Whisper con un modelo falso (TD10, sin descargar modelos ni audio)."""

from __future__ import annotations

from pathlib import Path

import pytest

from meeting_forge.ingestion import transcriber


class _FakeSegment:
    def __init__(self, start: float, end: float, text: str) -> None:
        self.start = start
        self.end = end
        self.text = text


class _FakeInfo:
    duration = 12.5
    language = "es"


class _FakeWhisperModel:
    """Sustituye a faster_whisper.WhisperModel: no carga nada, devuelve segmentos fijos."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def transcribe(
        self, path: str, language: str | None = None, vad_filter: bool = False
    ) -> tuple[object, _FakeInfo]:
        segments = iter(
            [
                _FakeSegment(0.0, 2.0, "  Hola  "),
                _FakeSegment(2.0, 4.0, "mundo"),
            ]
        )
        return segments, _FakeInfo()


@pytest.fixture
def _fake_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcriber, "WhisperModel", _FakeWhisperModel)


def test_transcribe_maps_segments(_fake_model: None, tmp_path: Path) -> None:
    audio = tmp_path / "reunion.wav"
    audio.write_bytes(b"\x00")

    result = transcriber.WhisperTranscriber().transcribe(audio)

    assert len(result.segments) == 2
    assert result.segments[0].text == "Hola"  # se hace strip del texto
    assert result.segments[1].text == "mundo"
    assert result.segments[0].speaker is None


def test_transcribe_uses_info_duration_and_language(_fake_model: None, tmp_path: Path) -> None:
    audio = tmp_path / "reunion.wav"
    audio.write_bytes(b"\x00")

    result = transcriber.WhisperTranscriber().transcribe(audio)

    assert result.duration_seconds == 12.5
    assert result.language == "es"
