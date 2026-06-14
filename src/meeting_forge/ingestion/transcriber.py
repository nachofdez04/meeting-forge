"""Transcriptor de audio usando faster-whisper."""

from pathlib import Path

from faster_whisper import WhisperModel
from loguru import logger

from ..config import settings
from .preprocessor import preprocess_audio
from .schemas import Transcript, TranscriptSegment


class WhisperTranscriber:
    """Wrapper sobre faster-whisper para transcripción de audio."""

    def __init__(self) -> None:
        """Inicializa el modelo Whisper según la configuración."""
        logger.info(
            "Cargando modelo Whisper: size={size}, device={device}, compute={compute}",
            size=settings.whisper_model_size,
            device=settings.whisper_device,
            compute=settings.whisper_compute_type,
        )
        self.model = WhisperModel(
            settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        logger.info("Modelo Whisper cargado correctamente")

    def transcribe(self, audio_path: Path) -> Transcript:
        """Transcribe un archivo de audio.

        Args:
            audio_path: Ruta al archivo de audio.

        Returns:
            Transcript con los segmentos transcritos.
        """
        # F9: preprocesado opcional (mono + 16 kHz + loudnorm) si está habilitado y hay ffmpeg.
        audio_path = preprocess_audio(audio_path, enabled=settings.audio_preprocess_enabled)
        logger.info("Transcribiendo: {path}", path=audio_path)

        segments_raw, info = self.model.transcribe(
            str(audio_path),
            language=settings.whisper_language,
            vad_filter=True,
        )

        segments = [
            TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
                speaker=None,
            )
            for seg in segments_raw
        ]

        # faster-whisper expone la duración real del audio en `info.duration`;
        # el fin del último segmento puede quedar corto si hay silencio final.
        duration = getattr(info, "duration", None) or (segments[-1].end if segments else 0.0)

        logger.info(
            "Transcripción completada: {n} segmentos, {d:.1f}s",
            n=len(segments),
            d=duration,
        )

        return Transcript(
            segments=segments,
            duration_seconds=duration,
            language=info.language,
        )
