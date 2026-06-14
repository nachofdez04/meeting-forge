"""Estrategia de actualización de documentos: roadmap y documentación técnica (F5).

A diferencia de ADR/Acta (que crean documentos nuevos), esta estrategia produce la **versión
revisada completa** de un documento a partir de su contenido actual + los insights de la reunión, y
calcula el **diff** frente al original para que el usuario revise el cambio antes de publicarlo.
"""

from __future__ import annotations

from loguru import logger

from ..analysis.llm_client import LLMProvider, _strip_markdown_fences, get_provider
from ..analysis.schemas import MeetingInsights
from ..config import settings
from .diffing import unified_md_diff
from .schemas import DocumentKind, GeneratedDocument, GenerationMode, MeetingMetadata

_SYSTEM = (
    "Eres un asistente técnico que mantiene la documentación de un proyecto de software. "
    "Integras lo discutido en reuniones en documentos Markdown claros, sin inventar información."
)

_DEFAULT_ROADMAP_PROMPT = """\
Actualiza el ROADMAP del proyecto a partir de la reunión.

## Reunión
- Título: {meeting_title}
- Fecha: {date}

## Roadmap actual
{existing_document}

## Información de la reunión
{insights_block}

Devuelve el documento Markdown completo ya actualizado (sin diff ni explicaciones).
"""

_DEFAULT_TECH_DOC_PROMPT = """\
Actualiza la documentación técnica del proyecto a partir de la reunión.

## Reunión
- Título: {meeting_title}
- Fecha: {date}

## Documentación actual
{existing_document}

## Información de la reunión
{insights_block}

Devuelve el documento Markdown completo ya actualizado (sin diff ni explicaciones).
"""

# kind → (nombre de prompt, filename por defecto, modo, prompt fallback)
_KIND_CONFIG: dict[DocumentKind, tuple[str, str, GenerationMode, str]] = {
    DocumentKind.ROADMAP: (
        "roadmap",
        "roadmap.md",
        GenerationMode.ROADMAP_UPDATE,
        _DEFAULT_ROADMAP_PROMPT,
    ),
    DocumentKind.TECHNICAL_DOC: (
        "tech_doc",
        "technical-doc.md",
        GenerationMode.TECHNICAL_DOC_UPDATE,
        _DEFAULT_TECH_DOC_PROMPT,
    ),
}


def _insights_block(insights: MeetingInsights) -> str:
    """Resume los insights en texto plano para inyectar en el prompt."""
    lines: list[str] = []
    if insights.summary:
        lines.append(f"Resumen: {insights.summary}")
    if insights.topics:
        lines.append("Temas: " + ", ".join(insights.topics))
    if insights.decisions:
        lines.append("Decisiones:")
        for decision in insights.decisions:
            line = f"- {decision.title}: {decision.description}"
            if decision.rationale:
                line += f" (Justificación: {decision.rationale})"
            lines.append(line)
    if insights.action_items:
        lines.append("Tareas:")
        for action in insights.action_items:
            assignee = f" [@{action.assignee}]" if action.assignee else ""
            lines.append(f"- {action.description}{assignee}")
    return "\n".join(lines) if lines else "(sin insights)"


class UpdateStrategy:
    """Genera/actualiza roadmap y documentación técnica con diff frente al documento existente."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        prompt_version: str = "v1",
    ) -> None:
        self.provider: LLMProvider = provider or get_provider()
        self._prompt_version = prompt_version

    def generate(
        self,
        insights: MeetingInsights,
        metadata: MeetingMetadata,
        *,
        kind: DocumentKind,
        existing_content: str = "",
        target_filename: str | None = None,
    ) -> GeneratedDocument:
        """Produce la versión revisada del documento `kind` y su diff frente al original."""
        if kind not in _KIND_CONFIG:
            raise ValueError(f"UpdateStrategy no soporta el kind {kind!r}")
        prompt_name, default_filename, mode, fallback = _KIND_CONFIG[kind]

        template = self._load_prompt(prompt_name, fallback)
        prompt = template.format(
            meeting_title=metadata.title or metadata.meeting_id,
            date=metadata.date or "—",
            existing_document=existing_content or "(todavía no existe; créalo desde cero)",
            insights_block=_insights_block(insights),
        )

        raw = self.provider.complete(prompt, system=_SYSTEM)
        revised = _strip_markdown_fences(raw).strip() + "\n"

        filename = target_filename or default_filename
        diff = unified_md_diff(existing_content, revised, filename) if existing_content else ""

        logger.info(
            "Documento '{kind}' generado ({n} líneas, diff={d})",
            kind=kind.value,
            n=revised.count("\n"),
            d="sí" if diff else "no",
        )

        return GeneratedDocument(
            filename=filename,
            kind=kind,
            mode=mode,
            markdown_content=revised,
            decision_titles=[d.title for d in insights.decisions],
            diff=diff or None,
        )

    def _load_prompt(self, name: str, fallback: str) -> str:
        path = settings.prompts_dir / "generation" / f"{name}_{self._prompt_version}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        logger.warning("Prompt no encontrado en {p}, usando default", p=path)
        return fallback
