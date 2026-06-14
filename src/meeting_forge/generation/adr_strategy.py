"""Estrategia de generación de ADRs (Architecture Decision Records).

Flujo híbrido:
1. Template construye la estructura fija (headings, tabla de metadatos, sección Referencias).
2. LLM genera las secciones de prosa (Contexto, Decisión, Consecuencias) usando marcadores #N.
3. Post-procesado reescribe #N → [^N] y añade el bloque de footnotes.
"""

from __future__ import annotations

from collections.abc import Callable

from loguru import logger
from pydantic import BaseModel, Field

from ..analysis.llm_client import LLMProvider, get_provider
from ..analysis.schemas import Decision, MeetingInsights
from ..config import settings
from .citations import (
    CitationRegistry,
    render_footnote_block,
    rewrite_marker_text,
    rewrite_markers,
)
from .filenames import build_adr_filename, build_consolidated_adr_filename
from .schemas import DocumentKind, GeneratedDocument, GenerationMode, MeetingMetadata
from .templates import render_adr_skeleton


def _remap_resolver(mapping: dict[int, int]) -> Callable[[int], int | None]:
    """Resolver `#local → [^global]` para el ADR consolidado (definido fuera del bucle · sin B023)."""

    def _resolve(local_idx: int) -> int | None:
        return mapping.get(local_idx)

    return _resolve


_DEFAULT_PROMPT = """\
Redacta las secciones de prosa de una ADR para la siguiente decisión:

Título: {decision_title}
Descripción: {decision_description}

Genera: context_md (contexto), decision_md (la decisión), consequences_md (consecuencias).
"""


class _RawADR(BaseModel):
    """Respuesta cruda del LLM: prosa con marcadores #N."""

    title: str = Field(default="", description="Título (puede ajustar el original)")
    status: str = Field(default="Propuesto")
    context_md: str = Field(..., description="Sección Contexto con marcadores #N opcionales")
    decision_md: str = Field(..., description="Sección Decisión con marcadores #N opcionales")
    consequences_md: str = Field(
        ..., description="Sección Consecuencias con marcadores #N opcionales"
    )


# ---------------------------------------------------------------------------
# AdrStrategy
# ---------------------------------------------------------------------------


