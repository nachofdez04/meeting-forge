"""Métricas agregadas para la pantalla de inicio de la UI (UX-10).

Da una visión de conjunto que hoy no existe: cuántas reuniones hay, cuántos documentos esperan
validación, cuántas tareas siguen abiertas y las más recientes. Lógica pura sobre los ficheros de
`data/outputs/`; la UI solo pinta las tarjetas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .tasks import aggregate_tasks
from .ui.loader import MeetingSummary, list_meetings
from .validation import store as validation_store
from .validation.schemas import ValidationStatus


@dataclass
class DashboardStats:
    """Resumen para la pantalla de inicio."""

    n_meetings: int = 0
    n_pending_docs: int = 0
    n_open_tasks: int = 0
    n_total_tasks: int = 0
    recent: list[MeetingSummary] = field(default_factory=list)


def _pending_docs_in_meeting(meeting_dir: Path) -> int:
    """Documentos generados de la reunión sin decidir (sin registro o en estado PENDING)."""
    from .ui.loader import load_generated_docs  # import perezoso (evita ciclo con la UI)

    docs = load_generated_docs(meeting_dir)
    if not docs:
        return 0
    state = validation_store.load_state(meeting_dir)
    pending = 0
    for doc in docs:
        record = state.records.get(doc.filename)
        if record is None or record.status == ValidationStatus.PENDING:
            pending += 1
    return pending


def compute_stats(outputs_dir: Path, recent_limit: int = 5) -> DashboardStats:
    """Calcula las métricas de la pantalla de inicio a partir de `data/outputs/`."""
    meetings = list_meetings(outputs_dir)
    tasks = aggregate_tasks(outputs_dir)
    pending_docs = sum(_pending_docs_in_meeting(m.meeting_dir) for m in meetings)
    return DashboardStats(
        n_meetings=len(meetings),
        n_pending_docs=pending_docs,
        n_open_tasks=sum(1 for t in tasks if not t.done),
        n_total_tasks=len(tasks),
        recent=meetings[:recent_limit],
    )
