"""Modelos Pydantic del módulo de generación (Fase 2)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from ..rag.schemas import SourceRef


class GenerationMode(str, Enum):
    """Modos de generación de documentos."""

    ADR_PER_DECISION = "adr-per-decision"
    ADR_CONSOLIDATED = "adr-consolidated"
    ACTA = "acta"


class DocumentKind(str, Enum):
    """Tipo de documento generado."""

    ADR = "adr"
    ACTA = "acta"


class MeetingMetadata(BaseModel):
    """Metadatos de la reunión para nominar y datar los documentos generados."""

    meeting_id: str = Field(..., description="Identificador estable (normalmente el stem del audio)")
    title: str = Field("", description="Título legible de la reunión")
    date: str | None = Field(
        None, description="Fecha ISO YYYY-MM-DD; se deriva del mtime del audio si se omite"
    )
    attendees: list[str] = Field(default_factory=list, description="Participantes de la reunión")
    source_audio: str | None = Field(None, description="Path del audio origen (para trazabilidad)")


class GeneratedDocument(BaseModel):
    """Documento Markdown producido por el generador."""

    filename: str = Field(..., description="Nombre del fichero (sin directorio)")
    kind: DocumentKind
    mode: GenerationMode
    markdown_content: str = Field(..., description="Contenido Markdown listo para escribir")
    sources_used: list[SourceRef] = Field(
        default_factory=list,
        description="SourceRefs incluidas en el documento (para trazabilidad)",
    )
    decision_titles: list[str] = Field(
        default_factory=list,
        description="Títulos de las Decisions que respaldan este documento",
    )

    def write_to(self, directory: Path) -> Path:
        """Escribe el documento en el directorio indicado y devuelve la ruta final."""
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / self.filename
        target.write_text(self.markdown_content, encoding="utf-8")
        return target
