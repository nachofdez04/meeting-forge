"""Wrappers sobre git CLI para operaciones en el repo destino (Fase 4)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Fuerza mensajes de git en inglés (B9): así las comprobaciones por texto (p.ej. "no tracking
# information") no dependen del idioma configurado en la máquina del usuario.
_GIT_ENV = {**os.environ, "LC_ALL": "C", "LANG": "C"}


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
        env=_GIT_ENV,
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
        raise GitOperationError(f"{target_path} existe pero no es un repositorio git (falta .git/)")
    elif remote:
        _run(["git", "fetch", "--all", "--prune"], cwd=target_path)
    return target_path


def get_current_branch(repo: Path) -> str:
    """Devuelve el nombre de la rama actual."""
    result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    return result.stdout.strip()


def get_remote_url(repo: Path, remote: str = "origin") -> str | None:
    """Devuelve la URL del remote indicado, o None si no está configurado."""
    result = _run(["git", "remote", "get-url", remote], cwd=repo, check=False)
    url = result.stdout.strip()
    return url or None


def is_clean(repo: Path) -> bool:
    """True si el working tree y el index están limpios (sin cambios sin commitear)."""
    result = _run(["git", "status", "--porcelain"], cwd=repo)
    return result.stdout.strip() == ""


def ensure_clean(repo: Path) -> None:
    """Lanza GitOperationError si el repo destino tiene cambios sin commitear (F7).

    Evita mezclar trabajo manual del usuario con los documentos auto-generados.
    """
    if not is_clean(repo):
        raise GitOperationError(
            "El repositorio destino tiene cambios sin commitear; "
            "resuélvelos (commit o stash) antes de publicar."
        )


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
    """Escribe (ruta_relativa, contenido) en el repo. Crea subdirectorios si hacen falta.

    TD9: cada destino se resuelve y se verifica que quede dentro del repo, bloqueando rutas con
    `..` o absolutas (defensa contra path traversal al escribir en un repositorio externo).
    """
    repo_resolved = repo.resolve()
    written: list[Path] = []
    for rel_path, content in files:
        target = (repo / rel_path).resolve()
        if not target.is_relative_to(repo_resolved):
            raise GitOperationError(
                f"Ruta fuera del repositorio destino (path traversal bloqueado): {rel_path}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(target)
    return written


def add_and_commit(repo: Path, paths: list[Path], message: str) -> str:
    """Hace git add de los paths y crea el commit. Devuelve el SHA corto.

    B10: si tras el `git add` no hay nada staged (el contenido aprobado ya coincide con el repo),
    no se intenta commitear y se lanza un error claro en vez del mensaje confuso de git.
    """
    repo_resolved = repo.resolve()
    str_paths = [str(p.resolve().relative_to(repo_resolved)) for p in paths]
    _run(["git", "add", "--", *str_paths], cwd=repo)

    staged = _run(["git", "diff", "--cached", "--quiet"], cwd=repo, check=False)
    if staged.returncode == 0:
        raise GitOperationError(
            "No hay cambios que publicar: el contenido aprobado ya coincide con el del repositorio."
        )

    _run(["git", "commit", "-m", message], cwd=repo)
    result = _run(["git", "rev-parse", "--short", "HEAD"], cwd=repo)
    return result.stdout.strip()


def push(repo: Path, branch: str) -> None:
    """Hace git push -u origin <branch>."""
    _run(["git", "push", "-u", "origin", branch], cwd=repo)
