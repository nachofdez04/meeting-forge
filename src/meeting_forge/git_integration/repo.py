"""Wrappers sobre git CLI para operaciones en el repo destino (Fase 4)."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitOperationError(RuntimeError):
    """Error en una operación git. Incluye stdout/stderr para diagnóstico."""

    def __init__(self, message: str, stdout: str = "", stderr: str = "") -> None:
        detail = "\n".join(filter(None, [message, stdout.strip(), stderr.strip()]))
        super().__init__(detail)
        self.stdout = stdout
        self.stderr = stderr


def _run(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise GitOperationError(
            f"git {args[1] if len(args) > 1 else ''!r} falló (código {result.returncode})",
            stdout=result.stdout,
            stderr=result.stderr,
        )
    return result


def ensure_repo(target_path: Path, remote: str | None = None) -> Path:
    """Garantiza que target_path sea un repo git válido.

    - Si no existe y hay remote: clona.
    - Si existe y tiene .git: hace fetch (o no-op si no hay remote).
    - Si existe pero no tiene .git: lanza GitOperationError.
    """
    git_dir = target_path / ".git"
    if not target_path.exists():
        if not remote:
            raise GitOperationError(
                f"El directorio destino no existe y no se proporcionó remote: {target_path}"
            )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", remote, str(target_path)], cwd=target_path.parent)
    elif not git_dir.exists():
        raise GitOperationError(
            f"{target_path} existe pero no es un repositorio git (falta .git/)"
        )
    elif remote:
        _run(["git", "fetch", "--all", "--prune"], cwd=target_path)
    return target_path


def get_current_branch(repo: Path) -> str:
    """Devuelve el nombre de la rama actual."""
    result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    return result.stdout.strip()


def checkout_branch(repo: Path, branch: str, base: str | None = None) -> None:
    """Crea y activa una rama nueva desde base, o cambia a una existente."""
    existing = _run(["git", "branch", "--list", branch], cwd=repo)
    if existing.stdout.strip():
        _run(["git", "checkout", branch], cwd=repo)
    elif base:
        _run(["git", "checkout", "-b", branch, base], cwd=repo)
    else:
        _run(["git", "checkout", "-b", branch], cwd=repo)


def pull(repo: Path) -> None:
    """Hace git pull --ff-only en la rama actual."""
    result = _run(["git", "pull", "--ff-only"], cwd=repo, check=False)
    # No es error si no hay upstream configurado (repo recién clonado con una sola rama)
    if result.returncode != 0 and "no tracking information" not in result.stderr:
        raise GitOperationError(
            "git pull falló",
            stdout=result.stdout,
            stderr=result.stderr,
        )


def write_files(repo: Path, files: list[tuple[str, str]]) -> list[Path]:
    """Escribe (ruta_relativa, contenido) en el repo. Crea subdirectorios si hacen falta."""
    written: list[Path] = []
    for rel_path, content in files:
        target = repo / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(target)
    return written


def add_and_commit(repo: Path, paths: list[Path], message: str) -> str:
    """Hace git add de los paths y crea el commit. Devuelve el SHA corto."""
    str_paths = [str(p.relative_to(repo)) for p in paths]
    _run(["git", "add", "--"] + str_paths, cwd=repo)
    _run(["git", "commit", "-m", message], cwd=repo)
    result = _run(["git", "rev-parse", "--short", "HEAD"], cwd=repo)
    return result.stdout.strip()


def push(repo: Path, branch: str) -> None:
    """Hace git push -u origin <branch>."""
    _run(["git", "push", "-u", "origin", branch], cwd=repo)
