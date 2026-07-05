"""Tests de helpers puros del servicio de pipeline (F4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from meeting_forge import pipeline as pipeline_mod
from meeting_forge.generation import GenerationMode
from meeting_forge.ingestion.schemas import Transcript, TranscriptSegment
from meeting_forge.pipeline import (
    audio_date,
    normalize_meeting_date,
    parse_attendees,
    parse_modes,
)


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


class TestNormalizeMeetingDate:
    def test_valid_iso_date_passes_through(self, tmp_path: Path) -> None:
        assert normalize_meeting_date("2026-06-30", tmp_path / "a.wav") == "2026-06-30"

    def test_empty_falls_back_to_audio_date(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"x")
        assert normalize_meeting_date("  ", audio) == audio_date(audio)

    @pytest.mark.parametrize(
        "bad", ["junio 2026", "30/06/2026", "2026-06-30T12:00", "2026-13-40", "2026-6-1"]
    )
    def test_invalid_dates_fall_back(self, bad: str, tmp_path: Path) -> None:
        # La fecha acaba en el filename del acta y en la rama git: nada fuera de YYYY-MM-DD.
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"x")
        assert normalize_meeting_date(bad, audio) == audio_date(audio)


class TestParseAttendees:
    def test_csv_with_spaces_and_empties(self) -> None:
        # UX-4: "Ana, Luis,, Marta " → lista limpia.
        assert parse_attendees("Ana, Luis,, Marta ") == ["Ana", "Luis", "Marta"]

    def test_empty_string_returns_empty_list(self) -> None:
        assert parse_attendees("") == []
        assert parse_attendees("  ,  ") == []


class _FakeTranscriber:
    def transcribe(self, _path: Path, vocabulary: str = "") -> Transcript:
        return Transcript(
            segments=[TranscriptSegment(start=0.0, end=1.0, text="hola", speaker=None)],
            duration_seconds=1.0,
            language="es",
        )


def _make_processed_meeting(tmp_path: Path) -> Path:
    """Crea en disco una reunión ya procesada mínima (result + transcript + validación)."""
    meeting_dir = tmp_path / "m1"
    meeting_dir.mkdir()
    transcript = {
        "segments": [{"start": 0.0, "end": 1.0, "text": "hola", "speaker": "SPEAKER_00"}],
        "duration_seconds": 1.0,
        "language": "es",
    }
    result = {
        "audio_file": "m1.wav",
        "transcript": transcript,
        "insights": {
            "decisions": [{"title": "D1", "description": "original"}],
            "action_items": [],
            "topics": [],
            "summary": "s",
        },
        "meeting_metadata": {
            "meeting_id": "m1",
            "title": "Reunión 1",
            "date": "2026-07-01",
            "attendees": [],
            "source_audio": None,
        },
        "generated_documents": [],
        "speaker_names": {"SPEAKER_00": "Ana"},
    }
    (meeting_dir / "m1_result.json").write_text(json.dumps(result), encoding="utf-8")
    (meeting_dir / "m1_transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
    (meeting_dir / "validation.json").write_text('{"records": {}}', encoding="utf-8")
    return meeting_dir


class _FakeGenerator:
    """DocumentGenerator falso: siempre produce un único acta determinística."""

    def __init__(self, provider: object = None, adr_prompt_version: str = "v1") -> None:
        pass

    def generate(
        self, insights: object, metadata: object, modes: object, existing_docs: object = None
    ) -> list[object]:
        from meeting_forge.generation.schemas import (
            DocumentKind,
            GeneratedDocument,
        )

        return [
            GeneratedDocument(
                filename="acta-regen.md",
                kind=DocumentKind.ACTA,
                mode=GenerationMode.ACTA,
                markdown_content="# Acta regenerada\n",
            )
        ]


class TestRegenerateDocuments:
    def test_regenerates_cleans_stale_and_resets_validation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        meeting_dir = _make_processed_meeting(tmp_path)
        stale = meeting_dir / "acta" / "acta-vieja.md"
        stale.parent.mkdir()
        stale.write_text("# Vieja\n", encoding="utf-8")

        monkeypatch.setattr(pipeline_mod, "get_provider", lambda collector=None: object())
        monkeypatch.setattr(pipeline_mod, "DocumentGenerator", _FakeGenerator)

        res = pipeline_mod.regenerate_documents(meeting_dir, modes=[GenerationMode.ACTA])

        assert (meeting_dir / "acta" / "acta-regen.md").exists()
        assert not stale.exists(), "los documentos huérfanos del run anterior deben limpiarse"
        assert not (meeting_dir / "validation.json").exists(), "la validación debe invalidarse"
        result = json.loads((meeting_dir / "m1_result.json").read_text(encoding="utf-8"))
        assert result["generated_documents"][0]["filename"] == "acta-regen.md"
        assert res.n_documents == 1

    def test_no_valid_modes_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        meeting_dir = _make_processed_meeting(tmp_path)
        monkeypatch.setattr(pipeline_mod, "get_provider", lambda collector=None: object())
        with pytest.raises(ValueError, match="modos"):
            pipeline_mod.regenerate_documents(meeting_dir, modes=[])


class _CapturingExtractor:
    """InsightsExtractor falso que captura el texto del transcript recibido."""

    last_text: str = ""

    def __init__(self, provider: object = None, retriever: object = None) -> None:
        self.last_context: list[object] = []

    def extract(self, transcript: Transcript) -> object:
        from meeting_forge.analysis.schemas import Decision, MeetingInsights

        _CapturingExtractor.last_text = transcript.to_text()
        return MeetingInsights(
            decisions=[Decision(title="Nueva decisión", description="re-extraída")],
            summary="nuevo resumen",
        )


class TestRerunExtraction:
    def test_reextracts_with_speaker_names_and_updates_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        meeting_dir = _make_processed_meeting(tmp_path)
        monkeypatch.setattr(pipeline_mod, "get_provider", lambda collector=None: object())
        monkeypatch.setattr(pipeline_mod, "InsightsExtractor", _CapturingExtractor)

        res = pipeline_mod.rerun_extraction(meeting_dir, use_rag=False, use_generation=False)

        # UX-3: los nombres guardados se aplican al texto que ve el LLM.
        assert "Ana: hola" in _CapturingExtractor.last_text
        result = json.loads((meeting_dir / "m1_result.json").read_text(encoding="utf-8"))
        assert result["insights"]["decisions"][0]["title"] == "Nueva decisión"
        assert result["insights_edited"] is False
        assert not (meeting_dir / "validation.json").exists()
        assert res.n_decisions == 1

    def test_generation_failure_still_persists_new_insights(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        meeting_dir = _make_processed_meeting(tmp_path)
        monkeypatch.setattr(pipeline_mod, "get_provider", lambda collector=None: object())
        monkeypatch.setattr(pipeline_mod, "InsightsExtractor", _CapturingExtractor)

        class _BoomGenerator:
            def __init__(self, provider: object = None, adr_prompt_version: str = "v1") -> None:
                pass

            def generate(self, *args: object, **kwargs: object) -> list[object]:
                raise RuntimeError("generación rota")

        monkeypatch.setattr(pipeline_mod, "DocumentGenerator", _BoomGenerator)

        res = pipeline_mod.rerun_extraction(
            meeting_dir, use_rag=False, use_generation=True, modes=[GenerationMode.ACTA]
        )

        result = json.loads((meeting_dir / "m1_result.json").read_text(encoding="utf-8"))
        assert result["insights"]["decisions"][0]["title"] == "Nueva decisión"
        assert res.n_documents == 0


class _BoomExtractor:
    def __init__(self, provider: object = None, retriever: object = None) -> None:
        self.last_context: list[object] = []

    def extract(self, _transcript: Transcript) -> None:
        raise RuntimeError("LLM boom")


class TestExtractionFailurePersistsPartial:
    def test_partial_result_written_then_reraised(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # BUG-2: si la extracción falla, no se pierde el transcript: se persiste un result.json
        # parcial (transcript + error + telemetría) y luego se propaga el error.
        audio = tmp_path / "m.wav"
        audio.write_bytes(b"x")

        monkeypatch.setattr(pipeline_mod, "WhisperTranscriber", _FakeTranscriber)
        monkeypatch.setattr(pipeline_mod, "InsightsExtractor", _BoomExtractor)
        monkeypatch.setattr(pipeline_mod, "get_provider", lambda collector=None: object())

        out = tmp_path / "out"
        with pytest.raises(RuntimeError, match="LLM boom"):
            pipeline_mod.run_pipeline(audio, output_dir=out, use_rag=False, use_generation=False)

        result_file = out / "m" / "m_result.json"
        assert result_file.exists(), "debe persistirse un result.json parcial"
        data = json.loads(result_file.read_text(encoding="utf-8"))
        assert data["error"]["phase"] == "extraction"
        assert data["transcript"]["segments"][0]["text"] == "hola"
        assert "run_meta" in data
