"""Tests de integración del pipeline de generación (Fase 2).

Usa un LLMProvider mockeado (sin red) para verificar que el pipeline completo
produce documentos Markdown válidos con footnotes correctamente formateados.

Marcados con @pytest.mark.integration para separación clara, aunque en este
caso pueden ejecutarse sin API key al usar provider mockeado.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypeVar
from unittest.mock import MagicMock

import pytest

from meeting_forge.analysis.schemas import MeetingInsights
from meeting_forge.generation.generator import DocumentGenerator
from meeting_forge.generation.schemas import (
    DocumentKind,
    GeneratedDocument,
    GenerationMode,
    MeetingMetadata,
)

T = TypeVar("T")

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# Patrón para footnotes en el cuerpo: [^N]
_INLINE_FOOTNOTE_RE = re.compile(r"\[\^(\d+)\](?!:)")
# Patrón para definiciones de footnotes: [^N]: ...
_FOOTNOTE_DEF_RE = re.compile(r"^\[\^(\d+)\]:", re.MULTILINE)
# Marcador huérfano que NO fue reescrito
_ORPHAN_MARKER_RE = re.compile(r"(?<!\[)#(\d+)")


def _make_mock_provider() -> MagicMock:
    """Provider mock que devuelve prosa genérica con un marcador #1 si hay sources."""
    provider = MagicMock()

    def _complete_structured(prompt: str, schema: type[T], system: str | None = None) -> T:
        # Si el prompt contiene sources (marcador #1), usamos #1 en la prosa
        has_sources = "[#1]" in prompt
        raw = {
            "title": "",
            "status": "Propuesto",
            "context_md": "Contexto generado por LLM. #1" if has_sources else "Contexto sin fuentes.",
            "decision_md": "Se adopta la solución propuesta.",
            "consequences_md": "- Ventaja: simplicidad.\n- Riesgo: deuda técnica.",
        }
        return schema.model_validate(raw)  # type: ignore[attr-defined]

    provider.complete_structured.side_effect = _complete_structured
    return provider


@pytest.fixture
def sample_insights() -> MeetingInsights:
    """Carga el fixture sample_insights.json."""
    path = _FIXTURES_DIR / "sample_insights.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return MeetingInsights.model_validate(data)


@pytest.fixture
def metadata() -> MeetingMetadata:
    return MeetingMetadata(
        meeting_id="sprint-planning",
        title="Sprint Planning Mayo 2026",
        date="2026-05-25",
    )


