"""Extracción de insights de transcripciones usando LLMs (con RAG opcional)."""

from __future__ import annotations

import re

from loguru import logger
from pydantic import BaseModel, Field

from ..config import settings
from ..ingestion.schemas import Transcript
from ..rag.retriever import Retriever
from ..rag.schemas import RetrievalResult, SourceRef
from .llm_client import LLMProvider, get_provider
from .schemas import ActionItem, Decision, MeetingInsights, TranscriptRef

_DEFAULT_PROMPT = """
Analiza la siguiente transcripción de una reunión técnica y extrae:

1. **Decisiones técnicas**: Cualquier decisión de arquitectura, tecnología o estrategia.
2. **Tareas pendientes**: Acciones asignadas a personas o equipos.
3. **Temas principales**: Los tópicos centrales de la discusión.
4. **Resumen ejecutivo**: Un párrafo que sintetice lo más importante.

Cada línea del transcript lleva un marcador de segmento `[S0]`, `[S1]`, … Para cada decisión y
tarea, incluye en `transcript_refs` los marcadores (`"S3"`, `"S7"`) de los segmentos donde se
discutió. Cita solo lo que realmente la respalda; si no aplica ninguno, deja la lista vacía.

Transcripción:
{transcript}
"""

_SOURCE_MARKER_RE = re.compile(r"#(\d+)")
_SEGMENT_MARKER_RE = re.compile(r"S(\d+)")


# --- Schemas internos: el LLM emite marcadores `"#N"` (docs RAG) y `"S<n>"` (segmentos). ---


class _RawDecision(BaseModel):
    title: str
    description: str
    rationale: str | None = None
    owners: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    transcript_refs: list[str] = Field(default_factory=list)


class _RawActionItem(BaseModel):
    description: str
    assignee: str | None = None
    deadline: str | None = None
    sources: list[str] = Field(default_factory=list)
    transcript_refs: list[str] = Field(default_factory=list)


class _RawMeetingInsights(BaseModel):
    decisions: list[_RawDecision] = Field(default_factory=list)
    action_items: list[_RawActionItem] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    summary: str = ""


