"""Tests de la conversión insights ⇄ filas editables (UX-5)."""

from __future__ import annotations

from meeting_forge.analysis.insights_editing import (
    actions_to_rows,
    decisions_to_rows,
    rows_to_actions,
    rows_to_decisions,
)
from meeting_forge.analysis.schemas import ActionItem, Decision
from meeting_forge.rag.schemas import SourceRef


def _ref(path: str = "docs/a.md") -> SourceRef:
    return SourceRef(source_path=path, line_start=1, line_end=5)


def _decisions() -> list[Decision]:
    return [
        Decision(
            title="D1",
            description="desc 1",
            rationale="porque sí",
            owners=["Ana", "Luis"],
            tags=["rag"],
            sources=[_ref("docs/a.md")],
        ),
        Decision(title="D2", description="desc 2", sources=[_ref("docs/b.md")]),
    ]


class TestDecisionsRoundtrip:
    def test_unedited_rows_roundtrip(self) -> None:
        original = _decisions()
        restored = rows_to_decisions(decisions_to_rows(original), original)
        assert restored == original

    def test_edited_title_keeps_sources(self) -> None:
        original = _decisions()
        rows = decisions_to_rows(original)
        rows[0]["Título"] = "D1 corregida"
        restored = rows_to_decisions(rows, original)
        assert restored[0].title == "D1 corregida"
        assert restored[0].sources == original[0].sources

    def test_deleting_a_row_keeps_other_sources_aligned(self) -> None:
        # Al borrar la primera fila, la segunda conserva SUS fuentes (mapeo por columna `#`,
        # no por posición).
        original = _decisions()
        rows = decisions_to_rows(original)[1:]
        restored = rows_to_decisions(rows, original)
        assert len(restored) == 1
        assert restored[0].title == "D2"
        assert restored[0].sources[0].source_path == "docs/b.md"

    def test_new_row_has_no_sources(self) -> None:
        original = _decisions()
        rows = decisions_to_rows(original)
        rows.append({"Título": "Nueva", "Descripción": "añadida a mano"})
        restored = rows_to_decisions(rows, original)
        assert restored[-1].title == "Nueva"
        assert restored[-1].sources == []

    def test_blank_rows_are_dropped(self) -> None:
        original = _decisions()
        rows = decisions_to_rows(original)
        rows.append({"Título": "  ", "Descripción": ""})
        assert len(rows_to_decisions(rows, original)) == len(original)

    def test_missing_title_uses_description_prefix(self) -> None:
        restored = rows_to_decisions([{"Título": "", "Descripción": "solo descripción"}], [])
        assert restored[0].title == "solo descripción"

    def test_owner_and_tag_csv_parsing(self) -> None:
        rows = [{"Título": "T", "Descripción": "d", "Responsables": " Ana ,, Luis ", "Tags": ""}]
        restored = rows_to_decisions(rows, [])
        assert restored[0].owners == ["Ana", "Luis"]
        assert restored[0].tags == []

    def test_float_row_id_from_data_editor(self) -> None:
        # st.data_editor puede devolver la columna `#` como float.
        original = _decisions()
        rows = decisions_to_rows(original)
        rows[1]["#"] = 1.0
        restored = rows_to_decisions(rows, original)
        assert restored[1].sources[0].source_path == "docs/b.md"


class TestActionsRoundtrip:
    def test_roundtrip_and_empty_fields(self) -> None:
        original = [
            ActionItem(description="Tarea 1", assignee="Ana", deadline="2026-08-01"),
            ActionItem(description="Tarea 2", sources=[_ref()]),
        ]
        restored = rows_to_actions(actions_to_rows(original), original)
        assert restored == original

    def test_blank_description_dropped(self) -> None:
        rows = [{"Descripción": "   ", "Asignado": "Ana"}]
        assert rows_to_actions(rows, []) == []

    def test_empty_assignee_and_deadline_become_none(self) -> None:
        rows = [{"Descripción": "Hacer algo", "Asignado": " ", "Deadline": ""}]
        restored = rows_to_actions(rows, [])
        assert restored[0].assignee is None
        assert restored[0].deadline is None
