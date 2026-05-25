"""Módulo de generación (Fase 2): ADRs y actas con citas reales a partir de MeetingInsights."""

from .generator import DocumentGenerator
from .schemas import DocumentKind, GeneratedDocument, GenerationMode, MeetingMetadata

__all__ = [
    "DocumentGenerator",
    "DocumentKind",
    "GeneratedDocument",
    "GenerationMode",
    "MeetingMetadata",
]
