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
from .schemas import ActionItem, Decision, MeetingInsights

_DEFAULT_PROMPT = """
Analiza la siguiente transcripción de una reunión técnica y extrae:

1. **Decisiones técnicas**: Cualquier decisión de arquitectura, tecnología o estrategia.
2. **Tareas pendientes**: Acciones asignadas a personas o equipos.
3. **Temas principales**: Los tópicos centrales de la discusión.
4. **Resumen ejecutivo**: Un párrafo que sintetice lo más importante.

Transcripción:
{transcript}
"""

_SOURCE_MARKER_RE = re.compile(r"#(\d+)")


# --- Schemas internos: el LLM emite `sources: list[str]` (marcadores "#N"). ---


class _RawDecision(BaseModel):
    title: str
    description: str
    rationale: str | None = None
    owners: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class _RawActionItem(BaseModel):
    description: str
    assignee: str | None = None
    deadline: str | None = None
    sources: list[str] = Field(default_factory=list)


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
        if self.retriever is not None and "{context}" in self.prompt_template:
            prompt = self.prompt_template.format(
                context=context_block,
                transcript=transcript.to_text(),
            )
        else:
            prompt = self.prompt_template.format(transcript=transcript.to_text())

        raw = self.provider.complete_structured(
            prompt=prompt,
            schema=_RawMeetingInsights,
            system=(
                "Eres un asistente experto en analizar reuniones técnicas y "
                "extraer información estructurada."
            ),
        )

        insights = self._resolve_sources(raw, ordered_chunks)
        logger.info(
            "Insights extraídos: {d} decisiones, {a} tareas, {s} con citas",
            d=len(insights.decisions),
            a=len(insights.action_items),
            s=sum(1 for d in insights.decisions if d.sources)
            + sum(1 for a in insights.action_items if a.sources),
        )
        return insights

    def _build_context(
        self, transcript: Transcript
    ) -> tuple[str, list[RetrievalResult]]:
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
            header = (
                f"[#{idx}] {res.chunk.source_path}"
                f":{res.chunk.line_start}-{res.chunk.line_end}"
            )
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
        raw: _RawMeetingInsights, ordered_chunks: list[RetrievalResult]
    ) -> MeetingInsights:
        """Mapea marcadores `"#N"` a SourceRef usando la lista ordenada."""
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

        decisions = [
            Decision(
                title=d.title,
                description=d.description,
                rationale=d.rationale,
                owners=d.owners,
                tags=d.tags,
                sources=to_refs(d.sources),
            )
            for d in raw.decisions
        ]
        action_items = [
            ActionItem(
                description=a.description,
                assignee=a.assignee,
                deadline=a.deadline,
                sources=to_refs(a.sources),
            )
            for a in raw.action_items
        ]
        return MeetingInsights(
            decisions=decisions,
            action_items=action_items,
            topics=raw.topics,
            summary=raw.summary,
        )
