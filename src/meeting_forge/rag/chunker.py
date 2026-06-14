"""Chunking de documentos Markdown respetando la jerarquía de secciones."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from markdown_it import MarkdownIt

from ..config import settings
from .schemas import DocumentChunk


@dataclass
class _Section:
    """Sección intermedia durante el parsing."""

    section_path: list[str]
    lines: list[str] = field(default_factory=list)
    line_start: int = 0
    line_end: int = 0

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


def _hash_chunk(source_path: str, line_start: int, line_end: int, text: str) -> str:
    """Hash determinístico para identificar chunks (idempotente)."""
    h = hashlib.sha1()
    h.update(source_path.encode("utf-8"))
    h.update(f":{line_start}-{line_end}:".encode())
    h.update(text.encode("utf-8"))
    return h.hexdigest()[:16]


class MarkdownChunker:
    """Divide Markdown en chunks por sección, con split por tamaño si es necesario."""

    def __init__(
        self,
        max_chars: int | None = None,
        overlap_chars: int | None = None,
    ) -> None:
        self.max_chars = max_chars or settings.chunk_max_chars
        self.overlap_chars = overlap_chars or settings.chunk_overlap_chars
        self._md = MarkdownIt("commonmark")

    def chunk_file(self, source_path: str, content: str) -> list[DocumentChunk]:
        """Devuelve la lista de chunks para un archivo dado."""
        sections = self._split_into_sections(content)
        chunks: list[DocumentChunk] = []
        for sec in sections:
            text = sec.text
            if not text:
                continue
            for sub_text, l_start, l_end in self._maybe_split_by_size(
                text, sec.line_start, sec.line_end
            ):
                chunk = DocumentChunk(
                    chunk_id=_hash_chunk(source_path, l_start, l_end, sub_text),
                    source_path=source_path,
                    section_path=list(sec.section_path),
                    text=sub_text,
                    line_start=l_start,
                    line_end=l_end,
                )
                chunks.append(chunk)
        return chunks

    def _split_into_sections(self, content: str) -> list[_Section]:
        """Recorre tokens del Markdown y agrupa contenido por jerarquía de headers."""
        lines = content.splitlines()
        tokens = self._md.parse(content)

        sections: list[_Section] = []
        header_stack: list[str] = []

        # Mapeo de tokens heading a (nivel, texto, line_start)
        heading_breaks: list[tuple[int, int, str]] = []
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if t.type == "heading_open" and t.map:
                level = int(t.tag[1])  # h1 → 1, h2 → 2, ...
                line_start = t.map[0] + 1  # markdown-it usa 0-indexed
                title = ""
                if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                    title = tokens[i + 1].content.strip()
                heading_breaks.append((line_start, level, title))
            i += 1

        # Si no hay headers, todo el archivo es un único chunk
        if not heading_breaks:
            return [
                _Section(
                    section_path=[],
                    lines=lines,
                    line_start=1,
                    line_end=len(lines),
                )
            ]

        # Construye secciones entre breaks
        # Contenido antes del primer header (preámbulo)
        first_header_line = heading_breaks[0][0]
        if first_header_line > 1:
            preamble = lines[: first_header_line - 1]
            if any(line.strip() for line in preamble):
                sections.append(
                    _Section(
                        section_path=[],
                        lines=preamble,
                        line_start=1,
                        line_end=first_header_line - 1,
                    )
                )

        for idx, (line_start, level, title) in enumerate(heading_breaks):
            # Ajustar stack de jerarquía
            header_stack = header_stack[: level - 1]
            header_stack.append(title)
            # Determinar dónde termina esta sección
            next_line = (
                heading_breaks[idx + 1][0] - 1 if idx + 1 < len(heading_breaks) else len(lines)
            )
            section_lines = lines[line_start - 1 : next_line]
            sections.append(
                _Section(
                    section_path=list(header_stack),
                    lines=section_lines,
                    line_start=line_start,
                    line_end=next_line,
                )
            )

        return sections

    def _maybe_split_by_size(
        self, text: str, line_start: int, line_end: int
    ) -> list[tuple[str, int, int]]:
        """Si el texto excede max_chars, lo divide con overlap.

        Cada sub-chunk recibe un rango de líneas aproximado (B7) contando los saltos de línea
        consumidos hasta su offset, de modo que las citas apunten a líneas distintas y la clave de
        deduplicación `path:line_start-line_end` no colapse sub-chunks diferentes en una sola cita.
        """
        if len(text) <= self.max_chars:
            return [(text, line_start, line_end)]

        parts: list[tuple[str, int, int]] = []
        step = max(1, self.max_chars - self.overlap_chars)
        start = 0
        while start < len(text):
            end = min(start + self.max_chars, len(text))
            sub_start = line_start + text.count("\n", 0, start)
            sub_end = min(line_end, line_start + text.count("\n", 0, end))
            parts.append((text[start:end], sub_start, max(sub_start, sub_end)))
            if end == len(text):
                break
            start += step
        return parts
