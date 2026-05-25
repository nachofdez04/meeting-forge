"""Tests de git_integration/repo.py usando repos git reales en tmp_path."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from meeting_forge.git_integration.repo import (
    GitOperationError,
    add_and_commit,
    checkout_branch,
    ensure_repo,
    write_files,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git no disponible en el entorno"
)


def _init_repo(path: Path, initial_branch: str = "main") -> Path:
    """Crea un repo git mínimo con un commit inicial."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", initial_branch], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=path, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=path, capture_output=True, check=True
    )
    readme = path / "README.md"
    readme.write_text("# Test repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=path, capture_output=True, check=True
    )
    return path


class TestEnsureRepo:
    def test_valid_repo_passes(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        result = ensure_repo(repo)
        assert result == repo

    def test_non_repo_raises(self, tmp_path: Path) -> None:
        (tmp_path / "notrepo").mkdir()
        with pytest.raises(GitOperationError, match="no es un repositorio git"):
            ensure_repo(tmp_path / "notrepo")

    def test_missing_without_remote_raises(self, tmp_path: Path) -> None:
        with pytest.raises(GitOperationError, match="no existe"):
            ensure_repo(tmp_path / "missing")


class TestCheckoutBranch:
    def test_creates_new_branch(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        checkout_branch(repo, "feature/x", base="main")
        result = subprocess.run(
            ["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True
        )
        assert result.stdout.strip() == "feature/x"

    def test_switches_to_existing_branch(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        subprocess.run(["git", "checkout", "-b", "existing"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "checkout", "main"], cwd=repo, capture_output=True, check=True)
        checkout_branch(repo, "existing")
        result = subprocess.run(
            ["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True
        )
        assert result.stdout.strip() == "existing"


class TestWriteFiles:
    def test_writes_files(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        written = write_files(repo, [("docs/meetings/m1/adr-0001.md", "# ADR")])
        assert len(written) == 1
        assert written[0].read_text(encoding="utf-8") == "# ADR"

    def test_creates_subdirs(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        write_files(repo, [("deep/nested/dir/file.md", "content")])
        assert (repo / "deep" / "nested" / "dir" / "file.md").exists()


class TestAddAndCommit:
    def test_creates_commit(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        paths = write_files(repo, [("new.md", "# New")])
        sha = add_and_commit(repo, paths, "docs: add new.md")
        assert len(sha) >= 7
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"], cwd=repo, capture_output=True, text=True
        )
        assert "docs: add new.md" in log.stdout

    def test_returns_short_sha(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        paths = write_files(repo, [("f.md", "x")])
        sha = add_and_commit(repo, paths, "msg")
        assert len(sha) <= 12
