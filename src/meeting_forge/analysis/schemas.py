"""Modelos Pydantic para insights extraídos."""

from pydantic import BaseModel, Field


class Decision(BaseModel):
    """Decisión técnica identificada en la reunión."""

    title: str = Field(..., description="Título breve de la decisión")
    description: str = Field(..., description="Descripción detallada")
    rationale: str | None = Field(None, description="Justificación o contexto")
    owners: list[str] = Field(default_factory=list, description="Responsables de la decisión")
    tags: list[str] = Field(default_factory=list, description="Tags para categorización")


class ActionItem(BaseModel):
    """Tarea o acción pendiente identificada en la reunión."""

    description: str = Field(..., description="Descripción de la tarea")
    assignee: str | None = Field(None, description="Persona asignada")
    deadline: str | None = Field(None, description="Fecha límite si se mencionó")


class MeetingInsights(BaseModel):
    """Conjunto de insights extraídos de una reunión."""

    decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    topics: list[str] = Field(
        default_factory=list, description="Temas principales discutidos"
    )
    summary: str = Field("", description="Resumen ejecutivo de la reunión")
