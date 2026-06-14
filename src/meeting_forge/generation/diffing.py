"""Utilidad de diff Markdown para los modos de actualización de documentos (F5)."""

from __future__ import annotations

import difflib


def unified_md_diff(original: str, revised: str, filename: str = "documento.md") -> str:
    """Devuelve el diff unificado entre `original` y `revised` (o "" si son idénticos).

    Pensado para mostrar al usuario qué cambiaría en un documento existente antes de aprobarlo.
    """
    diff = difflib.unified_diff(
        original.splitlines(),
        revised.splitlines(),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm="",
    )
    return "\n".join(diff)
