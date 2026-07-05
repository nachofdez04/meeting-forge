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

    last_initial_prompt: str | None = None  # captura el prompt recibido (UX-1)

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def transcribe(
        self,
        path: str,
        language: str | None = None,
        vad_filter: bool = False,
        initial_prompt: str | None = None,
    ) -> tuple[object, _FakeInfo]:
        _FakeWhisperModel.last_initial_prompt = initial_prompt
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


class _InfoNoDuration:
    """info sin atributo `duration` (algunos backends no la exponen)."""

    language = "en"


class _ModelNoDuration:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def transcribe(self, *args: object, **kwargs: object) -> tuple[object, _InfoNoDuration]:
        segments = iter([_FakeSegment(0.0, 3.0, "a"), _FakeSegment(3.0, 7.5, "b")])
        return segments, _InfoNoDuration()


class _ModelEmpty:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def transcribe(self, *args: object, **kwargs: object) -> tuple[object, _InfoNoDuration]:
        return iter([]), _InfoNoDuration()


def test_transcribe_falls_back_to_last_segment_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # B4: si info no expone duration, se usa el fin del último segmento.
    monkeypatch.setattr(transcriber, "WhisperModel", _ModelNoDuration)
    audio = tmp_path / "reunion.wav"
    audio.write_bytes(b"\x00")

    result = transcriber.WhisperTranscriber().transcribe(audio)
    assert result.duration_seconds == 7.5


def test_transcribe_empty_audio_zero_duration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(transcriber, "WhisperModel", _ModelEmpty)
    audio = tmp_path / "reunion.wav"
    audio.write_bytes(b"\x00")

    result = transcriber.WhisperTranscriber().transcribe(audio)
    assert result.segments == []
    assert result.duration_seconds == 0.0


def test_transcribe_assigns_speakers_when_diarization_enabled(
    _fake_model: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # M7: con diarización activada, los segmentos reciben speaker por solape (diarize_audio mockeado).
    from meeting_forge.ingestion.diarization import SpeakerTurn

    monkeypatch.setattr(transcriber.settings, "diarization_enabled", True)
    monkeypatch.setattr(
        transcriber,
        "diarize_audio",
        lambda *args, **kwargs: [
            SpeakerTurn(0.0, 2.0, "SPEAKER_00"),
            SpeakerTurn(2.0, 4.0, "SPEAKER_01"),
        ],
    )
    audio = tmp_path / "reunion.wav"
    audio.write_bytes(b"\x00")

    result = transcriber.WhisperTranscriber().transcribe(audio)
    assert result.segments[0].speaker == "SPEAKER_00"
    assert result.segments[1].speaker == "SPEAKER_01"


def test_transcribe_no_speakers_when_diarization_disabled(
    _fake_model: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(transcriber.settings, "diarization_enabled", False)
    audio = tmp_path / "reunion.wav"
    audio.write_bytes(b"\x00")

    result = transcriber.WhisperTranscriber().transcribe(audio)
    assert all(s.speaker is None for s in result.segments)


# ---------------------------------------------------------------------------
# UX-1 · initial_prompt (glosario + vocabulario del run)
# ---------------------------------------------------------------------------


@pytest.fixture
def _clean_prompt_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Aísla settings de prompt/glosario en un data_dir temporal. Devuelve el data_dir."""
    monkeypatch.setattr(transcriber.settings, "whisper_initial_prompt", "")
    monkeypatch.setattr(transcriber.settings, "data_dir", tmp_path / "data")
    return tmp_path / "data"


class TestBuildInitialPrompt:
    def test_nothing_configured_returns_none(self, _clean_prompt_settings: Path) -> None:
        assert transcriber.build_initial_prompt() is None

    def test_combines_setting_glossary_and_extra(
        self, _clean_prompt_settings: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            transcriber.settings, "whisper_initial_prompt", "Reunión técnica de MeetingForge."
        )
        glossary = _clean_prompt_settings / "glossary.txt"
        glossary.parent.mkdir(parents=True, exist_ok=True)
        glossary.write_text("# comentario\nChromaDB\n\nfaster-whisper\n", encoding="utf-8")

        prompt = transcriber.build_initial_prompt("Nacho, RAG")

        assert prompt is not None
        assert "Reunión técnica de MeetingForge." in prompt
        assert "Vocabulario del proyecto: ChromaDB, faster-whisper." in prompt
        assert "Nacho, RAG" in prompt
        assert "# comentario" not in prompt

    def test_truncates_overlong_prompt(
        self, _clean_prompt_settings: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(transcriber.settings, "whisper_initial_prompt", "x" * 5000)
        prompt = transcriber.build_initial_prompt()
        assert prompt is not None
        assert len(prompt) == transcriber._INITIAL_PROMPT_MAX_CHARS


def test_transcribe_passes_initial_prompt_to_model(
    _fake_model: None, _clean_prompt_settings: Path, tmp_path: Path
) -> None:
    audio = tmp_path / "reunion.wav"
    audio.write_bytes(b"\x00")

    transcriber.WhisperTranscriber().transcribe(audio, vocabulary="ChromaDB, Nacho")

    assert _FakeWhisperModel.last_initial_prompt is not None
    assert "ChromaDB, Nacho" in _FakeWhisperModel.last_initial_prompt


def test_transcribe_without_vocabulary_passes_none(
    _fake_model: None, _clean_prompt_settings: Path, tmp_path: Path
) -> None:
    audio = tmp_path / "reunion.wav"
    audio.write_bytes(b"\x00")

    transcriber.WhisperTranscriber().transcribe(audio)

    assert _FakeWhisperModel.last_initial_prompt is None


# ---------------------------------------------------------------------------
# UX-13 · los contenedores de vídeo fuerzan la extracción de audio
# ---------------------------------------------------------------------------


def test_video_forces_audio_extraction(
    _fake_model: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(transcriber.settings, "audio_preprocess_enabled", False)
    calls: list[bool] = []

    def _spy_preprocess(path: Path, *, enabled: bool = False) -> Path:
        calls.append(enabled)
        return path

    monkeypatch.setattr(transcriber, "preprocess_audio", _spy_preprocess)
    video = tmp_path / "reunion.mp4"
    video.write_bytes(b"\x00")

    transcriber.WhisperTranscriber().transcribe(video)

    assert calls == [True], "un .mp4 debe pasar por ffmpeg aunque el preprocesado esté off"


def test_audio_respects_preprocess_setting(
    _fake_model: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(transcriber.settings, "audio_preprocess_enabled", False)
    calls: list[bool] = []

    def _spy_preprocess(path: Path, *, enabled: bool = False) -> Path:
        calls.append(enabled)
        return path

    monkeypatch.setattr(transcriber, "preprocess_audio", _spy_preprocess)
    audio = tmp_path / "reunion.wav"
    audio.write_bytes(b"\x00")

    transcriber.WhisperTranscriber().transcribe(audio)

    assert calls == [False], "un .wav sigue respetando AUDIO_PREPROCESS_ENABLED"
