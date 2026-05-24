"""Extracción de insights de transcripciones usando LLMs."""

from loguru import logger

from ..config import settings
from ..ingestion.schemas import Transcript
from .llm_client import LLMProvider, get_provider
from .schemas import MeetingInsights

_DEFAULT_PROMPT = """
Analiza la siguiente transcripción de una reunión técnica y extrae:

1. **Decisiones técnicas**: Cualquier decisión de arquitectura, tecnología o estrategia.
2. **Tareas pendientes**: Acciones asignadas a personas o equipos.
3. **Temas principales**: Los tópicos centrales de la discusión.
4. **Resumen ejecutivo**: Un párrafo que sintetice lo más importante.

Transcripción:
{transcript}
"""


class InsightsExtractor:
    """Extrae decisiones, tareas y temas de una transcripción."""

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider: LLMProvider = provider or get_provider()
        self.prompt_template = self._load_prompt()

    def _load_prompt(self) -> str:
        """Carga el prompt v1 desde archivo, o el fallback inline."""
        prompt_path = settings.prompts_dir / "extraction" / "v1.md"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        logger.warning("Prompt no encontrado en {p}, usando default", p=prompt_path)
        return _DEFAULT_PROMPT

    def extract(self, transcript: Transcript) -> MeetingInsights:
        """Extrae insights de una transcripción.

        Args:
            transcript: Transcripción a analizar.

        Returns:
            MeetingInsights estructurado.
        """
        logger.info("Extrayendo insights con LLM")
        prompt = self.prompt_template.format(transcript=transcript.to_text())

        insights = self.provider.complete_structured(
            prompt=prompt,
            schema=MeetingInsights,
            system=(
                "Eres un asistente experto en analizar reuniones técnicas y "
                "extraer información estructurada."
            ),
        )

        logger.info(
            "Insights extraídos: {d} decisiones, {a} tareas",
            d=len(insights.decisions),
            a=len(insights.action_items),
        )
        return insights
