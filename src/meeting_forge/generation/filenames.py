"""Utilidades para generar nombres de fichero seguros a partir de texto arbitrario."""

from __future__ import annotations

import re
import unicodedata

from .schemas import MeetingMetadata

# Caracteres que podrían causar inyección o problemas en filesystems / Markdown
_STRIP_RE = re.compile(r"[`\[\]()<>{}|\\/*?:\"']")
# Cualquier run de espacios/guiones/otros separadores → un solo guión
_SEPARATOR_RE = re.compile(r"[\s\-_]+")
# Sólo letras, dígitos y guiones al final
_CLEAN_RE = re.compile(r"[^a-z0-9\-]")


def slug(text: str, max_length: int = 60) -> str:
    """Convierte texto arbitrario en un slug ASCII seguro para nombres de fichero.

    >>> slug("Adoptar `eval()` para [tests]")
    'adoptar-eval-para-tests'
    >>> slug("Diseño · Aprobación")
    'diseno-aprobacion'
    """
    if not text or not text.strip():
        return "untitled"

    # Normalización Unicode NFKD → ASCII (elimina acentos, convierte puntuación especial)
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")

    lowered = ascii_text.lower()
    stripped = _STRIP_RE.sub(" ", lowered)
    dashed = _SEPARATOR_RE.sub("-", stripped)
    clean = _CLEAN_RE.sub("", dashed)
    clean = clean.strip("-")

    if not clean:
        return "untitled"

    # Truncar sin cortar a mitad de palabra
    if len(clean) > max_length:
        truncated = clean[:max_length]
        last_dash = truncated.rfind("-")
        if last_dash > max_length // 2:
            truncated = truncated[:last_dash]
        clean = truncated.strip("-")

    return clean or "untitled"


def build_adr_filename(decision_title: str, counter: int) -> str:
    """Genera el nombre de fichero para un ADR por-decisión.

    Ejemplo: ``adr-0001-adoptar-chromadb.md``
    El contador es per-run (scoped a la reunión actual).
    """
    return f"adr-{counter:04d}-{slug(decision_title)}.md"


def build_consolidated_adr_filename(metadata: MeetingMetadata) -> str:
    """Genera el nombre de fichero para el ADR consolidado de una reunión.

    Ejemplo: ``adr-sprint-planning-consolidated.md``
    """
    return f"adr-{slug(metadata.meeting_id)}-consolidated.md"


def build_acta_filename(metadata: MeetingMetadata) -> str:
    """Genera el nombre de fichero para el acta de una reunión.

    Ejemplo: ``acta-2026-05-25-sprint-planning.md``
    Si no hay fecha se omite el prefijo de fecha.
    """
    meeting_slug = slug(metadata.meeting_id)
    if metadata.date:
        return f"acta-{metadata.date}-{meeting_slug}.md"
    return f"acta-{meeting_slug}.md"
