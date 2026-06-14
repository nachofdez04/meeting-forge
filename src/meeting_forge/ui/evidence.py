"""Lee rodajas de archivos fuente para el panel de evidencia."""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SliceResult:
    """Resultado de leer una rodaja de un archivo fuente."""

    text: str
    found: bool
    resolved_path: str
    warning: str = field(default="")


@functools.lru_cache(maxsize=64)
def _read_file_lines(resolved_path: str) -> tuple[str, ...] | None:
    """Lee el archivo y retorna sus líneas como tuple inmutable. Cachea por path."""
    try:
        content = Path(resolved_path).read_text(encoding="utf-8")
        return tuple(content.splitlines())
    except OSError:
        return None


def read_source_slice(
    source_path: str,
    line_start: int,
    line_end: int,
    base_dir: Path,
    context_lines: int = 0,
) -> SliceResult:
    """Lee líneas [line_start, line_end] (1-indexed, inclusive) de source_path relativo a base_dir.

    context_lines añade líneas extra antes y después, recortadas a los límites del archivo.
    Retorna SliceResult con found=False si el archivo no existe o el rango es inválido.
    """
    resolved = (base_dir / source_path).resolve()
    resolved_str = str(resolved)

    # TD9: no leer fuera del directorio base (bloquea `..` y rutas absolutas).
    if not resolved.is_relative_to(base_dir.resolve()):
        return SliceResult(
            text="",
            found=False,
            resolved_path=resolved_str,
            warning=f"Ruta fuera del directorio base (bloqueada): {source_path}",
        )

    lines = _read_file_lines(resolved_str)

    if lines is None:
        return SliceResult(
            text="",
            found=False,
            resolved_path=resolved_str,
            warning=f"Archivo no encontrado: {source_path}",
        )

    total = len(lines)
    if line_start < 1 or line_start > total:
        return SliceResult(
            text="",
            found=False,
            resolved_path=resolved_str,
            warning=(
                f"Línea de inicio {line_start} fuera de rango "
                f"(el archivo tiene {total} líneas)."
            ),
        )

    # Convert to 0-indexed with context, clipped to file bounds
    start_0 = max(0, line_start - 1 - context_lines)
    end_0 = min(total, line_end + context_lines)
    slice_text = "\n".join(lines[start_0:end_0])

    return SliceResult(text=slice_text, found=True, resolved_path=resolved_str)
