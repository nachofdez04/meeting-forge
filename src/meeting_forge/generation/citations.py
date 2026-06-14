"""Gestión de citas: registro, numeración, reescritura #N → [^N] y bloque de footnotes."""

from __future__ import annotations

import re
from collections.abc import Callable

from loguru import logger

from ..rag.schemas import SourceRef

# Reutiliza el mismo patrón que analysis/extractor.py para coherencia
_MARKER_RE = re.compile(r"#(\d+)")

# Detecta bloques de código (fenced ```) para no reescribir markers dentro de ellos
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


class CitationRegistry:
    """Asigna números secuenciales a SourceRefs, deduplicando por (path, start, end)."""

    def __init__(self) -> None:
        self._key_to_index: dict[tuple[str, int, int], int] = {}
        self._ordered: list[SourceRef] = []

    def register(self, ref: SourceRef) -> int:
        """Registra un SourceRef y devuelve su número (1-indexed). Idempotente."""
        key = (ref.source_path, ref.line_start, ref.line_end)
        if key in self._key_to_index:
            return self._key_to_index[key]
        idx = len(self._ordered) + 1
        self._key_to_index[key] = idx
        self._ordered.append(ref)
        return idx

    def register_all(self, refs: list[SourceRef]) -> list[int]:
        """Registra una lista de SourceRefs y devuelve sus índices en orden."""
        return [self.register(r) for r in refs]

    def get(self, index: int) -> SourceRef | None:
        """Devuelve el SourceRef para el índice dado (1-indexed), o None si fuera de rango."""
        if index < 1 or index > len(self._ordered):
            return None
        return self._ordered[index - 1]

    @property
    def size(self) -> int:
        return len(self._ordered)

    def build_sources_block(self) -> str:
        """Genera el bloque de contexto `[#N] path:Lstart-Lend (section)` para inyectar en prompts.

        Formato idéntico al _build_context de InsightsExtractor (extractor.py:115) para consistencia.
        """
        lines: list[str] = []
        for idx, ref in enumerate(self._ordered, start=1):
            header = f"[#{idx}] {ref.source_path}:{ref.line_start}-{ref.line_end}"
            if ref.section_path:
                header += f"  ({' › '.join(ref.section_path)})"
            lines.append(header)
        return "\n".join(lines)


def escape_user_text(text: str) -> str:
    """Escapa secuencias `[^` en texto de usuario para evitar colisiones con nuestros footnotes.

    El LLM de Fase 1 pudo haber generado texto con `[^x]` que confundiría al renderer.
    """
    return text.replace("[^", r"\[^")


def rewrite_marker_text(text: str, resolve: Callable[[int], int | None]) -> tuple[str, set[int]]:
    """Reescribe marcadores `#N` → `[^M]` donde `M = resolve(N)`.

    Si `resolve(N)` devuelve None, deja `#N` intacto. Ignora los marcadores dentro de code fences.
    Devuelve (texto_reescrito, conjunto de índices `M` realmente usados). Helper común para no
    duplicar esta lógica entre la reescritura por-registro y la remapeada local→global (TD3).
    """
    fences: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        fences.append(m.group(0))
        return f"\x00FENCE{len(fences) - 1}\x00"

    protected = _CODE_FENCE_RE.sub(_stash, text)
    used: set[int] = set()

    def _replace(m: re.Match[str]) -> str:
        target = resolve(int(m.group(1)))
        if target is None:
            return m.group(0)  # deja el marker original en lugar de borrarlo silenciosamente
        used.add(target)
        return f"[^{target}]"

    rewritten = _MARKER_RE.sub(_replace, protected)
    for i, fence in enumerate(fences):
        rewritten = rewritten.replace(f"\x00FENCE{i}\x00", fence)

    return rewritten, used


def rewrite_markers(text: str, registry: CitationRegistry) -> tuple[str, set[int]]:
    """Reescribe `#N` → `[^N]` validando contra *registry*; los fuera de rango se dejan con warning."""

    def _resolve(idx: int) -> int | None:
        if registry.get(idx) is None:
            logger.warning("Marcador #{} fuera de rango en generación (máx {})", idx, registry.size)
            return None
        return idx

    return rewrite_marker_text(text, _resolve)


def render_footnote_block(registry: CitationRegistry, used_indices: set[int]) -> str:
    """Genera el bloque de footnotes Markdown para los índices realmente usados.

    Formato: ``[^N]: `path/to/doc.md` líneas S–E — *section › path*``
    Compatible con MkDocs Material (pymdownx.footnotes).
    """
    if not used_indices:
        return ""

    lines: list[str] = []
    for idx in sorted(used_indices):
        ref = registry.get(idx)
        if ref is None:
            continue
        line = f"[^{idx}]: `{ref.source_path}` líneas {ref.line_start}–{ref.line_end}"
        if ref.section_path:
            line += f" — *{' › '.join(ref.section_path)}*"
        lines.append(line)

    return "\n".join(lines)
