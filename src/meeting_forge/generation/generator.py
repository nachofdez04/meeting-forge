"""Orquestador del módulo de generación: enruta por modo y agrega resultados."""

from __future__ import annotations

from loguru import logger

from ..analysis.llm_client import LLMProvider
from ..analysis.schemas import MeetingInsights
from .acta_strategy import ActaStrategy
from .adr_strategy import AdrStrategy
from .schemas import GeneratedDocument, GenerationMode, MeetingMetadata


class DocumentGenerator:
    """Genera ADRs y actas a partir de MeetingInsights resueltos.

    Uso típico::

        gen = DocumentGenerator()
        docs = gen.generate(insights, metadata, modes=[GenerationMode.ADR_PER_DECISION, GenerationMode.ACTA])
        for doc in docs:
            doc.write_to(output_dir / doc.kind.value)
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        adr_prompt_version: str = "v1",
    ) -> None:
        self._adr = AdrStrategy(provider=provider, prompt_version=adr_prompt_version)
        self._acta = ActaStrategy()

    # ------------------------------------------------------------------
    # Entry point principal
    # ------------------------------------------------------------------

    def generate(
        self,
        insights: MeetingInsights,
        metadata: MeetingMetadata,
        modes: list[GenerationMode],
    ) -> list[GeneratedDocument]:
        """Genera los documentos para los modos solicitados.

        El orden de los documentos en la lista de retorno sigue el orden de `modes`.
        Si un modo no produce ningún documento (ej. consolidated sin decisiones), se omite.
        """
        if not modes:
            logger.warning("generate() llamado sin modos — no se produce ningún documento")
            return []

        logger.info(
            "Iniciando generación: {n} modo(s) — {modes}",
            n=len(modes),
            modes=[m.value for m in modes],
        )

        docs: list[GeneratedDocument] = []

        for mode in modes:
            try:
                new_docs = self._dispatch(mode, insights, metadata)
                docs.extend(new_docs)
                logger.info(
                    "Modo {mode}: {n} documento(s) generado(s)",
                    mode=mode.value,
                    n=len(new_docs),
                )
            except Exception as exc:
                logger.error(
                    "Error generando modo {mode}: {e}. Se omite y se continúa.",
                    mode=mode.value,
                    e=exc,
                )

        logger.info("Generación completada: {total} documento(s) en total", total=len(docs))
        return docs

    # ------------------------------------------------------------------
    # Acceso directo a cada modo (útil para tests y uso programático)
    # ------------------------------------------------------------------

    def generate_adr_per_decision(
        self,
        insights: MeetingInsights,
        metadata: MeetingMetadata,
    ) -> list[GeneratedDocument]:
        """Un ADR por cada Decision en MeetingInsights."""
        return self._adr.generate_per_decision(insights, metadata)

    def generate_adr_consolidated(
        self,
        insights: MeetingInsights,
        metadata: MeetingMetadata,
    ) -> GeneratedDocument | None:
        """ADR consolidado de la reunión; None si no hay decisiones."""
        return self._adr.generate_consolidated(insights, metadata)

    def generate_acta(
        self,
        insights: MeetingInsights,
        metadata: MeetingMetadata,
    ) -> GeneratedDocument:
        """Acta de la reunión (siempre produce un documento, incluso si insights está vacío)."""
        return self._acta.generate(insights, metadata)

    # ------------------------------------------------------------------
    # Dispatcher interno
    # ------------------------------------------------------------------

    def _dispatch(
        self,
        mode: GenerationMode,
        insights: MeetingInsights,
        metadata: MeetingMetadata,
    ) -> list[GeneratedDocument]:
        if mode == GenerationMode.ADR_PER_DECISION:
            return self.generate_adr_per_decision(insights, metadata)

        if mode == GenerationMode.ADR_CONSOLIDATED:
            doc = self.generate_adr_consolidated(insights, metadata)
            return [doc] if doc is not None else []

        if mode == GenerationMode.ACTA:
            return [self.generate_acta(insights, metadata)]

        raise ValueError(f"Modo de generación desconocido: {mode!r}")
