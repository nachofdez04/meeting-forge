"""Test de integración end-to-end del pipeline.

Marcado como skipped por defecto: requiere modelos Whisper descargados,
ffmpeg instalado, API keys reales y un audio de prueba en
``tests/fixtures/sample.wav``. Habilítalo manualmente cuando esas piezas
estén presentes.
"""

import os
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.wav"


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION"),
    reason="Requires audio fixture, ffmpeg, API keys and Whisper model (set RUN_INTEGRATION=1)",
)
def test_e2e_pipeline() -> None:
    """Pipeline completo: audio → transcript → insights."""
    from meeting_forge.analysis.extractor import InsightsExtractor
    from meeting_forge.ingestion.transcriber import WhisperTranscriber

    transcriber = WhisperTranscriber()
    transcript = transcriber.transcribe(FIXTURE)
    assert transcript.duration_seconds > 0
    assert len(transcript.segments) > 0

    extractor = InsightsExtractor()
    insights = extractor.extract(transcript)
    assert insights is not None
