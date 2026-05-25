"""Test de integración E2E de Fase 4: validación + publicación Git.

Crea un repo destino temporal, aprueba documentos (uno con edición),
publica sin llamar a GitHub real (mock de gh) y verifica el estado del repo.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from meeting_forge.generation.schemas import MeetingMetadata
from meeting_forge.git_integration import publisher as pub_module
from meeting_forge.ui.loader import GeneratedDocView
from meeting_forge.validation import store as val_store

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("git") is None, reason="git no disponible"),
]


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for cmd in [
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "ci@example.com"],
        ["git", "config", "user.name", "CI"],
    ]:
        subprocess.run(cmd, cwd=path, capture_output=True, check=True)
    (path / "README.md").write_text("# Docs\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, capture_output=True, check=True)
    return path


@pytest.fixture()
def target_repo(tmp_path: Path) -> Path:
    return _init_repo(tmp_path / "docs-repo")


@pytest.fixture()
def meeting_dir(tmp_path: Path) -> Path:
    d = tmp_path / "outputs" / "sprint-2026"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def docs() -> list[GeneratedDocView]:
    return [
        GeneratedDocView(filename="adr-0001-cache.md", kind="adr", markdown_content="# ADR 1\n\nOriginal."),
        GeneratedDocView(filename="adr-0002-auth.md", kind="adr", markdown_content="# ADR 2\n\nOriginal."),
        GeneratedDocView(filename="acta-2026-05-25-sprint.md", kind="acta", markdown_content="# Acta\n\nOriginal."),
    ]


@pytest.fixture()
def metadata() -> MeetingMetadata:
    return MeetingMetadata(meeting_id="sprint-2026", title="Sprint 2026", date="2026-05-25")


def test_phase4_full_flow(
    target_repo: Path,
    meeting_dir: Path,
    docs: list[GeneratedDocView],
    metadata: MeetingMetadata,
) -> None:
    """Flujo completo: inicializar → validar → publicar → verificar repo."""
    # 1. Inicializar estado de validación
    state = val_store.initialize_pending(meeting_dir, docs)
    assert state.pending_count() == 3

    # 2. Aprobar con edición, aprobar sin edición, rechazar
    state = val_store.mark_approved(state, "adr-0001-cache.md", edited_content="# ADR 1\n\nEditado.")
    state = val_store.mark_approved(state, "acta-2026-05-25-sprint.md")
    state = val_store.mark_rejected(state, "adr-0002-auth.md", reason="Incompleto")
    val_store.save_state(meeting_dir, state)

    assert state.approved_count() == 2
    assert state.rejected_count() == 1

    # 3. Publicar (mock de gh y push para no necesitar remote)
    pr_url = "https://github.com/owner/docs-repo/pull/1"
    with (
        patch.object(pub_module.pr_module, "create_pr", return_value=pr_url),
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

        result = pub_module.publish_meeting(meeting_dir, metadata, state, docs)

    # 4. Verificar resultado
    assert result.pr_url == pr_url
    assert len(result.files) == 2
    assert result.branch.startswith("meeting-forge/sprint-2026")

    # 5. Verificar estado del repo destino
    branches = subprocess.run(
        ["git", "branch"], cwd=target_repo, capture_output=True, text=True
    ).stdout
    assert result.branch in branches

    # 6. Verificar archivos en el repo
    adr_path = target_repo / "docs" / "meetings" / "sprint-2026" / "adr" / "adr-0001-cache.md"
    assert adr_path.exists()
    assert adr_path.read_text(encoding="utf-8") == "# ADR 1\n\nEditado."  # contenido editado

    acta_path = target_repo / "docs" / "meetings" / "sprint-2026" / "acta" / "acta-2026-05-25-sprint.md"
    assert acta_path.exists()

    rejected_path = target_repo / "docs" / "meetings" / "sprint-2026" / "adr" / "adr-0002-auth.md"
    assert not rejected_path.exists()  # rechazado, no publicado

    # 7. Verificar publish.json en meeting_dir
    publish_json = meeting_dir / "publish.json"
    assert publish_json.exists()
    loaded = pub_module.load_publish_result(meeting_dir)
    assert loaded is not None
    assert loaded.commit_sha == result.commit_sha

    # 8. Idempotencia: load_publish_result devuelve el mismo resultado
    loaded2 = pub_module.load_publish_result(meeting_dir)
    assert loaded2 is not None
    assert loaded2.branch == result.branch
