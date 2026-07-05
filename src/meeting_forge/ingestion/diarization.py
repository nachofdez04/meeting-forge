"""Diarización opcional de hablantes (M7 · amplía F9).

Asigna un identificador de *speaker* a cada segmento de la transcripción usando **pyannote.audio**.
Diseño tolerante a fallos, igual que el preprocesado de audio (F9): la diarización solo se ejecuta
si está habilitada y el modelo carga; ante cualquier problema (dependencia ausente, token de Hugging
Face inválido, licencia no aceptada o fallo del modelo) se hace *passthrough* y la transcripción
continúa **sin speakers**, sin romper el pipeline.

`pyannote.audio` es una dependencia **opcional pesada** (grupo `diarization` en `pyproject.toml`); se
importa de forma perezosa para que el paquete funcione sin ella instalada.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from .schemas import TranscriptSegment

_DEFAULT_MODEL = "pyannote/speaker-diarization-3.1"


@dataclass
class SpeakerTurn:
    """Intervalo temporal atribuido a un hablante por el diarizador."""

    start: float
    end: float
    speaker: str


def assign_speakers(segments: list[TranscriptSegment], turns: list[SpeakerTurn]) -> int:
    """Asigna a cada segmento el speaker con **mayor solape temporal**. Devuelve cuántos asignó.

    Lógica pura y testeable (independiente de pyannote): para cada segmento elige el turno cuyo
    intervalo se solapa más con él; si ningún turno se solapa, deja `speaker` sin tocar (None).
    """
    if not turns:
        return 0
    assigned = 0
    for seg in segments:
        best_label: str | None = None
        best_overlap = 0.0
        for turn in turns:
            overlap = min(seg.end, turn.end) - max(seg.start, turn.start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_label = turn.speaker
        if best_label is not None:
            seg.speaker = best_label
            assigned += 1
    return assigned


def _load_pipeline(model: str, hf_token: str) -> Any:
    """Carga el pipeline de pyannote. Devuelve None si no se puede (dependencia/token/licencia).

    Aislado para poder mockearlo en tests sin instalar pyannote ni descargar modelos.
    """
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        logger.warning(
            "pyannote.audio no está instalado; se omite la diarización. "
            "Instálalo con `uv sync --group diarization` para habilitar speakers."
        )
        return None
    try:
        pipeline = Pipeline.from_pretrained(model, use_auth_token=hf_token or None)
    except Exception as exc:  # pragma: no cover - depende de red/credenciales
        logger.warning("No se pudo cargar el modelo de diarización '{m}': {e}", m=model, e=exc)
        return None
    if pipeline is None:
        logger.warning(
            "Modelo de diarización no disponible (¿falta HUGGINGFACE_TOKEN o aceptar la licencia "
            "de '{m}' en huggingface.co?). Se continúa sin speakers.",
            m=model,
        )
    return pipeline


def diarize_audio(
    audio_path: Path,
    *,
    enabled: bool = False,
    hf_token: str = "",
    model: str = _DEFAULT_MODEL,
) -> list[SpeakerTurn] | None:
    """Devuelve los turnos de hablante del audio, o None si la diarización no aplica/falla.

    None (passthrough) cubre: deshabilitada, pyannote ausente, token/licencia faltante o error del
    modelo. El llamador debe tratar None como "sin diarización" y seguir con la transcripción.
    """
    if not enabled:
        return None
    pipeline = _load_pipeline(model, hf_token)
    if pipeline is None:
        return None
    try:
        annotation = pipeline(str(audio_path))
        turns = [
            SpeakerTurn(start=float(segment.start), end=float(segment.end), speaker=str(label))
            for segment, _, label in annotation.itertracks(yield_label=True)
        ]
    except Exception as exc:  # pragma: no cover - depende del modelo en runtime
        logger.warning("Diarización fallida ({e}); se continúa sin speakers", e=exc)
        return None

    logger.info(
        "Diarización: {n} turno(s), {s} speaker(s) distinto(s)",
        n=len(turns),
        s=len({t.speaker for t in turns}),
    )
    return turns
