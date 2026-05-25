"""Wrapper sobre gh CLI para crear Pull Requests (Fase 4)."""

from __future__ import annotations

import subprocess
from pathlib import Path


class PrCreationError(RuntimeError):
    """Error al crear el PR con gh CLI."""

    def __init__(self, message: str, stdout: str = "", stderr: str = "") -> None:
        detail = "\n".join(filter(None, [message, stdout.strip(), stderr.strip()]))
        super().__init__(detail)
        self.stdout = stdout
        self.stderr = stderr


def is_gh_available(gh_executable: str = "gh") -> bool:
    """Comprueba si el ejecutable gh está disponible en el PATH."""
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


def create_pr(
    repo_path: Path,
    branch: str,
    title: str,
    body: str,
    base: str = "main",
    gh_executable: str = "gh",
) -> str:
    """Crea un PR con gh CLI y devuelve la URL del PR creado.

    Lanza PrCreationError si gh no está disponible o el comando falla.
    """
    result = subprocess.run(
        [
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
        ],
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
