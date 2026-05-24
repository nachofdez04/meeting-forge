"""Modelos Pydantic para transcripción."""

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    """Segmento individual de la transcripción."""

    start: float = Field(..., description="Timestamp de inicio en segundos")
    end: float = Field(..., description="Timestamp de fin en segundos")
    text: str = Field(..., description="Texto transcrito")
    speaker: str | None = Field(
        None, description="Identificador del speaker (si hay diarización)"
    )


class Transcript(BaseModel):
    """Transcripción completa de un audio."""

    segments: list[TranscriptSegment] = Field(default_factory=list)
    duration_seconds: float = Field(..., description="Duración total del audio")
    language: str | None = Field(None, description="Idioma detectado")

    def to_text(self) -> str:
        """Devuelve el texto completo concatenado, un segmento por línea."""
        return "\n".join(seg.text for seg in self.segments)
