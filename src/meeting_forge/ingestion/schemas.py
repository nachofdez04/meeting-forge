"""Modelos Pydantic para transcripción."""

from collections.abc import Mapping

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    """Segmento individual de la transcripción."""

    start: float = Field(..., description="Timestamp de inicio en segundos")
    end: float = Field(..., description="Timestamp de fin en segundos")
    text: str = Field(..., description="Texto transcrito")
    speaker: str | None = Field(None, description="Identificador del speaker (si hay diarización)")


class Transcript(BaseModel):
    """Transcripción completa de un audio."""

    segments: list[TranscriptSegment] = Field(default_factory=list)
    duration_seconds: float = Field(..., description="Duración total del audio")
    language: str | None = Field(None, description="Idioma detectado")

    def to_text(self) -> str:
        """Devuelve el texto completo concatenado, un segmento por línea.

        Si un segmento tiene speaker (diarización · M7), la línea va prefijada con él
        (`Ana: hola`): con hablantes delante, el LLM asigna responsables y tareas mucho
        mejor (UX-3).
        """
        return "\n".join(
            f"{seg.speaker}: {seg.text}" if seg.speaker else seg.text for seg in self.segments
        )

    def to_indexed_text(self) -> str:
        """Como `to_text()`, pero prefija cada línea con su índice de segmento `[S<n>]` (UX-6).

        Permite que el LLM cite el momento exacto en que se discutió cada decisión/tarea
        (`transcript_refs`), resoluble después a los tiempos del segmento.
        """
        lines: list[str] = []
        for i, seg in enumerate(self.segments):
            speaker = f"{seg.speaker}: " if seg.speaker else ""
            lines.append(f"[S{i}] {speaker}{seg.text}")
        return "\n".join(lines)

    def rename_speakers(self, mapping: Mapping[str, str]) -> int:
        """Sustituye etiquetas de speaker (`SPEAKER_00` → `Ana`) in-place (UX-3).

        Ignora entradas vacías del mapping. Devuelve cuántos segmentos renombró.
        """
        renamed = 0
        for seg in self.segments:
            if seg.speaker is None:
                continue
            new_name = (mapping.get(seg.speaker) or "").strip()
            if new_name and new_name != seg.speaker:
                seg.speaker = new_name
                renamed += 1
        return renamed
