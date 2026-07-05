"""Agregación global de tareas de todas las reuniones (UX-7).

Los `action_items` extraídos se quedan enterrados dentro de cada `result.json`. Este módulo los
reúne en una sola vista con su reunión de origen, y persiste el estado hecha/pendiente en
`data/outputs/tasks.json` (clave estable: `meeting_id` + hash de la descripción, para que sobreviva
a reordenamientos y no dependa de la posición). Lógica pura y testeable: la UI solo pinta.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

_STATUS_FILENAME = "tasks.json"


@dataclass
class AggregatedTask:
    """Una tarea (action item) con su reunión de origen y su estado de completitud."""

    key: str
    meeting_id: str
    description: str
    assignee: str | None
    deadline: str | None
    done: bool


def task_key(meeting_id: str, description: str) -> str:
    """Clave estable de una tarea: `meeting_id` + hash del texto (independiente de la posición)."""
    digest = hashlib.sha1(description.strip().encode("utf-8")).hexdigest()[:12]
    return f"{meeting_id}:{digest}"


def load_task_status(outputs_dir: Path) -> dict[str, bool]:
    """Lee el mapa `key → done`; {} si no existe o es ilegible."""
    path = outputs_dir / _STATUS_FILENAME
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("tasks.json ilegible en {p}: {e}", p=path, e=exc)
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): bool(v) for k, v in raw.items()}


def save_task_status(outputs_dir: Path, status: dict[str, bool]) -> None:
    """Escribe el mapa de estados atómicamente (tmp + replace)."""
    outputs_dir.mkdir(parents=True, exist_ok=True)
    target = outputs_dir / _STATUS_FILENAME
    tmp = outputs_dir / f".tasks_{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def set_task_done(outputs_dir: Path, key: str, done: bool) -> dict[str, bool]:
    """Marca una tarea como hecha/pendiente y persiste. Devuelve el mapa actualizado."""
    status = load_task_status(outputs_dir)
    status[key] = done
    save_task_status(outputs_dir, status)
    return status


def _iter_action_items(outputs_dir: Path) -> list[tuple[str, dict[str, object]]]:
    """Recorre las reuniones y devuelve (meeting_id, action_item_dict) de cada tarea."""
    out: list[tuple[str, dict[str, object]]] = []
    if not outputs_dir.is_dir():
        return out
    for subdir in sorted(outputs_dir.iterdir()):
        if not subdir.is_dir():
            continue
        result_files = sorted(subdir.glob("*_result.json"))
        if not result_files:
            continue
        try:
            raw = json.loads(result_files[0].read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Ignorando {p} (result.json ilegible): {e}", p=result_files[0], e=exc)
            continue
        insights = raw.get("insights") if isinstance(raw, dict) else None
        items = insights.get("action_items") if isinstance(insights, dict) else None
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                out.append((subdir.name, item))
    return out


def aggregate_tasks(outputs_dir: Path) -> list[AggregatedTask]:
    """Reúne todas las tareas de todas las reuniones con su estado hecha/pendiente."""
    status = load_task_status(outputs_dir)
    tasks: list[AggregatedTask] = []
    for meeting_id, item in _iter_action_items(outputs_dir):
        description = str(item.get("description") or "").strip()
        if not description:
            continue
        assignee_raw = item.get("assignee")
        deadline_raw = item.get("deadline")
        key = task_key(meeting_id, description)
        tasks.append(
            AggregatedTask(
                key=key,
                meeting_id=meeting_id,
                description=description,
                assignee=str(assignee_raw) if assignee_raw else None,
                deadline=str(deadline_raw) if deadline_raw else None,
                done=status.get(key, False),
            )
        )
    return tasks


def filter_by_assignee(tasks: list[AggregatedTask], assignee: str | None) -> list[AggregatedTask]:
    """Filtra por asignado exacto; `None` o vacío = todas."""
    if not assignee:
        return tasks
    return [t for t in tasks if t.assignee == assignee]


def distinct_assignees(tasks: list[AggregatedTask]) -> list[str]:
    """Asignados presentes (ordenados), para poblar el filtro."""
    return sorted({t.assignee for t in tasks if t.assignee})


def tasks_to_csv(tasks: list[AggregatedTask]) -> str:
    """Serializa las tareas a CSV (para descargar desde la UI)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["reunion", "descripcion", "asignado", "deadline", "estado"])
    for t in tasks:
        writer.writerow(
            [
                t.meeting_id,
                t.description,
                t.assignee or "",
                t.deadline or "",
                "hecha" if t.done else "pendiente",
            ]
        )
    return buffer.getvalue()
