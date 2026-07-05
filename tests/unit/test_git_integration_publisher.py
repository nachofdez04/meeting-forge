"""Tests de git_integration/publisher.py (mocks de repo y pr)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from meeting_forge.generation.schemas import MeetingMetadata
from meeting_forge.git_integration import publisher as pub_module
from meeting_forge.git_integration.schemas import PublishResult
from meeting_forge.ui.loader import GeneratedDocView
from meeting_forge.validation import store as val_store
from meeting_forge.validation.schemas import MeetingValidationState

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git no disponible en el entorno"
)


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"], cwd=path, capture_output=True, check=True
    )
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, capture_output=True, check=True)
    (path / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, capture_output=True, check=True)
    return path


def _make_docs() -> list[GeneratedDocView]:
    return [
        GeneratedDocView(filename="adr-0001.md", kind="adr", markdown_content="# ADR original"),
        GeneratedDocView(filename="acta.md", kind="acta", markdown_content="# Acta"),
    ]


def _make_metadata(meeting_id: str = "sprint-2026") -> MeetingMetadata:
    return MeetingMetadata(meeting_id=meeting_id, title="Sprint 2026", date="2026-05-25")


class TestPublishMeeting:
    def test_publishes_approved_docs(self, tmp_path: Path) -> None:
        target_repo = _init_repo(tmp_path / "target")
        meeting_dir = tmp_path / "meeting"
        meeting_dir.mkdir()

        docs = _make_docs()
        state = val_store.initialize_pending(meeting_dir, docs)
        state = val_store.mark_approved(state, "adr-0001.md")
        state = val_store.mark_approved(state, "acta.md")
        val_store.save_state(meeting_dir, state)

        with (
            patch.object(
                pub_module.pr_module, "create_pr", return_value="https://github.com/pull/1"
            ),
            patch.object(pub_module.repo_module, "push"),
            patch.object(pub_module, "settings") as mock_settings,
        ):
            mock_settings.git_integration_enabled = True
            mock_settings.git_target_repo_path = target_repo
            mock_settings.git_target_remote = None
            mock_settings.git_base_branch = "main"
            mock_settings.git_branch_prefix = "meeting-forge/"
            mock_settings.git_docs_subdir = "docs/meetings"
            mock_settings.gh_executable = "gh"

            result = pub_module.publish_meeting(meeting_dir, _make_metadata(), state, docs)

        assert result.pr_url == "https://github.com/pull/1"
        assert len(result.files) == 2
        assert (meeting_dir / "publish.json").exists()

    def test_uses_edited_content(self, tmp_path: Path) -> None:
        target_repo = _init_repo(tmp_path / "target")
        meeting_dir = tmp_path / "meeting"
        meeting_dir.mkdir()

        docs = _make_docs()
        state = val_store.initialize_pending(meeting_dir, docs)
        state = val_store.mark_approved(state, "adr-0001.md", edited_content="# EDITADO")
        state = val_store.mark_rejected(state, "acta.md")
        val_store.save_state(meeting_dir, state)

        with (
            patch.object(
                pub_module.pr_module, "create_pr", return_value="https://github.com/pull/2"
            ),
            patch.object(pub_module.repo_module, "push"),
            patch.object(pub_module, "settings") as mock_settings,
        ):
            mock_settings.git_integration_enabled = True
            mock_settings.git_target_repo_path = target_repo
            mock_settings.git_target_remote = None
            mock_settings.git_base_branch = "main"
            mock_settings.git_branch_prefix = "meeting-forge/"
            mock_settings.git_docs_subdir = "docs/meetings"
            mock_settings.gh_executable = "gh"

            result = pub_module.publish_meeting(meeting_dir, _make_metadata(), state, docs)

        assert len(result.files) == 1
        committed_file = target_repo / result.files[0]
        assert committed_file.read_text(encoding="utf-8") == "# EDITADO"

    def test_raises_when_no_approved(self, tmp_path: Path) -> None:
        meeting_dir = tmp_path / "meeting"
        meeting_dir.mkdir()
        docs = _make_docs()
        state = MeetingValidationState()

        with (
            patch.object(pub_module, "settings") as mock_settings,
        ):
            mock_settings.git_integration_enabled = True
            mock_settings.git_target_repo_path = tmp_path / "repo"
            mock_settings.git_target_remote = None
            mock_settings.git_base_branch = "main"
            mock_settings.git_branch_prefix = "meeting-forge/"
            mock_settings.git_docs_subdir = "docs/meetings"
            mock_settings.gh_executable = "gh"

            with pytest.raises(pub_module.PublishError, match="No hay documentos aprobados"):
                pub_module.publish_meeting(meeting_dir, _make_metadata(), state, docs)

    def test_raises_when_disabled(self, tmp_path: Path) -> None:
        with patch.object(pub_module, "settings") as mock_settings:
            mock_settings.git_integration_enabled = False
            with pytest.raises(pub_module.PublishError, match="desactivada"):
                pub_module.publish_meeting(tmp_path, _make_metadata(), MeetingValidationState(), [])

    def test_publish_json_not_written_on_git_error(self, tmp_path: Path) -> None:
        meeting_dir = tmp_path / "meeting"
        meeting_dir.mkdir()
        docs = _make_docs()
        state = val_store.initialize_pending(meeting_dir, docs)
        state = val_store.mark_approved(state, "adr-0001.md")

        with (
            patch.object(pub_module, "settings") as mock_settings,
            patch.object(
                pub_module.repo_module,
                "ensure_repo",
                side_effect=pub_module.repo_module.GitOperationError("fail"),
            ),
        ):
            mock_settings.git_integration_enabled = True
            mock_settings.git_target_repo_path = tmp_path / "repo"
            mock_settings.git_target_remote = None
            mock_settings.git_base_branch = "main"
            mock_settings.git_branch_prefix = "meeting-forge/"
            mock_settings.git_docs_subdir = "docs/meetings"
            mock_settings.gh_executable = "gh"

            with pytest.raises(pub_module.PublishError):
                pub_module.publish_meeting(meeting_dir, _make_metadata(), state, docs)

        assert not (meeting_dir / "publish.json").exists()


class TestLoadPublishResult:
    def test_returns_none_if_missing(self, tmp_path: Path) -> None:
        assert pub_module.load_publish_result(tmp_path) is None

    def test_returns_result_if_present(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        result = PublishResult(
            branch="meeting-forge/test",
            commit_sha="abc1234",
            pr_url="https://github.com/pull/1",
            published_at=datetime.now(tz=UTC),
            files=["docs/meetings/test/adr/adr-0001.md"],
        )
        (tmp_path / "publish.json").write_text(result.model_dump_json(), encoding="utf-8")
        loaded = pub_module.load_publish_result(tmp_path)
        assert loaded is not None
        assert loaded.branch == "meeting-forge/test"
        assert loaded.commit_sha == "abc1234"