class InsightsExtractor:
    """Extrae decisiones, tareas y temas de una transcripción.

    Si recibe un `Retriever`, enriquece el prompt con contexto y mapea los
    marcadores `"#N"` que devuelve el LLM a `SourceRef` reales.
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        retriever: Retriever | None = None,
    ) -> None:
        self.provider: LLMProvider = provider or get_provider()
        self.retriever = retriever
        self.prompt_template = self._load_prompt(use_v2=retriever is not None)
        # Chunks recuperados en la última extracción (para persistir evidencia · F3).
        self.last_context: list[RetrievalResult] = []

    def _load_prompt(self, use_v2: bool) -> str:
        """Carga v2 si hay retriever, v1 si no."""
        name = "v2.md" if use_v2 else "v1.md"
        prompt_path = settings.prompts_dir / "extraction" / name
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        logger.warning("Prompt no encontrado en {p}, usando default", p=prompt_path)
        return _DEFAULT_PROMPT

    def extract(self, transcript: Transcript) -> MeetingInsights:
        """Extrae insights, opcionalmente enriquecidos con contexto RAG."""
        logger.info("Extrayendo insights con LLM (rag={r})", r=self.retriever is not None)

        context_block, ordered_chunks = self._build_context(transcript)
        self.last_context = ordered_chunks
        # Texto con índices de segmento `[S<n>]` para que el LLM cite momentos del audio (UX-6).
        transcript_text = transcript.to_indexed_text()
        if self.retriever is not None and "{context}" in self.prompt_template:
            prompt = self.prompt_template.format(
                context=context_block,
                transcript=transcript_text,
            )
        else:
            prompt = self.prompt_template.format(transcript=transcript_text)

        raw = self.provider.complete_structured(
            prompt=prompt,
            schema=_RawMeetingInsights,
            system=(
                "Eres un asistente experto en analizar reuniones técnicas y "
                "extraer información estructurada."
            ),
        )

        insights = self._resolve_sources(raw, ordered_chunks, transcript)
        logger.info(
            "Insights extraídos: {d} decisiones, {a} tareas, {s} con citas",
            d=len(insights.decisions),
            a=len(insights.action_items),
            s=sum(1 for d in insights.decisions if d.sources)
            + sum(1 for a in insights.action_items if a.sources),
        )
        return insights

    def _build_context(self, transcript: Transcript) -> tuple[str, list[RetrievalResult]]:
        """Recupera chunks y construye el bloque de contexto con marcadores `#N`."""
        if self.retriever is None:
            return "", []

        results = self.retriever.retrieve_for_transcript(transcript)
        if not results:
            return "(sin contexto disponible)", []

        lines: list[str] = []
        total_chars = 0
        used: list[RetrievalResult] = []
        for idx, res in enumerate(results, start=1):
            header = f"[#{idx}] {res.chunk.source_path}:{res.chunk.line_start}-{res.chunk.line_end}"
            if res.chunk.section_path:
                header += f"  ({' › '.join(res.chunk.section_path)})"
            block = f"{header}\n{res.chunk.text}\n"
            if total_chars + len(block) > settings.context_max_chars and used:
                break
            lines.append(block)
            total_chars += len(block)
            used.append(res)

        return "\n".join(lines), used

    @staticmethod
    def _resolve_sources(
        raw: _RawMeetingInsights,
        ordered_chunks: list[RetrievalResult],
        transcript: Transcript | None = None,
    ) -> MeetingInsights:
        """Mapea marcadores `"#N"` a SourceRef (docs) y `"S<n>"` a TranscriptRef (audio · UX-6)."""

        def to_refs(markers: list[str]) -> list[SourceRef]:
            refs: list[SourceRef] = []
            seen: set[str] = set()
            for marker in markers:
                m = _SOURCE_MARKER_RE.search(marker)
                if not m:
                    continue
                idx = int(m.group(1))
                if idx < 1 or idx > len(ordered_chunks):
                    logger.warning("Marcador #{n} fuera de rango", n=idx)
                    continue
                chunk = ordered_chunks[idx - 1].chunk
                key = f"{chunk.source_path}:{chunk.line_start}-{chunk.line_end}"
                if key in seen:
                    continue
                seen.add(key)
                refs.append(
                    SourceRef(
                        source_path=chunk.source_path,
                        line_start=chunk.line_start,
                        line_end=chunk.line_end,
                        section_path=list(chunk.section_path),
                    )
                )
            return refs

        segments = transcript.segments if transcript is not None else []

        def to_transcript_refs(markers: list[str]) -> list[TranscriptRef]:
            refs: list[TranscriptRef] = []
            seen: set[int] = set()
            for marker in markers:
                m = _SEGMENT_MARKER_RE.search(marker)
                if not m:
                    continue
                idx = int(m.group(1))
                if idx < 0 or idx >= len(segments):
                    logger.warning("Marcador de segmento S{n} fuera de rango", n=idx)
                    continue
                if idx in seen:
                    continue
                seen.add(idx)
                seg = segments[idx]
                refs.append(
                    TranscriptRef(segment_index=idx, start=seg.start, end=seg.end, text=seg.text)
                )
            return refs

        decisions = [
            Decision(
                title=d.title,
                description=d.description,
                rationale=d.rationale,
                owners=d.owners,
                tags=d.tags,
                sources=to_refs(d.sources),
                transcript_refs=to_transcript_refs(d.transcript_refs),
            )
            for d in raw.decisions
        ]
        action_items = [
            ActionItem(
                description=a.description,
                assignee=a.assignee,
                deadline=a.deadline,
                sources=to_refs(a.sources),
                transcript_refs=to_transcript_refs(a.transcript_refs),
            )
            for a in raw.action_items
        ]
        return MeetingInsights(
            decisions=decisions,
            action_items=action_items,
            topics=raw.topics,
            summary=raw.summary,
        )
