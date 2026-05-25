"""Tests de git_integration/templates.py."""

from __future__ import annotations

from meeting_forge.git_integration.templates import (
    build_branch_name,
    build_commit_message,
    build_pr_body,
    build_pr_title,
)


class TestBuildBranchName:
    def test_basic(self) -> None:
        name = build_branch_name("meeting-forge/", "sprint-planning", "2026-05-25")
        assert name == "meeting-forge/sprint-planning-2026-05-25"

    def test_no_date(self) -> None:
        name = build_branch_name("meeting-forge/", "sprint-planning", None)
        assert name == "meeting-forge/sprint-planning"

    def test_special_chars_in_meeting_id(self) -> None:
        name = build_branch_name("prefix/", "Reunión técnica & diseño", "2026-01-01")
        assert " " not in name
        assert "&" not in name

    def test_does_not_end_with_slash_or_dot(self) -> None:
        name = build_branch_name("meeting-forge/", "test", None)
        assert not name.endswith("/")
        assert not name.endswith(".")

    def test_long_meeting_id_truncated(self) -> None:
        long_id = "a" * 200
        name = build_branch_name("p/", long_id, None)
        assert len(name) < 120


class TestBuildCommitMessage:
    def test_singular(self) -> None:
        msg = build_commit_message("Sprint Planning", 1)
        assert msg == "docs(meetings): Sprint Planning (1 doc)"

    def test_plural(self) -> None:
        msg = build_commit_message("Sprint Planning", 3)
        assert msg == "docs(meetings): Sprint Planning (3 docs)"


class TestBuildPrTitle:
    def test_basic(self) -> None:
        title = build_pr_title("Sprint Planning", 2)
        assert "[MeetingForge]" in title
        assert "Sprint Planning" in title
        assert "2 docs" in title


class TestBuildPrBody:
    def test_contains_meeting_id(self) -> None:
        body = build_pr_body("sprint-2026", "2026-05-25", ["docs/meetings/f1.md"])
        assert "sprint-2026" in body
        assert "2026-05-25" in body
        assert "f1.md" in body

    def test_no_date(self) -> None:
        body = build_pr_body("my-meeting", None, [])
        assert "my-meeting" in body
