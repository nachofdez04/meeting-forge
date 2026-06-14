"""Tests del generador de reunión de demostración (F10)."""

from __future__ import annotations

from pathlib import Path

from meeting_forge.demo import DEMO_MEETING_ID, build_demo_meeting
from meeting_forge.ui.loader import load_generated_docs, load_meeting


class TestBuildDemoMeeting:
    def test_creates_loadable_meeting(self, tmp_path: Path) -> None:
        meeting_dir = build_demo_meeting(tmp_path)
        assert meeting_dir.name == DEMO_MEETING_ID

        data = load_meeting(meeting_dir)
        assert len(data.insights.decisions) >= 1
        assert len(data.insights.action_items) >= 1
        assert data.metadata.get("provider") == "demo"
        assert data.transcript_segments  # hay segmentos de transcripción de muestra

    def test_generates_acta(self, tmp_path: Path) -> None:
        meeting_dir = build_demo_meeting(tmp_path)
        docs = load_generated_docs(meeting_dir)
        assert any(d.kind == "acta" for d in docs)

    def test_idempotent(self, tmp_path: Path) -> None:
        build_demo_meeting(tmp_path)
        meeting_dir = build_demo_meeting(tmp_path)  # reejecutar no debe fallar
        assert (meeting_dir / f"{DEMO_MEETING_ID}_result.json").exists()
