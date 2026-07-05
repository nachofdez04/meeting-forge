"""Tests del DocumentGenerator (con LLMProvider mockeado)."""

from __future__ import annotations

from typing import TypeVar
from unittest.mock import MagicMock

from meeting_forge.analysis.schemas import ActionItem, Decision, MeetingInsights
from meeting_forge.generation.generator import DocumentGenerator
from meeting_forge.generation.schemas import (
    DocumentKind,
    GenerationMode,
    MeetingMetadata,
)
from meeting_forge.rag.schemas import SourceRef

T = TypeVar("T")


def _ref(path: str = "docs/adr.md", start: int = 1, end: int = 5) -> SourceRef:
    return SourceRef(source_path=path, line_start=start, line_end=end, section_path=["Root"])


def _metadata() -> MeetingMetadata:
    return MeetingMetadata(
        meeting_id="reunion-test",
        title="Reunión de prueba",
        date="2026-05-25",
    )


def _insights_with_decisions(n: int = 2) -> MeetingInsights:
    return MeetingInsights(
        decisions=[
            Decision(
                title=f"Decisión {i}",
                description=f"Descripción de la decisión {i}.",
                sources=[_ref()] if i == 1 else [],
            )
            for i in range(1, n + 1)
        ],
        action_items=[ActionItem(description="Tarea 1")],
        topics=["tema A"],
        summary="Resumen de prueba.",
    )


def _make_mock_provider(raw_adr_dict: dict[str, str] | None = None) -> MagicMock:
    """Crea un LLMProvider mock que devuelve un _RawADR canned."""
    default_raw = {
        "title": "",
        "status": "Propuesto",
        "context_md": "Contexto de prueba. #1",
        "decision_md": "Se decide adoptar la solución.",
        "consequences_md": "- Ventaja: simplicidad.\n- Riesgo: escalabilidad.",
    }
    raw = raw_adr_dict or default_raw

    provider = MagicMock()

    def _complete_structured(prompt: str, schema: type[T], system: str | None = None) -> T:
        # Deserializa en el schema que se pida (tolerante a _RawADR)
        return schema.model_validate(raw)  # type: ignore[attr-defined]

    provider.complete_structured.side_effect = _complete_structured
    return provider


# ---------------------------------------------------------------------------
# Routing por modo
# ---------------------------------------------------------------------------


class TestDocumentGeneratorRouting:
    def test_modes_adr_per_decision_returns_one_per_decision(self) -> None:
        provider = _make_mock_provider()
        gen = DocumentGenerator(provider=provider)
        insights = _insights_with_decisions(n=3)
        docs = gen.generate(insights, _metadata(), modes=[GenerationMode.ADR_PER_DECISION])
        assert len(docs) == 3
        assert all(d.kind == DocumentKind.ADR for d in docs)
        assert all(d.mode == GenerationMode.ADR_PER_DECISION for d in docs)

    def test_mode_acta_returns_exactly_one_doc(self) -> None:
        provider = _make_mock_provider()
        gen = DocumentGenerator(provider=provider)
        docs = gen.generate(_insights_with_decisions(), _metadata(), modes=[GenerationMode.ACTA])
        assert len(docs) == 1
        assert docs[0].kind == DocumentKind.ACTA

    def test_mode_acta_makes_no_llm_calls(self) -> None:
        provider = _make_mock_provider()
        gen = DocumentGenerator(provider=provider)
        gen.generate(_insights_with_decisions(), _metadata(), modes=[GenerationMode.ACTA])
        provider.complete_structured.assert_not_called()
        provider.complete.assert_not_called()

    def test_mode_consolidated_returns_one_doc(self) -> None:
        provider = _make_mock_provider()
        gen = DocumentGenerator(provider=provider)
        docs = gen.generate(
            _insights_with_decisions(n=2),
            _metadata(),
            modes=[GenerationMode.ADR_CONSOLIDATED],
        )
        assert len(docs) == 1
        assert docs[0].kind == DocumentKind.ADR
        assert docs[0].mode == GenerationMode.ADR_CONSOLIDATED

    def test_all_three_modes_combined(self) -> None:
        provider = _make_mock_provider()
        gen = DocumentGenerator(provider=provider)
        insights = _insights_with_decisions(n=2)
        docs = gen.generate(
            insights,
            _metadata(),
            modes=[
                GenerationMode.ADR_PER_DECISION,
                GenerationMode.ADR_CONSOLIDATED,
                GenerationMode.ACTA,
            ],
        )
        # 2 per-decision + 1 consolidated + 1 acta
        assert len(docs) == 4

    def test_empty_modes_returns_empty_list(self) -> None:
        gen = DocumentGenerator(provider=_make_mock_provider())
        docs = gen.generate(_insights_with_decisions(), _metadata(), modes=[])
        assert docs == []


