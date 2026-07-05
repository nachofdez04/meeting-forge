"""Lectura y actualización del estado persistido de una reunión (paso 2 · UX-2/UX-3/UX-5).

Una reunión procesada vive en `data/outputs/<meeting_id>/` con dos ficheros de datos:
`<id>_result.json` (fuente de verdad: transcript + insights + metadata + evidencia) y
`<id>_transcript.json` (copia canónica del transcript). Este módulo centraliza su lectura y
las escrituras parciales que hace el ciclo HITL: corregir el transcript, renombrar speakers y
editar insights. Todas las escrituras de `result.json` son atómicas (tmp + replace), igual que
en `validation/store.py`.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from .analysis.schemas import MeetingInsights
from .ingestion.schemas import Transcript

_SPEAKER_NAMES_KEY = "speaker_names"


def find_result_path(meeting_dir: Path) -> Path:
    """Devuelve el `*_result.json` de la reunión (orden determinista si hubiera varios)."""
    candidates = sorted(meeting_dir.glob("*_result.json"))
    if not candidates:
        raise FileNotFoundError(f"No se encontró *_result.json en {meeting_dir}")
    return candidates[0]


def load_result(meeting_dir: Path) -> dict[str, object]:
    """Carga el result.json de la reunión como dict."""
    raw = json.loads(find_result_path(meeting_dir).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"result.json inválido en {meeting_dir} (se esperaba un objeto)")
    return raw


def save_result(meeting_dir: Path, result: dict[str, object]) -> None:
    """Escribe el result.json atómicamente (tmp + replace) para no corromperlo a medias."""
    target = find_result_path(meeting_dir)
    tmp = meeting_dir / f".result_{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _transcript_path(meeting_dir: Path) -> Path:
    return meeting_dir / f"{meeting_dir.name}_transcript.json"


def load_transcript(meeting_dir: Path) -> Transcript:
    """Carga el transcript canónico; si el fichero no existe, cae al bloque de result.json."""
    path = _transcript_path(meeting_dir)
    if path.exists():
        return Transcript.model_validate_json(path.read_text(encoding="utf-8"))
    result = load_result(meeting_dir)
    return Transcript.model_validate(result.get("transcript", {}))


def save_transcript(meeting_dir: Path, transcript: Transcript) -> None:
    """Persiste el transcript corregido (UX-2) en el fichero canónico Y en result.json."""
    _transcript_path(meeting_dir).write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    result = load_result(meeting_dir)
    result["transcript"] = transcript.model_dump()
    save_result(meeting_dir, result)


def load_speaker_names(meeting_dir: Path) -> dict[str, str]:
    """Mapa `etiqueta → nombre` (UX-3) guardado en result.json; {} si no hay."""
    raw = load_result(meeting_dir).get(_SPEAKER_NAMES_KEY)
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if str(v).strip()}


def save_speaker_names(meeting_dir: Path, names: dict[str, str]) -> None:
    """Persiste el mapa de nombres de speaker (UX-3), descartando entradas vacías."""
    result = load_result(meeting_dir)
    result[_SPEAKER_NAMES_KEY] = {k: v.strip() for k, v in names.items() if v.strip()}
    save_result(meeting_dir, result)


def save_insights(meeting_dir: Path, insights: MeetingInsights, *, edited: bool = True) -> None:
    """Persiste insights (corregidos a mano · UX-5, o re-extraídos · UX-2) en result.json.

    `edited=True` marca `insights_edited` para que la auditoría distinga la corrección humana
    de la extracción automática.
    """
    result = load_result(meeting_dir)
    result["insights"] = insights.model_dump()
    if edited:
        result["insights_edited"] = True
    save_result(meeting_dir, result)
