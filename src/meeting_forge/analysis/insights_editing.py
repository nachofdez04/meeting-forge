"""Conversión insights ⇄ filas editables para la UI (UX-5).

La pestaña Insights edita decisiones y tareas con `st.data_editor` (filas añadibles y
borrables). Estos helpers son puros y testeables: convierten los modelos a filas de dict y
reconstruyen los modelos desde las filas editadas. La columna oculta `#` (índice original)
permite **preservar las fuentes (SourceRef)** de cada fila aunque el usuario borre o reordene
otras: las citas no son editables a mano, pero no deben perderse al corregir un título.
"""

from __future__ import annotations

from loguru import logger

from .schemas import ActionItem, Decision

_ID_COL = "#"


def _split_csv(raw: object) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _row_id(row: dict[str, object]) -> int | None:
    """Índice original de la fila, o None si es una fila nueva (o el valor no es usable)."""
    raw = row.get(_ID_COL)
    if raw is None or raw == "":
        return None
    try:
        return int(float(str(raw)))  # data_editor puede devolverlo como int, float o str
    except (TypeError, ValueError):
        return None


def decisions_to_rows(decisions: list[Decision]) -> list[dict[str, object]]:
    """Convierte las decisiones a filas para `st.data_editor`."""
    return [
        {
            _ID_COL: i,
            "Título": d.title,
            "Descripción": d.description,
            "Justificación": d.rationale or "",
            "Responsables": ", ".join(d.owners),
            "Tags": ", ".join(d.tags),
        }
        for i, d in enumerate(decisions)
    ]


def rows_to_decisions(rows: list[dict[str, object]], original: list[Decision]) -> list[Decision]:
    """Reconstruye las decisiones desde las filas editadas.

    - Filas sin título ni descripción se descartan (con warning).
    - Una fila sin título toma el inicio de la descripción como título.
    - Las fuentes se recuperan de la decisión original vía la columna `#` (filas nuevas: sin fuentes).
    """
    decisions: list[Decision] = []
    for row in rows:
        title = str(row.get("Título") or "").strip()
        description = str(row.get("Descripción") or "").strip()
        if not title and not description:
            logger.warning("Decisión vacía descartada al guardar la edición")
            continue
        if not title:
            title = description[:60]
        idx = _row_id(row)
        sources = original[idx].sources if idx is not None and 0 <= idx < len(original) else []
        rationale = str(row.get("Justificación") or "").strip()
        decisions.append(
            Decision(
                title=title,
                description=description or title,
                rationale=rationale or None,
                owners=_split_csv(row.get("Responsables")),
                tags=_split_csv(row.get("Tags")),
                sources=list(sources),
            )
        )
    return decisions


def actions_to_rows(actions: list[ActionItem]) -> list[dict[str, object]]:
    """Convierte las tareas a filas para `st.data_editor`."""
    return [
        {
            _ID_COL: i,
            "Descripción": a.description,
            "Asignado": a.assignee or "",
            "Deadline": a.deadline or "",
        }
        for i, a in enumerate(actions)
    ]


def rows_to_actions(rows: list[dict[str, object]], original: list[ActionItem]) -> list[ActionItem]:
    """Reconstruye las tareas desde las filas editadas (mismas reglas que las decisiones)."""
    actions: list[ActionItem] = []
    for row in rows:
        description = str(row.get("Descripción") or "").strip()
        if not description:
            logger.warning("Tarea vacía descartada al guardar la edición")
            continue
        idx = _row_id(row)
        sources = original[idx].sources if idx is not None and 0 <= idx < len(original) else []
        assignee = str(row.get("Asignado") or "").strip()
        deadline = str(row.get("Deadline") or "").strip()
        actions.append(
            ActionItem(
                description=description,
                assignee=assignee or None,
                deadline=deadline or None,
                sources=list(sources),
            )
        )
    return actions
