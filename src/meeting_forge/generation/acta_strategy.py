"""Estrategia de generación de actas de reunión.

100% determinístico (cero llamadas LLM): recompone los MeetingInsights ya estructurados
en un Markdown de acta con footnotes [^N] apuntando a los SourceRef existentes.
"""

from __future__ import annotations

from loguru import logger

from ..analysis.schemas import MeetingInsights
from .citations import CitationRegistry, render_footnote_block
from .filenames import build_acta_filename
from .schemas import DocumentKind, GeneratedDocument, GenerationMode, MeetingMetadata
from .templates import render_acta


class ActaStrategy:
    """Genera el acta de una reunión a partir de MeetingInsights (sin LLM)."""

    def generate(
        self,
        insights: MeetingInsights,
        metadata: MeetingMetadata,
    ) -> GeneratedDocument:
        """Genera el acta Markdown de la reunión."""
        logger.info(
            "Generando acta para '{meeting}' ({d} decisiones, {a} tareas)",
            meeting=metadata.title or metadata.meeting_id,
            d=len(insights.decisions),
            a=len(insights.action_items),
        )

        # El registry se construye durante el render (render_acta lo rellena vía citations)
        registry = CitationRegistry()

        # Pre-registrar todos los sources en orden de aparición para numerar
        # consistentemente antes de que render_acta los procese
        for decision in insights.decisions:
            registry.register_all(decision.sources)
        for action in insights.action_items:
            registry.register_all(action.sources)

        # Render determinístico: devuelve el markdown y los índices realmente usados
        markdown_body, used_indices = render_acta(insights, metadata, registry)

        # Bloque de footnotes sólo si hay citas reales
        footnote_block = render_footnote_block(registry, used_indices)
        if footnote_block:
            markdown = markdown_body.rstrip() + "\n\n## Referencias\n\n" + footnote_block + "\n"
        else:
            markdown = markdown_body.rstrip() + "\n"

        # Recopilar sources únicas usadas
        all_sources = [
            s
            for d in insights.decisions
            for s in d.sources
        ] + [
            s
            for a in insights.action_items
            for s in a.sources
        ]
        unique_sources = list(
            {(s.source_path, s.line_start, s.line_end): s for s in all_sources}.values()
        )

        logger.info(
            "Acta generada: {lines} líneas, {refs} citas",
            lines=markdown.count("\n"),
            refs=len(used_indices),
        )

        return GeneratedDocument(
            filename=build_acta_filename(metadata),
            kind=DocumentKind.ACTA,
            mode=GenerationMode.ACTA,
            markdown_content=markdown,
            sources_used=unique_sources,
            decision_titles=[d.title for d in insights.decisions],
        )
