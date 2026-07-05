"""Preprocesado opcional de audio antes de la transcripción (F9).

Sin dependencias Python nuevas: usa **ffmpeg** (ya requerido por faster-whisper) vía subprocess para
normalizar volumen (`loudnorm`), pasar a mono y resamplear a 16 kHz. Diseño tolerante a fallos: si el
preprocesado está desactivado, ffmpeg no está disponible o la conversión falla, se devuelve el audio
**original** (passthrough) sin romper el pipeline.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from loguru import logger

# Contenedores de vídeo (grabaciones de Meet/Teams/Zoom · UX-13): la pista de audio se extrae
# con ffmpeg antes de transcribir, aunque el preprocesado esté desactivado en settings.
_VIDEO_SUFFIXES = frozenset({".mp4", ".webm", ".mkv", ".mov", ".avi"})


def needs_audio_extraction(path: Path) -> bool:
    """True si el fichero es un contenedor de vídeo del que conviene extraer el audio (UX-13)."""
    return path.suffix.lower() in _VIDEO_SUFFIXES


def preprocess_audio(
    input_path: Path,
    *,
    enabled: bool = False,
    target_sr: int = 16000,
    ffmpeg_executable: str = "ffmpeg",
) -> Path:
    """Devuelve la ruta del audio preprocesado, o la original si el preprocesado no aplica.

    Pasos (si `enabled` y hay ffmpeg): mono + resampleo a `target_sr` Hz + normalización de volumen.
    """
    if not enabled:
        return input_path
    if shutil.which(ffmpeg_executable) is None:
        logger.warning("ffmpeg no disponible; se omite el preprocesado de audio")
        return input_path

    output_path = input_path.with_name(f"{input_path.stem}_pre16k.wav")
    cmd = [
        ffmpeg_executable,
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        str(target_sr),
        "-af",
        "loudnorm",
        str(output_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        logger.warning("No se pudo ejecutar ffmpeg ({e}); se usa el audio original", e=exc)
        return input_path

    if result.returncode != 0 or not output_path.exists():
        logger.warning(
            "ffmpeg falló (código {c}); se usa el audio original. stderr: {e}",
            c=result.returncode,
            e=result.stderr.strip()[:200],
        )
        return input_path

    logger.info("Audio preprocesado (mono, {sr} Hz, loudnorm): {p}", sr=target_sr, p=output_path)
    return output_path
