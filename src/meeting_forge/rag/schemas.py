"""Modelos Pydantic del módulo RAG."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    """Fragmento de documentación indexable."""

    chunk_id: str = Field(..., description="ID único determinístico (hash)")
    source_path: str = Field(..., description="Ruta relativa al corpus")
    section_path: list[str] = Field(
        default_factory=list,
        description="Jerarquía de headers (H1 → H2 → ...)",
    )
    text: str = Field(..., description="Contenido textual del chunk")
    line_start: int = Field(..., ge=0, description="Línea inicial en el archivo (1-indexed)")
    line_end: int = Field(..., ge=0, description="Línea final en el archivo (1-indexed)")


class SourceRef(BaseModel):
    """Referencia a un fragmento de documentación usado como evidencia."""

    source_path: str
    line_start: int
    line_end: int
    section_path: list[str] = Field(default_factory=list)


class RetrievalResult(BaseModel):
    """Resultado de una consulta al vector store."""

    chunk: DocumentChunk
    score: float = Field(..., description="Similitud (mayor = más relevante)")
