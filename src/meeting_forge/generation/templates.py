"""Templates de string para generar el esqueleto de ADRs y actas.

Utiliza str.format puro (sin Jinja2) para mantener las dependencias mínimas.
El LLM rellena las secciones de prosa de los ADRs; las actas son 100% determinísticas.
"""

from __future__ import annotations

from ..analysis.schemas import ActionItem, Decision, MeetingInsights
from .citations import CitationRegistry, escape_user_text
from .schemas import MeetingMetadata

# ---------------------------------------------------------------------------
# ADR skeleton
# ---------------------------------------------------------------------------

_ADR_SKELETON = """\
# ADR: {title}

| Campo | Valor |
|---|---|
| **Estado** | {status} |
| **Fecha** | {date} |
| **Responsables** | {owners} |
| **Tags** | {tags} |

## Contexto

{context_md}

## Decisión

{decision_md}

## Consecuencias

{consequences_md}
"""

_ADR_SKELETON_WITH_REFS = _ADR_SKELETON + """
## Referencias

{footnote_block}
"""

_ADR_CONSOLIDATED_HEADER = """\
# ADR Consolidado: {title}

> Reunión: {meeting_title}
> Fecha: {date}
> Decisiones: {n_decisions}

"""

_ADR_CONSOLIDATED_SECTION = """\
---

## Decisión {counter}: {title}

"""


def render_adr_skeleton(
    *,
    title: str,
    status: str,
    date: str,
    owners: str,
    tags: str,
    context_md: str,
    decision_md: str,
    consequences_md: str,
    footnote_block: str,
) -> str:
    """Ensambla el Markdown final de un ADR a partir de sus partes."""
    template = _ADR_SKELETON_WITH_REFS if footnote_block else _ADR_SKELETON
    return template.format(
        title=title,
        status=status,
        date=date or "—",
        owners=owners or "—",
        tags=tags or "—",
        context_md=context_md,
        decision_md=decision_md,
        consequences_md=consequences_md,
        footnote_block=footnote_block,
    ).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Acta template (100% determinístico, cero llamadas LLM)
# ---------------------------------------------------------------------------


def _format_source_inline(index: int) -> str:
    return f"[^{index}]"


def render_acta(
    insights: MeetingInsights,
    metadata: MeetingMetadata,
    registry: CitationRegistry,
) -> tuple[str, set[int]]:
    """Renderiza el acta completa de la reunión. Devuelve (markdown, used_indices).

    Los SourceRef de cada Decision/ActionItem ya están en el registry (pre-registrados
    por el caller). Esta función sólo construye el Markdown inline y rastrea qué índices usa.
    """
    used: set[int] = set()
    lines: list[str] = []

    # --- Cabecera ---
    meeting_title = metadata.title or metadata.meeting_id
    lines.append(f"# Acta de reunión: {escape_user_text(meeting_title)}\n")
    if metadata.date:
        lines.append(f"**Fecha**: {metadata.date}  ")
    if metadata.attendees:
        lines.append(f"**Asistentes**: {', '.join(metadata.attendees)}  ")
    lines.append("")

    # --- Resumen ejecutivo ---
    lines.append("## Resumen ejecutivo\n")
    if insights.summary:
        lines.append(escape_user_text(insights.summary))
    else:
        lines.append("_(sin resumen disponible)_")
    lines.append("")

    # --- Temas ---
    if insights.topics:
        lines.append("## Temas tratados\n")
        for topic in insights.topics:
            lines.append(f"- {escape_user_text(topic)}")
        lines.append("")

    # --- Decisiones ---
    lines.append("## Decisiones\n")
    if not insights.decisions:
        lines.append("_(sin decisiones registradas)_\n")
    else:
        for i, decision in enumerate(insights.decisions, start=1):
            _render_decision(decision, i, registry, used, lines)

    # --- Action items ---
    lines.append("## Tareas pendientes\n")
    if not insights.action_items:
        lines.append("_(sin tareas registradas)_\n")
    else:
        for action in insights.action_items:
            _render_action_item(action, registry, used, lines)

    return "\n".join(lines), used


def _render_decision(
    decision: Decision,
    counter: int,
    registry: CitationRegistry,
    used: set[int],
    lines: list[str],
) -> None:
    # Inline citation markers after the title
    citations = ""
    if decision.sources:
        indices = [registry.register(s) for s in decision.sources]
        used.update(indices)
        citations = "".join(_format_source_inline(i) for i in indices)

    lines.append(f"### {counter}. {escape_user_text(decision.title)}{citations}\n")

    if decision.description:
        lines.append(escape_user_text(decision.description))
        lines.append("")

    if decision.rationale:
        lines.append(f"**Justificación**: {escape_user_text(decision.rationale)}")
        lines.append("")

    if decision.owners:
        lines.append(f"**Responsables**: {', '.join(decision.owners)}")
    if decision.tags:
        lines.append(f"**Tags**: {', '.join(f'`{t}`' for t in decision.tags)}")
    lines.append("")


def _render_action_item(
    action: ActionItem,
    registry: CitationRegistry,
    used: set[int],
    lines: list[str],
) -> None:
    citations = ""
    if action.sources:
        indices = [registry.register(s) for s in action.sources]
        used.update(indices)
        citations = " " + "".join(_format_source_inline(i) for i in indices)

    parts = [f"- {escape_user_text(action.description)}{citations}"]
    details: list[str] = []
    if action.assignee:
        details.append(f"@{action.assignee}")
    if action.deadline:
        details.append(f"deadline: {action.deadline}")
    if details:
        parts.append(f"  _({', '.join(details)})_")
    lines.extend(parts)
