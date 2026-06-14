"""Modelos Pydantic del módulo de generación (Fase 2)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from ..rag.schemas import SourceRef


@dataclass
class GeneratedDocView:
    """Vista ligera de un documento generado (ADR, Acta, Roadmap, Doc técnica).

    Contrato compartido por UI, validación y publicación. Vive aquí (capa de dominio) para que
    `validation/` y `git_integration/` no dependan de `ui/` (evita el ciclo de imports · TD1).
    """

    filename: str
    kind: str  # "adr" | "acta" | "roadmap" | "technical-doc"
    markdown_content: str
    diff: str | None = None  # diff vs documento existente, en modos de actualización (F5)


class GenerationMode(StrEnum):
    """Modos de generación de documentos."""

    ADR_PER_DECISION = "adr-per-decision"
    ADR_CONSOLIDATED = "adr-consolidated"
    ACTA = "acta"
    ROADMAP_UPDATE = "roadmap-update"
    TECHNICAL_DOC_UPDATE = "technical-doc-update"


class DocumentKind(StrEnum):
    """Tipo de documento generado."""

    ADR = "adr"
    ACTA = "acta"
    ROADMAP = "roadmap"
    TECHNICAL_DOC = "technical-doc"


class MeetingMetadata(BaseModel):
    """Metadatos de la reunión para nominar y datar los documentos generados."""

    meeting_id: str = Field(
        ..., description="Identificador estable (normalmente el stem del audio)"
    )
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
    diff: str | None = Field(
        default=None,
        description="Diff unificado vs el documento existente (solo en modos de actualización · F5)",
    )

    def write_to(self, directory: Path) -> Path:
        """Escribe el documento (y su diff, si lo hay) y devuelve la ruta del `.md`."""
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / self.filename
        target.write_text(self.markdown_content, encoding="utf-8")
        if self.diff:
            (directory / f"{self.filename}.diff").write_text(self.diff, encoding="utf-8")
        return target