@pytest.mark.integration
class TestGenerationE2E:
    def test_adr_per_decision_produces_one_per_decision(
        self, sample_insights: MeetingInsights, metadata: MeetingMetadata
    ) -> None:
        gen = DocumentGenerator(provider=_make_mock_provider())
        docs = gen.generate(
            sample_insights, metadata, modes=[GenerationMode.ADR_PER_DECISION]
        )
        assert len(docs) == len(sample_insights.decisions)

    def test_acta_produces_exactly_one_doc(
        self, sample_insights: MeetingInsights, metadata: MeetingMetadata
    ) -> None:
        gen = DocumentGenerator(provider=_make_mock_provider())
        docs = gen.generate(sample_insights, metadata, modes=[GenerationMode.ACTA])
        assert len(docs) == 1
        assert docs[0].kind == DocumentKind.ACTA

    def test_every_inline_footnote_has_a_definition(
        self, sample_insights: MeetingInsights, metadata: MeetingMetadata
    ) -> None:
        """Cada [^N] en el cuerpo debe tener su correspondiente [^N]: al final."""
        gen = DocumentGenerator(provider=_make_mock_provider())
        docs = gen.generate(
            sample_insights,
            metadata,
            modes=[GenerationMode.ADR_PER_DECISION, GenerationMode.ACTA],
        )
        for doc in docs:
            md = doc.markdown_content
            inline_indices = {int(m) for m in _INLINE_FOOTNOTE_RE.findall(md)}
            def_indices = {int(m) for m in _FOOTNOTE_DEF_RE.findall(md)}
            missing = inline_indices - def_indices
            assert not missing, (
                f"[{doc.filename}] Footnotes inline sin definición: {missing}\n\n{md[:500]}"
            )

    def test_footnote_defs_reference_real_sourceref(
        self, sample_insights: MeetingInsights, metadata: MeetingMetadata
    ) -> None:
        """Cada línea [^N]: debe mencionar un source_path presente en el input."""
        known_paths = {
            s.source_path
            for d in sample_insights.decisions
            for s in d.sources
        } | {
            s.source_path
            for a in sample_insights.action_items
            for s in a.sources
        }

        gen = DocumentGenerator(provider=_make_mock_provider())
        docs = gen.generate(
            sample_insights,
            metadata,
            modes=[GenerationMode.ADR_PER_DECISION, GenerationMode.ACTA],
        )
        for doc in docs:
            for match in _FOOTNOTE_DEF_RE.finditer(doc.markdown_content):
                # La línea completa de la definición debe contener uno de los paths conocidos
                line_start = match.start()
                line_end = doc.markdown_content.find("\n", line_start)
                line = doc.markdown_content[line_start : line_end if line_end != -1 else None]
                assert any(p in line for p in known_paths), (
                    f"[{doc.filename}] Footnote apunta a path desconocido: {line!r}"
                )

    def test_no_orphan_hash_markers_remain(
        self, sample_insights: MeetingInsights, metadata: MeetingMetadata
    ) -> None:
        """No deben quedar marcadores #N huérfanos (no reescritos) fuera de code fences."""
        gen = DocumentGenerator(provider=_make_mock_provider())
        docs = gen.generate(
            sample_insights,
            metadata,
            modes=[GenerationMode.ADR_PER_DECISION, GenerationMode.ACTA],
        )
        for doc in docs:
            # Quitar code fences antes de buscar orphans
            md_no_fences = re.sub(r"```.*?```", "", doc.markdown_content, flags=re.DOTALL)
            orphans = _ORPHAN_MARKER_RE.findall(md_no_fences)
            assert not orphans, (
                f"[{doc.filename}] Marcadores huérfanos encontrados: {orphans}"
            )

    def test_decision_without_sources_has_no_referencias_section(
        self, sample_insights: MeetingInsights, metadata: MeetingMetadata
    ) -> None:
        """La 3ª decisión del fixture no tiene sources → su ADR no debe tener ## Referencias."""
        # Decisión 3 = "Transcripción local con faster-whisper" (sources=[])
        from meeting_forge.analysis.schemas import MeetingInsights as MI
        single = MI(decisions=[sample_insights.decisions[2]])
        gen = DocumentGenerator(provider=_make_mock_provider())
        docs = gen.generate(single, metadata, modes=[GenerationMode.ADR_PER_DECISION])
        assert len(docs) == 1
        assert "## Referencias" not in docs[0].markdown_content

    def test_all_modes_combined(
        self, sample_insights: MeetingInsights, metadata: MeetingMetadata
    ) -> None:
        gen = DocumentGenerator(provider=_make_mock_provider())
        docs = gen.generate(
            sample_insights,
            metadata,
            modes=[
                GenerationMode.ADR_PER_DECISION,
                GenerationMode.ADR_CONSOLIDATED,
                GenerationMode.ACTA,
            ],
        )
        # 3 per-decision + 1 consolidated + 1 acta = 5
        assert len(docs) == len(sample_insights.decisions) + 2
        kinds = [d.kind for d in docs]
        assert DocumentKind.ACTA in kinds
        modes = [d.mode for d in docs]
        assert GenerationMode.ADR_CONSOLIDATED in modes

    def test_documents_can_be_written_to_disk(
        self,
        sample_insights: MeetingInsights,
        metadata: MeetingMetadata,
        tmp_path: Path,
    ) -> None:
        gen = DocumentGenerator(provider=_make_mock_provider())
        docs = gen.generate(
            sample_insights,
            metadata,
            modes=[GenerationMode.ADR_PER_DECISION, GenerationMode.ACTA],
        )
        for doc in docs:
            saved = doc.write_to(tmp_path / doc.kind.value)
            assert saved.exists()
            assert saved.read_text(encoding="utf-8") == doc.markdown_content