# ---------------------------------------------------------------------------
# generate_adr_consolidated con cero decisiones
# ---------------------------------------------------------------------------


class TestConsolidatedNoDecisions:
    def test_returns_none_when_no_decisions(self) -> None:
        gen = DocumentGenerator(provider=_make_mock_provider())
        empty = MeetingInsights()
        result = gen.generate_adr_consolidated(empty, _metadata())
        assert result is None

    def test_mode_consolidated_with_no_decisions_produces_no_docs(self) -> None:
        gen = DocumentGenerator(provider=_make_mock_provider())
        empty = MeetingInsights()
        docs = gen.generate(empty, _metadata(), modes=[GenerationMode.ADR_CONSOLIDATED])
        assert docs == []


# ---------------------------------------------------------------------------
# Consolidado: remapeo #local → [^global] con fuentes duplicadas
# ---------------------------------------------------------------------------


class TestConsolidatedDuplicateSources:
    def test_marker_maps_to_deduplicated_local_numbering(self) -> None:
        # El LLM ve la numeración DEDUPLICADA del registro local: con sources [A, A, B],
        # #2 es B. El remapeo debe respetarlo (antes enumeraba decision.sources cruda y
        # #2 acababa apuntando a A).
        ref_a = _ref(path="docs/a.md", start=1, end=5)
        ref_b = _ref(path="docs/b.md", start=10, end=20)
        insights = MeetingInsights(
            decisions=[
                Decision(
                    title="Decisión con duplicados",
                    description="Descripción.",
                    sources=[ref_a, ref_a, ref_b],
                )
            ]
        )
        provider = _make_mock_provider(
            {
                "title": "",
                "status": "Propuesto",
                "context_md": "Basado en #2.",
                "decision_md": "Se decide.",
                "consequences_md": "Ninguna.",
            }
        )
        gen = DocumentGenerator(provider=provider)
        doc = gen.generate_adr_consolidated(insights, _metadata())

        assert doc is not None
        md = doc.markdown_content
        assert "Basado en [^2]." in md
        # La footnote 2 debe ser la fuente B (segunda única), no la duplicada A.
        assert "[^2]: `docs/b.md`" in md


class TestGeneratedDocumentFields:
    def test_adr_per_decision_has_correct_fields(self) -> None:
        provider = _make_mock_provider()
        gen = DocumentGenerator(provider=provider)
        docs = gen.generate_adr_per_decision(_insights_with_decisions(n=1), _metadata())
        doc = docs[0]
        assert doc.filename.endswith(".md")
        assert doc.filename.startswith("adr-0001-")
        assert doc.decision_titles == ["Decisión 1"]
        assert isinstance(doc.markdown_content, str)
        assert len(doc.markdown_content) > 0

    def test_acta_has_correct_kind(self) -> None:
        gen = DocumentGenerator(provider=_make_mock_provider())
        doc = gen.generate_acta(_insights_with_decisions(), _metadata())
        assert doc.kind == DocumentKind.ACTA
        assert doc.mode == GenerationMode.ACTA

    def test_acta_filename_format(self) -> None:
        gen = DocumentGenerator(provider=_make_mock_provider())
        doc = gen.generate_acta(_insights_with_decisions(), _metadata())
        assert doc.filename.startswith("acta-2026-05-25-")
        assert doc.filename.endswith(".md")


# ---------------------------------------------------------------------------
# Graceful error handling in generate()
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_error_in_one_mode_does_not_stop_others(self) -> None:
        provider = MagicMock()
        # complete_structured lanza excepción → ADR falla
        provider.complete_structured.side_effect = RuntimeError("LLM error")

        gen = DocumentGenerator(provider=provider)
        insights = _insights_with_decisions(n=1)

        # Con modos [ADR, ACTA]: ADR falla pero ACTA debe completarse
        docs = gen.generate(
            insights,
            _metadata(),
            modes=[GenerationMode.ADR_PER_DECISION, GenerationMode.ACTA],
        )
        # Solo el acta llega (ADR per-decision lanzó excepción)
        assert len(docs) == 1
        assert docs[0].kind == DocumentKind.ACTA
