"""Tests de git_integration/pr.py (monkeypatch de subprocess)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from meeting_forge.git_integration.pr import (
    PrCreationError,
    build_compare_url,
    create_pr,
    is_gh_available,
)


class TestIsGhAvailable:
    def test_returns_true_when_gh_runs(self, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            assert is_gh_available("gh") is True

    def test_returns_false_when_not_found(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert is_gh_available("gh") is False

    def test_returns_false_when_nonzero(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            assert is_gh_available("gh") is False

    def test_returns_false_on_timeout(self) -> None:
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 5)):
            assert is_gh_available("gh") is False


class TestCreatePr:
    def _mock_run(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
        result = MagicMock()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    def test_returns_pr_url(self, tmp_path: Path) -> None:
        url = "https://github.com/owner/repo/pull/42"
        with patch("subprocess.run", return_value=self._mock_run(stdout=f"Some output\n{url}\n")):
            result = create_pr(tmp_path, "branch", "title", "body")
        assert result == url

    def test_raises_on_nonzero(self, tmp_path: Path) -> None:
        with patch(
            "subprocess.run",
            return_value=self._mock_run(returncode=1, stderr="authentication error"),
        ):
            with pytest.raises(PrCreationError, match="authentication error"):
                create_pr(tmp_path, "branch", "title", "body")

    def test_raises_when_no_url_in_stdout(self, tmp_path: Path) -> None:
        with patch("subprocess.run", return_value=self._mock_run(stdout="some non-url output")):
            with pytest.raises(PrCreationError, match="URL válida"):
                create_pr(tmp_path, "branch", "title", "body")

    def test_raises_when_stdout_empty(self, tmp_path: Path) -> None:
        # B-N3: returncode 0 con stdout vacío no debe reventar con IndexError, sino PrCreationError.
        with patch("subprocess.run", return_value=self._mock_run(returncode=0, stdout="")):
            with pytest.raises(PrCreationError, match="URL válida"):
                create_pr(tmp_path, "branch", "title", "body")

    def test_passes_correct_args(self, tmp_path: Path) -> None:
        url = "https://github.com/owner/repo/pull/1"
        with patch("subprocess.run", return_value=self._mock_run(stdout=url)) as mock_run:
            create_pr(
                tmp_path, "my-branch", "My Title", "My Body", base="develop", gh_executable="gh"
            )
        call_args = mock_run.call_args[0][0]
        assert "gh" in call_args
        assert "pr" in call_args
        assert "create" in call_args
        assert "my-branch" in call_args
        assert "develop" in call_args

    def test_draft_flag_added(self, tmp_path: Path) -> None:
        url = "https://github.com/owner/repo/pull/1"
        with patch("subprocess.run", return_value=self._mock_run(stdout=url)) as mock_run:
            create_pr(tmp_path, "b", "t", "body", draft=True)
        assert "--draft" in mock_run.call_args[0][0]

    def test_no_draft_by_default(self, tmp_path: Path) -> None:
        url = "https://github.com/owner/repo/pull/1"
        with patch("subprocess.run", return_value=self._mock_run(stdout=url)) as mock_run:
            create_pr(tmp_path, "b", "t", "body")
        assert "--draft" not in mock_run.call_args[0][0]


class TestBuildCompareUrl:
    def test_https_remote(self) -> None:
        url = build_compare_url("https://github.com/nacho/docs.git", "main", "meeting-forge/x")
        assert url == "https://github.com/nacho/docs/compare/main...meeting-forge/x?expand=1"

    def test_ssh_remote(self) -> None:
        url = build_compare_url("git@github.com:nacho/docs.git", "main", "feat")
        assert url == "https://github.com/nacho/docs/compare/main...feat?expand=1"

    def test_https_without_git_suffix(self) -> None:
        url = build_compare_url("https://github.com/nacho/docs", "main", "feat")
        assert url == "https://github.com/nacho/docs/compare/main...feat?expand=1"

    def test_non_github_returns_none(self) -> None:
        assert build_compare_url("https://gitlab.com/nacho/docs.git", "main", "feat") is None
