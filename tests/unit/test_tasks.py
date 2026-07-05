"""Tests de la agregación global de tareas (UX-7)."""

from __future__ import annotations

import json
from pathlib import Path

from meeting_forge import tasks as tasks_mod


def _write_meeting(
    outputs_dir: Path, meeting_id: str, action_items: list[dict[str, object]]
) -> None:
    meeting_dir = outputs_dir / meeting_id
    meeting_dir.mkdir(parents=True)
    result = {
        "insights": {
            "decisions": [],
            "action_items": action_items,
            "topics": [],
            "summary": "",
        }
    }
    (meeting_dir / f"{meeting_id}_result.json").write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8"
    )


class TestTaskKey:
    def test_stable_and_position_independent(self) -> None:
        k1 = tasks_mod.task_key("m1", "  Hacer X  ")
        k2 = tasks_mod.task_key("m1", "Hacer X")
        assert k1 == k2
        assert k1.startswith("m1:")

    def test_different_meeting_different_key(self) -> None:
        assert tasks_mod.task_key("m1", "Hacer X") != tasks_mod.task_key("m2", "Hacer X")


class TestAggregate:
    def test_aggregates_across_meetings(self, tmp_path: Path) -> None:
        _write_meeting(
            tmp_path,
            "m1",
            [{"description": "Tarea A", "assignee": "Ana", "deadline": "2026-08-01"}],
        )
        _write_meeting(tmp_path, "m2", [{"description": "Tarea B", "assignee": None}])

        tasks = tasks_mod.aggregate_tasks(tmp_path)

        assert {t.description for t in tasks} == {"Tarea A", "Tarea B"}
        by_desc = {t.description: t for t in tasks}
        assert by_desc["Tarea A"].assignee == "Ana"
        assert by_desc["Tarea A"].meeting_id == "m1"
        assert by_desc["Tarea B"].assignee is None
        assert all(not t.done for t in tasks)

    def test_skips_blank_descriptions(self, tmp_path: Path) -> None:
        _write_meeting(tmp_path, "m1", [{"description": "   "}, {"description": "Válida"}])
        tasks = tasks_mod.aggregate_tasks(tmp_path)
        assert [t.description for t in tasks] == ["Válida"]

    def test_ignores_unreadable_result(self, tmp_path: Path) -> None:
        (tmp_path / "roto").mkdir()
        (tmp_path / "roto" / "roto_result.json").write_text("{no json", encoding="utf-8")
        _write_meeting(tmp_path, "m1", [{"description": "Buena"}])
        assert [t.description for t in tasks_mod.aggregate_tasks(tmp_path)] == ["Buena"]

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        assert tasks_mod.aggregate_tasks(tmp_path / "nada") == []


class TestStatusPersistence:
    def test_set_done_persists_and_reflects_in_aggregate(self, tmp_path: Path) -> None:
        _write_meeting(tmp_path, "m1", [{"description": "Tarea A"}])
        key = tasks_mod.aggregate_tasks(tmp_path)[0].key

        tasks_mod.set_task_done(tmp_path, key, True)

        assert tasks_mod.load_task_status(tmp_path)[key] is True
        assert tasks_mod.aggregate_tasks(tmp_path)[0].done is True

    def test_save_leaves_no_tmp_files(self, tmp_path: Path) -> None:
        tasks_mod.save_task_status(tmp_path, {"m1:abc": True})
        assert not list(tmp_path.glob(".tasks_*.tmp"))

    def test_unreadable_status_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "tasks.json").write_text("{bad", encoding="utf-8")
        assert tasks_mod.load_task_status(tmp_path) == {}


class TestFiltersAndCsv:
    def test_filter_by_assignee(self, tmp_path: Path) -> None:
        _write_meeting(
            tmp_path,
            "m1",
            [
                {"description": "A", "assignee": "Ana"},
                {"description": "B", "assignee": "Luis"},
            ],
        )
        tasks = tasks_mod.aggregate_tasks(tmp_path)
        assert tasks_mod.distinct_assignees(tasks) == ["Ana", "Luis"]
        only_ana = tasks_mod.filter_by_assignee(tasks, "Ana")
        assert [t.description for t in only_ana] == ["A"]
        assert tasks_mod.filter_by_assignee(tasks, None) == tasks

    def test_csv_has_header_and_rows(self, tmp_path: Path) -> None:
        _write_meeting(tmp_path, "m1", [{"description": "A", "assignee": "Ana"}])
        csv_text = tasks_mod.tasks_to_csv(tasks_mod.aggregate_tasks(tmp_path))
        lines = csv_text.strip().splitlines()
        assert lines[0] == "reunion,descripcion,asignado,deadline,estado"
        assert "A" in lines[1] and "Ana" in lines[1] and "pendiente" in lines[1]
