"""Persistencia del estado de validación en disco (validation.json)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from ..generation.schemas import GeneratedDocView
from .schemas import MeetingValidationState, ValidationRecord, ValidationStatus

_FILENAME = "validation.json"


def load_state(meeting_dir: Path) -> MeetingValidationState:
    """Lee validation.json; si no existe devuelve estado vacío."""
    path = meeting_dir / _FILENAME
    if not path.exists():
        return MeetingValidationState()
    try:
        return MeetingValidationState.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("validation.json ilegible en {p}: {e}; se reinicia el estado", p=path, e=exc)
        return MeetingValidationState()


def save_state(meeting_dir: Path, state: MeetingValidationState) -> None:
    """Escribe el estado atómicamente (tmp + rename) para evitar corrupción."""
    meeting_dir.mkdir(parents=True, exist_ok=True)
    target = meeting_dir / _FILENAME
    tmp = meeting_dir / f".validation_{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def clear_state(meeting_dir: Path) -> None:
    """Borra el `validation.json` de la reunión (no-op si no existe).

    Se usa al reprocesar una reunión: los documentos se regeneran, así que las aprobaciones o
    ediciones previas apuntaban a contenido superado y deben reiniciarse a PENDING (B-N2).
    """
    (meeting_dir / _FILENAME).unlink(missing_ok=True)


def initialize_pending(meeting_dir: Path, docs: list[GeneratedDocView]) -> MeetingValidationState:
    """Crea registros PENDING para docs aún no validados. Idempotente: no sobreescribe."""
    state = load_state(meeting_dir)
    changed = False
    for doc in docs:
        if doc.filename not in state.records:
            state.records[doc.filename] = ValidationRecord(filename=doc.filename)
            changed = True
    if changed:
        save_state(meeting_dir, state)
    return state


def mark_approved(
    state: MeetingValidationState,
    filename: str,
    edited_content: str | None = None,
) -> MeetingValidationState:
    """Marca un documento como aprobado (con contenido editado opcional)."""
    record = state.records.get(filename, ValidationRecord(filename=filename))
    if edited_content is not None:
        record.status = ValidationStatus.EDITED
        record.edited_content = edited_content
    else:
        record.status = ValidationStatus.APPROVED
        record.edited_content = None
    record.rejection_reason = None
    record.validated_at = datetime.now(tz=UTC)
    state.records[filename] = record
    return state


def mark_rejected(
    state: MeetingValidationState,
    filename: str,
    reason: str = "",
) -> MeetingValidationState:
    """Marca un documento como rechazado."""
    record = state.records.get(filename, ValidationRecord(filename=filename))
    record.status = ValidationStatus.REJECTED
    record.rejection_reason = reason or None
    record.edited_content = None
    record.validated_at = datetime.now(tz=UTC)
    state.records[filename] = record
    return state


def reset_record(
    state: MeetingValidationState,
    filename: str,
) -> MeetingValidationState:
    """Resetea un documento a PENDING."""
    record = state.records.get(filename, ValidationRecord(filename=filename))
    record.status = ValidationStatus.PENDING
    record.edited_content = None
    record.rejection_reason = None
    record.validated_at = None
    state.records[filename] = record
    return state


def get_effective_content(
    state: MeetingValidationState,
    filename: str,
    original_content: str,
) -> str:
    """Devuelve edited_content si existe, o el contenido original del documento."""
    record = state.records.get(filename)
    if record and record.edited_content is not None:
        return record.edited_content
    return original_content


def auto_approve(
    state: MeetingValidationState,
    docs: list[GeneratedDocView],
    allowed_kinds: list[str],
) -> list[str]:
    """Auto-aprueba (F8) los documentos cuyo `kind` esté en `allowed_kinds`. Devuelve los filenames.

    Marca `auto_approved=True` para que la UI y la auditoría distingan estas aprobaciones de las humanas.
    """
    approved: list[str] = []
    for doc in docs:
        if doc.kind not in allowed_kinds:
            continue
        record = state.records.get(doc.filename, ValidationRecord(filename=doc.filename))
        record.status = ValidationStatus.APPROVED
        record.auto_approved = True
        record.edited_content = None
        record.rejection_reason = None
        record.validated_at = datetime.now(tz=UTC)
        state.records[doc.filename] = record
        approved.append(doc.filename)
    return approved
