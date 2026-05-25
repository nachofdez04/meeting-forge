"""Esquemas Pydantic para el estado de validación humana (Fase 4)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ValidationStatus(str, Enum):
    """Estado de validación de un documento."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


class ValidationRecord(BaseModel):
    """Estado de validación de un documento individual."""

    filename: str
    status: ValidationStatus = ValidationStatus.PENDING
    edited_content: str | None = None
    rejection_reason: str | None = None
    validated_at: datetime | None = None


class MeetingValidationState(BaseModel):
    """Estado de validación completo de una reunión."""

    records: dict[str, ValidationRecord] = Field(default_factory=dict)

    def approved_records(self) -> list[ValidationRecord]:
        """Devuelve solo los registros aprobados o editados (a publicar)."""
        return [
            r
            for r in self.records.values()
            if r.status in (ValidationStatus.APPROVED, ValidationStatus.EDITED)
        ]

    def pending_count(self) -> int:
        return sum(1 for r in self.records.values() if r.status == ValidationStatus.PENDING)

    def approved_count(self) -> int:
        return len(self.approved_records())

    def rejected_count(self) -> int:
        return sum(1 for r in self.records.values() if r.status == ValidationStatus.REJECTED)
