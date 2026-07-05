"""Tests del módulo generation/templates.py."""

from __future__ import annotations

from meeting_forge.analysis.schemas import ActionItem, Decision, MeetingInsights
from meeting_forge.generation.citations import CitationRegistry
from meeting_forge.generation.schemas import MeetingMetadata
from meeting_forge.generation.templates import render_acta, render_adr_skeleton
from meeting_forge.rag.schemas import SourceRef


def _ref(path: str, start: int = 1, end: int = 5) -> SourceRef:
    return SourceRef(source_path=path, line_start=start, line_end=end, section_path=["Root"])


def _metadata(meeting_id: str = "reunion-test", date: str = "2026-05-25") -> MeetingMetadata:
    return MeetingMetadata(meeting_id=meeting_id, title="Reunión de prueba", date=date)


# ---------------------------------------------------------------------------
# render_adr_skeleton
# ---------------------------------------------------------------------------


class TestRenderAdrSkeleton:
    def _defaults(self, footnote_block: str = "") -> str:
        return render_adr_skeleton(
            title="Adoptar ChromaDB",
            status="Propuesto",
            date="2026-05-25",
            owners="equipo-backend",
            tags="`arquitectura`",
            context_md="Se necesitaba un vector store local.",
            decision_md="Se adopta ChromaDB.",
            consequences_md="- Ventaja: sin servidor externo.\n- Riesgo: menor escala.",
            footnote_block=footnote_block,
        )

    def test_contains_all_h2_sections_with_sources(self) -> None:
        md = self._defaults(footnote_block="[^1]: `a.md` líneas 1–5")
        assert "## Contexto" in md
        assert "## Decisión" in md
        assert "## Consecuencias" in md
        assert "## Referencias" in md

    def test_omits_referencias_section_when_no_footnotes(self) -> None:
        md = self._defaults(footnote_block="")
        assert "## Referencias" not in md

    def test_contains_title_in_h1(self) -> None:
        md = self._defaults()
        assert "# ADR: Adoptar ChromaDB" in md

    def test_contains_metadata_table(self) -> None:
        md = self._defaults()
        assert "Propuesto" in md
        assert "2026-05-25" in md
        assert "equipo-backend" in md

    def test_ends_with_newline(self) -> None:
        md = self._defaults()
        assert md.endswith("\n")

    def test_footnote_block_in_output(self) -> None:
        footnote = "[^1]: `doc.md` líneas 1–5 — *Contexto*"
        md = self._defaults(footnote_block=footnote)
        assert footnote in md


# ---------------------------------------------------------------------------
# render_acta
# ---------------------------------------------------------------------------


class TestRenderActa:
    def _empty_insights(self) -> MeetingInsights:
        return MeetingInsights()

    def _full_insights(self) -> MeetingInsights:
        return MeetingInsights(
            decisions=[
                Decision(
                    title="Adoptar ChromaDB",
                    description="Se usa ChromaDB como vector store.",
                    rationale="Persistente y local.",
                    owners=["equipo-backend"],
                    tags=["arquitectura"],
                    sources=[_ref("adr-001.md", 1, 5)],
                ),
                Decision(
                    title="Decisión sin fuentes",
                    description="No tiene documentación de respaldo.",
                    sources=[],
                ),
            ],
            action_items=[
                ActionItem(
                    description="Hacer benchmark",
                    assignee="nacho",
                    deadline="2026-06-01",
                    sources=[_ref("adr-001.md", 1, 5)],  # misma source que la decisión
                ),
                ActionItem(description="Documentar README"),
            ],
            topics=["arquitectura RAG", "privacidad"],
            summary="Se acordó la arquitectura RAG con ChromaDB.",
        )

    def test_empty_insights_does_not_crash(self) -> None:
        reg = CitationRegistry()
        md, used = render_acta(self._empty_insights(), _metadata(), reg)
        assert isinstance(md, str)
        assert len(md) > 0

    def test_empty_insights_contains_placeholders(self) -> None:
        reg = CitationRegistry()
        md, _ = render_acta(self._empty_insights(), _metadata(), reg)
        assert "sin decisiones" in md
        assert "sin tareas" in md

    def test_full_insights_contains_decisions(self) -> None:
        reg = CitationRegistry()
        insights = self._full_insights()
        for d in insights.decisions:
            reg.register_all(d.sources)
        for a in insights.action_items:
            reg.register_all(a.sources)
        md, _ = render_acta(insights, _metadata(), reg)
        assert "Adoptar ChromaDB" in md
        assert "Decisión sin fuentes" in md

    def test_full_insights_contains_action_items(self) -> None:
        reg = CitationRegistry()
        insights = self._full_insights()
        for d in insights.decisions:
            reg.register_all(d.sources)
        for a in insights.action_items:
            reg.register_all(a.sources)
        md, _ = render_acta(insights, _metadata(), reg)
        assert "Hacer benchmark" in md
        assert "nacho" in md

    def test_decision_with_sources_produces_inline_markers(self) -> None:
        reg = CitationRegistry()
        insights = self._full_insights()
        for d in insights.decisions:
            reg.register_all(d.sources)
        for a in insights.action_items:
            reg.register_all(a.sources)
        md, used = render_acta(insights, _metadata(), reg)
        assert "[^1]" in md
        assert 1 in used

    def test_decision_without_sources_has_no_inline_marker(self) -> None:
        """La decisión sin sources no debe añadir markers."""
        reg = CitationRegistry()
        insights = MeetingInsights(
            decisions=[Decision(title="Sin fuentes", description="Nada.", sources=[])]
        )
        md, used = render_acta(insights, _metadata(), reg)
        assert "[^" not in md
        assert len(used) == 0

    def test_shared_source_deduped_in_registry(self) -> None:
        """La misma SourceRef en decisión y action item → un único índice."""
        reg = CitationRegistry()
        insights = self._full_insights()
        for d in insights.decisions:
            reg.register_all(d.sources)
        for a in insights.action_items:
            reg.register_all(a.sources)
        # adr-001.md:1-5 aparece en decisión 1 y en action item 1 → único índice
        assert reg.size == 1

    def test_summary_present_in_output(self) -> None:
        reg = CitationRegistry()
        insights = self._full_insights()
        md, _ = render_acta(insights, _metadata(), reg)
        assert "ChromaDB" in md  # del summary

    def test_topics_present_in_output(self) -> None:
        reg = CitationRegistry()
        insights = self._full_insights()
        md, _ = render_acta(insights, _metadata(), reg)
        assert "arquitectura RAG" in md

    def test_meeting_title_in_h1(self) -> None:
        reg = CitationRegistry()
        md, _ = render_acta(self._empty_insights(), _metadata(), reg)
        assert "# Acta de reunión:" in md

    def test_date_in_header(self) -> None:
        reg = CitationRegistry()
        md, _ = render_acta(self._empty_insights(), _metadata(date="2026-05-25"), reg)
        assert "2026-05-25" in md