class AdrStrategy:
    """Genera ADRs individuales y el ADR consolidado de una reunión."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        prompt_version: str = "v1",
    ) -> None:
        self.provider: LLMProvider = provider or get_provider()
        self._prompt_template = self._load_prompt(prompt_version)
        # TD6: caché de prosa por decisión para no repetir la llamada LLM entre el ADR
        # por-decisión y el consolidado (mismas decisiones → N llamadas en vez de 2N).
        self._raw_cache: dict[str, _RawADR] = {}

    # ------------------------------------------------------------------
    # Prompt loading
    # ------------------------------------------------------------------

    def _load_prompt(self, version: str) -> str:
        prompt_path = settings.prompts_dir / "generation" / f"adr_{version}.md"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        logger.warning("Prompt ADR no encontrado en {p}, usando default", p=prompt_path)
        return _DEFAULT_PROMPT

    # ------------------------------------------------------------------
    # Generación por-decisión
    # ------------------------------------------------------------------

    def generate_per_decision(
        self,
        insights: MeetingInsights,
        metadata: MeetingMetadata,
    ) -> list[GeneratedDocument]:
        """Genera un ADR independiente por cada Decision en MeetingInsights."""
        docs: list[GeneratedDocument] = []
        for counter, decision in enumerate(insights.decisions, start=1):
            logger.info(
                "Generando ADR {n}/{total}: {title}",
                n=counter,
                total=len(insights.decisions),
                title=decision.title,
            )
            # TD5: un fallo del LLM en una decisión no debe tirar el resto de ADRs del modo.
            try:
                doc = self._build_adr_for_decision(decision, counter, metadata)
                docs.append(doc)
            except Exception as exc:
                logger.error(
                    "Error generando ADR para '{title}': {e}. Se omite esta decisión.",
                    title=decision.title,
                    e=exc,
                )
        return docs

    def _build_adr_for_decision(
        self,
        decision: Decision,
        counter: int,
        metadata: MeetingMetadata,
    ) -> GeneratedDocument:
        # 1. Construir el registry con los sources de esta decisión
        registry = CitationRegistry()
        registry.register_all(decision.sources)

        # 2. Obtener la prosa del LLM
        raw = self._call_llm(decision, registry)

        # 3. Reescribir marcadores #N → [^N] en cada sección
        context_md, used_ctx = rewrite_markers(raw.context_md, registry)
        decision_md, used_dec = rewrite_markers(raw.decision_md, registry)
        consequences_md, used_con = rewrite_markers(raw.consequences_md, registry)
        all_used = used_ctx | used_dec | used_con

        # 4. Ensamblar footnote block (sólo si hay índices usados)
        footnote_block = render_footnote_block(registry, all_used)

        # 5. Montar el Markdown final
        title = raw.title if raw.title else decision.title
        markdown = render_adr_skeleton(
            title=title,
            status=raw.status,
            date=metadata.date or "—",
            owners=", ".join(decision.owners) if decision.owners else "—",
            tags=", ".join(f"`{t}`" for t in decision.tags) if decision.tags else "—",
            context_md=context_md,
            decision_md=decision_md,
            consequences_md=consequences_md,
            footnote_block=footnote_block,
        )

        return GeneratedDocument(
            filename=build_adr_filename(decision.title, counter),
            kind=DocumentKind.ADR,
            mode=GenerationMode.ADR_PER_DECISION,
            markdown_content=markdown,
            sources_used=list(decision.sources),
            decision_titles=[decision.title],
        )

    # ------------------------------------------------------------------
    # ADR consolidado (sintetizado apilando los por-decisión)
    # ------------------------------------------------------------------

    def generate_consolidated(
        self,
        insights: MeetingInsights,
        metadata: MeetingMetadata,
    ) -> GeneratedDocument | None:
        """Genera el ADR consolidado de la reunión.

        Estrategia v1 sintetizada: llama al LLM por cada decisión usando un registro
        local (#1, #2… por decisión), luego remapea los marcadores al registro global
        (que deduplica fuentes compartidas entre decisiones) antes de ensamblar el doc.
        Sin llamada LLM adicional respecto a generate_per_decision.

        Devuelve None si no hay decisiones.
        """
        if not insights.decisions:
            logger.info("ADR consolidado omitido: sin decisiones")
            return None

        meeting_title = metadata.title or metadata.meeting_id
        date_str = metadata.date or "—"

        # Registro global: asigna índices únicos a través de todas las decisiones
        global_registry = CitationRegistry()

        # Primera pasada: registrar TODAS las sources en el global_registry en orden de inserción
        for decision in insights.decisions:
            global_registry.register_all(decision.sources)

        # --- Header ---
        header_lines = [
            f"# ADR Consolidado — {meeting_title}",
            "",
            "| Campo | Valor |",
            "|---|---|",
            f"| **Reunión** | {meeting_title} |",
            f"| **Fecha** | {date_str} |",
            f"| **Decisiones** | {len(insights.decisions)} |",
            "",
            "> Este documento consolida todas las decisiones arquitectónicas "
            "tomadas en la reunión. Cada sección corresponde a un ADR individual.",
            "",
        ]

        body_sections: list[str] = []
        all_global_used: set[int] = set()

        for i, decision in enumerate(insights.decisions, start=1):
            # Registro local: el LLM verá #1, #2… para las fuentes de ESTA decisión
            local_registry = CitationRegistry()
            local_registry.register_all(decision.sources)

            raw = self._call_llm(decision, local_registry)

            # Remapear: #local_idx → [^global_idx]
            # local_idx (1-indexed) → decision.sources[local_idx-1] → global_registry.register
            local_to_global = {
                local_idx: global_registry.register(ref)
                for local_idx, ref in enumerate(decision.sources, start=1)
            }

            resolver = _remap_resolver(local_to_global)
            context_final, used_c = rewrite_marker_text(raw.context_md, resolver)
            decision_final, used_d = rewrite_marker_text(raw.decision_md, resolver)
            consequences_final, used_k = rewrite_marker_text(raw.consequences_md, resolver)
            all_global_used |= used_c | used_d | used_k

            title = raw.title if raw.title else decision.title
            section = [
                "---",
                "",
                f"## Decisión {i}: {title}",
                "",
                f"| **Estado** | {raw.status} | **Responsables** | "
                f"{', '.join(decision.owners) if decision.owners else '—'} |",
                "",
                "### Contexto",
                "",
                context_final,
                "",
                "### Decisión",
                "",
                decision_final,
                "",
                "### Consecuencias",
                "",
                consequences_final,
                "",
            ]
            body_sections.extend(section)

        # Bloque de footnotes global deduplicado
        footnote_block = render_footnote_block(global_registry, all_global_used)
        if footnote_block:
            body_sections += ["---", "", "## Referencias", "", footnote_block, ""]

        all_sources = [s for d in insights.decisions for s in d.sources]
        markdown = "\n".join(header_lines + body_sections)

        return GeneratedDocument(
            filename=build_consolidated_adr_filename(metadata),
            kind=DocumentKind.ADR,
            mode=GenerationMode.ADR_CONSOLIDATED,
            markdown_content=markdown,
            sources_used=list(
                {(s.source_path, s.line_start, s.line_end): s for s in all_sources}.values()
            ),
            decision_titles=[d.title for d in insights.decisions],
        )

    # ------------------------------------------------------------------
    # Llamada al LLM
    # ------------------------------------------------------------------

    def _call_llm(self, decision: Decision, registry: CitationRegistry) -> _RawADR:
        """Construye el prompt y llama al LLM. Devuelve _RawADR con prosa + marcadores #N.

        Memoiza por contenido de la decisión (TD6): el prompt es función pura de la decisión, así
        que el consolidado reutiliza la prosa ya generada por el modo por-decisión.
        """
        cache_key = self._decision_key(decision)
        cached = self._raw_cache.get(cache_key)
        if cached is not None:
            logger.debug("ADR reutilizado de caché para '{title}'", title=decision.title)
            return cached

        sources_block = (
            registry.build_sources_block() if registry.size > 0 else "(sin evidencia documental)"
        )

        prompt = self._prompt_template.format(
            decision_title=decision.title,
            decision_description=decision.description,
            decision_rationale=decision.rationale or "No especificada",
            decision_owners=", ".join(decision.owners) if decision.owners else "No especificados",
            decision_tags=", ".join(decision.tags) if decision.tags else "Sin tags",
            sources_block=sources_block,
        )

        raw = self.provider.complete_structured(
            prompt=prompt,
            schema=_RawADR,
            system=(
                "Eres un arquitecto técnico experto en documentar decisiones de diseño de software. "
                "Redacta con precisión técnica y claridad. Usa solo los marcadores #N para citar fuentes."
            ),
        )

        logger.debug(
            "ADR generado para '{title}': context={c} chars, consequences={k} chars",
            title=decision.title,
            c=len(raw.context_md),
            k=len(raw.consequences_md),
        )
        self._raw_cache[cache_key] = raw
        return raw

    @staticmethod
    def _decision_key(decision: Decision) -> str:
        """Clave de caché por contenido de la decisión (título + descripción + fuentes)."""
        sources = "|".join(f"{s.source_path}:{s.line_start}-{s.line_end}" for s in decision.sources)
        return f"{decision.title}\x1f{decision.description}\x1f{sources}"
