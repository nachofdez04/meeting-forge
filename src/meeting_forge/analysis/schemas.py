"""Modelos Pydantic para insights extraídos."""

from pydantic import BaseModel, Field

from ..rag.schemas import SourceRef

__all__ = ["ActionItem", "Decision", "MeetingInsights", "SourceRef", "TranscriptRef"]


class TranscriptRef(BaseModel):
    """Referencia a un momento del transcript donde se discutió algo (UX-6).

    Resuelta desde los marcadores `S<n>` que el LLM asocia a cada decisión/tarea; guarda el índice
    de segmento y sus tiempos para poder saltar al minuto exacto del audio.
    """

    segment_index: int = Field(..., ge=0, description="Índice del segmento en el transcript")
    start: float = Field(..., description="Inicio del segmento en segundos")
    end: float = Field(..., description="Fin del segmento en segundos")
    text: str = Field(..., description="Texto del segmento citado")


class Decision(BaseModel):
    """Decisión técnica identificada en la reunión."""

    title: str = Field(..., description="Título breve de la decisión")
    description: str = Field(..., description="Descripción detallada")
    rationale: str | None = Field(None, description="Justificación o contexto")
    owners: list[str] = Field(default_factory=list, description="Responsables de la decisión")
    tags: list[str] = Field(default_factory=list, description="Tags para categorización")
    sources: list[SourceRef] = Field(
        default_factory=list,
        description="Citas a chunks de documentación que respaldan la decisión",
    )
    transcript_refs: list[TranscriptRef] = Field(
        default_factory=list,
        description="Momentos del transcript donde se discutió la decisión (UX-6)",
    )


class ActionItem(BaseModel):
    """Tarea o acción pendiente identificada en la reunión."""

    description: str = Field(..., description="Descripción de la tarea")
    assignee: str | None = Field(None, description="Persona asignada")
    deadline: str | None = Field(None, description="Fecha límite si se mencionó")
    sources: list[SourceRef] = Field(
        default_factory=list,
        description="Citas a chunks de documentación relacionados",
    )
    transcript_refs: list[TranscriptRef] = Field(
        default_factory=list,
        description="Momentos del transcript donde se mencionó la tarea (UX-6)",
    )


class MeetingInsights(BaseModel):
    """Conjunto de insights extraídos de una reunión."""

    decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list, description="Temas principales discutidos")
    summary: str = Field(default="", description="Resumen ejecutivo de la reunión")
