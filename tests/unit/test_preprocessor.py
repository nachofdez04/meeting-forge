"""Tests del preprocesado opcional de audio (F9)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from meeting_forge.ingestion.preprocessor import needs_audio_extraction, preprocess_audio


def _audio(tmp_path: Path) -> Path:
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFFdummy")
    return audio


def test_needs_audio_extraction_for_video_containers() -> None:
    # UX-13: los contenedores de vídeo (Meet/Teams/Zoom) fuerzan la extracción de audio.
    assert needs_audio_extraction(Path("reunion.mp4")) is True
    assert needs_audio_extraction(Path("reunion.MKV")) is True
    assert needs_audio_extraction(Path("reunion.webm")) is True
    assert needs_audio_extraction(Path("reunion.wav")) is False
    assert needs_audio_extraction(Path("reunion.mp3")) is False


def test_disabled_returns_original(tmp_path: Path) -> None:
    audio = _audio(tmp_path)
    assert preprocess_audio(audio, enabled=False) == audio


def test_no_ffmpeg_returns_original(tmp_path: Path) -> None:
    audio = _audio(tmp_path)
    with patch("shutil.which", return_value=None):
        assert preprocess_audio(audio, enabled=True) == audio


def test_ffmpeg_failure_returns_original(tmp_path: Path) -> None:
    audio = _audio(tmp_path)
    fake = SimpleNamespace(returncode=1, stderr="boom", stdout="")
    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("subprocess.run", return_value=fake),
    ):
        assert preprocess_audio(audio, enabled=True) == audio


def test_ffmpeg_success_returns_output(tmp_path: Path) -> None:
    audio = _audio(tmp_path)
    out = audio.with_name("a_pre16k.wav")

    def _fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        out.write_bytes(b"RIFFconverted")  # simula que ffmpeg crea el output
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("subprocess.run", side_effect=_fake_run),
    ):
        result = preprocess_audio(audio, enabled=True)
    assert result == out
    assert result.exists()
