"""Tests de carga y validación de los ficheros de prompt de generación."""

from __future__ import annotations

import pytest

from meeting_forge.config import settings


class TestAdrPromptV1:
    def _load(self) -> str:
        path = settings.prompts_dir / "generation" / "adr_v1.md"
        assert path.exists(), f"Prompt no encontrado: {path}"
        return path.read_text(encoding="utf-8")

    def test_file_exists(self) -> None:
        path = settings.prompts_dir / "generation" / "adr_v1.md"
        assert path.exists()

    def test_contains_decision_title_placeholder(self) -> None:
        content = self._load()
        assert "{decision_title}" in content

    def test_contains_decision_description_placeholder(self) -> None:
        content = self._load()
        assert "{decision_description}" in content

    def test_contains_sources_block_placeholder(self) -> None:
        content = self._load()
        assert "{sources_block}" in content

    def test_contains_marker_instructions(self) -> None:
        content = self._load()
        # El prompt debe explicar cómo usar los marcadores #N
        assert "#N" in content or "#1" in content

    def test_contains_rationale_placeholder(self) -> None:
        content = self._load()
        assert "{decision_rationale}" in content

    def test_is_markdown(self) -> None:
        content = self._load()
        assert content.startswith("#")  # encabezado Markdown


class TestGenerationPromptsDir:
    def test_prompts_generation_dir_exists(self) -> None:
        gen_dir = settings.prompts_dir / "generation"
        assert gen_dir.exists()
        assert gen_dir.is_dir()
