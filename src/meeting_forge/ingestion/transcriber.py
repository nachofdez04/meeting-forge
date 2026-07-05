"""Transcriptor de audio usando faster-whisper."""

from pathlib import Path

from faster_whisper import WhisperModel
from loguru import logger

from ..config import settings
from .diarization import assign_speakers, diarize_audio
from .preprocessor import needs_audio_extraction, preprocess_audio
from .schemas import Transcript, TranscriptSegment

# Tope defensivo del initial_prompt (Whisper solo condiciona con ~224 tokens; más allá es ruido).
_INITIAL_PROMPT_MAX_CHARS = 1000


def build_initial_prompt(extra_vocabulary: str = "") -> str | None:
    """Construye el `initial_prompt` de Whisper con el vocabulario del proyecto (UX-1).

    Combina, en este orden: `WHISPER_INITIAL_PROMPT` (settings), el glosario opcional
    `data/glossary.txt` (un término por línea; `#` comenta) y el vocabulario puntual del run
    (campo de la UI / `--vocabulary` del CLI). Devuelve None si no hay nada configurado
    (comportamiento actual de Whisper, sin condicionar).
    """
    parts: list[str] = []
    if settings.whisper_initial_prompt.strip():
        parts.append(settings.whisper_initial_prompt.strip())

    glossary = settings.data_dir / "glossary.txt"
    if glossary.exists():
        try:
            terms = [
                line.strip()
                for line in glossary.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        except OSError as exc:
            logger.warning("No se pudo leer el glosario {p}: {e}", p=glossary, e=exc)
            terms = []
        if terms:
            parts.append("Vocabulario del proyecto: " + ", ".join(terms) + ".")

    if extra_vocabulary.strip():
        parts.append(extra_vocabulary.strip())

    if not parts:
        return None
    prompt = "\n".join(parts)
    if len(prompt) > _INITIAL_PROMPT_MAX_CHARS:
        logger.warning(
            "initial_prompt de Whisper truncado a {n} caracteres (era {m})",
            n=_INITIAL_PROMPT_MAX_CHARS,
            m=len(prompt),
        )
        prompt = prompt[:_INITIAL_PROMPT_MAX_CHARS]
    return prompt


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

    def transcribe(self, audio_path: Path, vocabulary: str = "") -> Transcript:
        """Transcribe un archivo de audio (o la pista de audio de un vídeo · UX-13).

        Args:
            audio_path: Ruta al archivo de audio o vídeo.
            vocabulary: Vocabulario puntual de este run para guiar a Whisper (UX-1),
                además del configurado en settings/glosario.

        Returns:
            Transcript con los segmentos transcritos.
        """
        # F9: preprocesado opcional (mono + 16 kHz + loudnorm) si está habilitado y hay ffmpeg.
        # UX-13: para contenedores de vídeo se fuerza (extrae la pista de audio a WAV); si ffmpeg
        # no está, se hace passthrough y faster-whisper intenta decodificar el contenedor.
        force_extract = needs_audio_extraction(audio_path)
        audio_path = preprocess_audio(
            audio_path, enabled=settings.audio_preprocess_enabled or force_extract
        )
        logger.info("Transcribiendo: {path}", path=audio_path)

        initial_prompt = build_initial_prompt(vocabulary)
        if initial_prompt:
            logger.debug("initial_prompt de Whisper: {n} caracteres", n=len(initial_prompt))

        segments_raw, info = self.model.transcribe(
            str(audio_path),
            language=settings.whisper_language,
            vad_filter=True,
            initial_prompt=initial_prompt,
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

        # M7: diarización opcional (asignar speaker por solape temporal). Tolerante a fallos: si
        # está desactivada o algo falla, los segmentos quedan con speaker=None (passthrough).
        if settings.diarization_enabled and segments:
            turns = diarize_audio(
                audio_path,
                enabled=True,
                hf_token=settings.huggingface_token,
                model=settings.diarization_model,
            )
            if turns:
                n_assigned = assign_speakers(segments, turns)
                logger.info("Speakers asignados a {n}/{t} segmentos", n=n_assigned, t=len(segments))

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
