"""Wrapper sobre gh CLI para crear Pull Requests (Fase 4)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Extrae owner/repo de una URL de remote de GitHub (https o ssh).
_GITHUB_REMOTE_RE = re.compile(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")


class PrCreationError(RuntimeError):
    """Error al crear el PR con gh CLI."""

    def __init__(self, message: str, stdout: str = "", stderr: str = "") -> None:
        detail = "\n".join(filter(None, [message, stdout.strip(), stderr.strip()]))
        super().__init__(detail)
        self.stdout = stdout
        self.stderr = stderr


def is_gh_available(gh_executable: str = "gh") -> bool:
    """Comprueba si el ejecutable gh está disponible en el PATH (no implica autenticación)."""
    try:
        result = subprocess.run(
            [gh_executable, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def is_gh_authenticated(gh_executable: str = "gh") -> bool:
    """Comprueba si gh está autenticado (`gh auth status`), independiente de su disponibilidad (B11)."""
    try:
        result = subprocess.run(
            [gh_executable, "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def create_pr(
    repo_path: Path,
    branch: str,
    title: str,
    body: str,
    base: str = "main",
    gh_executable: str = "gh",
    draft: bool = False,
) -> str:
    """Crea un PR con gh CLI y devuelve la URL del PR creado.

    Con `draft=True` el PR se crea como borrador (raíl del modo automático · F8).
    Lanza PrCreationError si gh no está disponible o el comando falla.
    """
    cmd = [
        gh_executable,
        "pr",
        "create",
        "--title",
        title,
        "--body",
        body,
        "--base",
        base,
        "--head",
        branch,
    ]
    if draft:
        cmd.append("--draft")
    result = subprocess.run(
        cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PrCreationError(
            f"gh pr create falló (código {result.returncode})",
            stdout=result.stdout,
            stderr=result.stderr,
        )
    # gh pr create devuelve la URL en la última línea del stdout
    url = result.stdout.strip().splitlines()[-1].strip()
    if not url.startswith("http"):
        raise PrCreationError(
            "gh pr create no devolvió una URL válida",
            stdout=result.stdout,
            stderr=result.stderr,
        )
    return url


def build_compare_url(remote_url: str, base: str, branch: str) -> str | None:
    """Construye la URL de 'compare' de GitHub para abrir el PR manualmente (F7).

    Devuelve None si el remote no es de GitHub. Útil como fallback cuando `gh` falla o falta.
    """
    match = _GITHUB_REMOTE_RE.search(remote_url)
    if not match:
        return None
    owner = match.group("owner")
    repo = match.group("repo")
    return f"https://github.com/{owner}/{repo}/compare/{base}...{branch}?expand=1"
