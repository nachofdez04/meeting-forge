"""Tests de las métricas de la pantalla de inicio (UX-10)."""

from __future__ import annotations

import json
from pathlib import Path

from meeting_forge import dashboard
from meeting_forge.generation.schemas import DocumentKind, GeneratedDocument, GenerationMode
from meeting_forge.validation import store as val_store


def _write_meeting(
    outputs_dir: Path,
    meeting_id: str,
    *,
    decisions: int = 0,
    actions: list[dict[str, object]] | None = None,
) -> Path:
    meeting_dir = outputs_dir / meeting_id
    meeting_dir.mkdir(parents=True)
    result = {
        "insights": {
            "decisions": [{"title": f"D{i}", "description": "x"} for i in range(decisions)],
            "action_items": actions or [],
            "topics": [],
            "summary": "",
        }
    }
    (meeting_dir / f"{meeting_id}_result.json").write_text(json.dumps(result), encoding="utf-8")
    return meeting_dir


def _add_acta(meeting_dir: Path, filename: str) -> GeneratedDocument:
    doc = GeneratedDocument(
        filename=filename,
        kind=DocumentKind.ACTA,
        mode=GenerationMode.ACTA,
        markdown_content="# Acta\n",
    )
    doc.write_to(meeting_dir / "acta")
    return doc


def test_empty_outputs_dir(tmp_path: Path) -> None:
    stats = dashboard.compute_stats(tmp_path / "nada")
    assert stats.n_meetings == 0
    assert stats.recent == []


def test_counts_meetings_and_tasks(tmp_path: Path) -> None:
    _write_meeting(
        tmp_path,
        "m1",
        decisions=2,
        actions=[{"description": "T1"}, {"description": "T2"}],
    )
    _write_meeting(tmp_path, "m2", actions=[{"description": "T3"}])

    stats = dashboard.compute_stats(tmp_path)

    assert stats.n_meetings == 2
    assert stats.n_total_tasks == 3
    assert stats.n_open_tasks == 3  # ninguna marcada hecha


def test_pending_docs_counts_unvalidated(tmp_path: Path) -> None:
    meeting_dir = _write_meeting(tmp_path, "m1")
    _add_acta(meeting_dir, "acta-1.md")
    _add_acta(meeting_dir, "acta-2.md")

    # Sin validation.json: ambos documentos cuentan como pendientes.
    assert dashboard.compute_stats(tmp_path).n_pending_docs == 2

    # Aprobar uno reduce el pendiente a 1.
    state = val_store.mark_approved(val_store.load_state(meeting_dir), "acta-1.md")
    val_store.save_state(meeting_dir, state)
    assert dashboard.compute_stats(tmp_path).n_pending_docs == 1


def test_open_tasks_excludes_done(tmp_path: Path) -> None:
    from meeting_forge import tasks as tasks_mod

    _write_meeting(tmp_path, "m1", actions=[{"description": "T1"}, {"description": "T2"}])
    key = tasks_mod.aggregate_tasks(tmp_path)[0].key
    tasks_mod.set_task_done(tmp_path, key, True)

    stats = dashboard.compute_stats(tmp_path)
    assert stats.n_total_tasks == 2
    assert stats.n_open_tasks == 1


def test_recent_is_limited(tmp_path: Path) -> None:
    for i in range(7):
        _write_meeting(tmp_path, f"m{i}")
    stats = dashboard.compute_stats(tmp_path, recent_limit=3)
    assert len(stats.recent) == 3
