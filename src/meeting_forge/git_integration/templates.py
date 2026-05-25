"""Templates determinísticos para ramas, commits y PRs (Fase 4)."""

from __future__ import annotations

from ..generation.filenames import slug

_BRANCH_MAX = 60


def build_branch_name(prefix: str, meeting_id: str, date: str | None) -> str:
    """Construye el nombre de la rama: <prefix><meeting_slug>[-<date>].

    El resultado es seguro para Git (sin espacios ni caracteres especiales).
    """
    meeting_slug = slug(meeting_id, max_length=_BRANCH_MAX)
    if date:
        safe_date = date.replace("/", "-")
        name = f"{prefix}{meeting_slug}-{safe_date}"
    else:
        name = f"{prefix}{meeting_slug}"
    # Ramas git no pueden terminar en .lock ni en /
    return name.rstrip("/").rstrip(".")


def build_commit_message(title: str, n_docs: int) -> str:
    """Genera el mensaje de commit."""
    return f"docs(meetings): {title} ({n_docs} doc{'s' if n_docs != 1 else ''})"


def build_pr_title(meeting_title: str, n_docs: int) -> str:
    """Genera el título del PR."""
    return f"[MeetingForge] {meeting_title} — {n_docs} doc{'s' if n_docs != 1 else ''}"


def build_pr_body(meeting_id: str, date: str | None, files: list[str]) -> str:
    """Genera el cuerpo del PR en Markdown."""
    date_line = f"**Fecha:** {date}" if date else ""
    files_md = "\n".join(f"- `{f}`" for f in files)
    parts = [
        "## Documentos generados por MeetingForge",
        "",
        f"**Reunión:** `{meeting_id}`",
    ]
    if date_line:
        parts.append(date_line)
    parts += [
        "",
        "### Archivos incluidos",
        "",
        files_md,
        "",
        "---",
        "_Auto-generado por [MeetingForge](https://github.com/nachofdez04/meeting-forge) · Fase 4_",
    ]
    return "\n".join(parts)
