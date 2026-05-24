"""Tests del post-procesado de marcadores `#N` → SourceRef en el extractor."""

from __future__ import annotations

from meeting_forge.analysis.extractor import (
    InsightsExtractor,
    _RawActionItem,
    _RawDecision,
    _RawMeetingInsights,
)
from meeting_forge.rag.schemas import DocumentChunk, RetrievalResult


def _result(chunk_id: str, path: str, l_start: int, l_end: int) -> RetrievalResult:
    return RetrievalResult(
        chunk=DocumentChunk(
            chunk_id=chunk_id,
            source_path=path,
            section_path=["root"],
            text="t",
            line_start=l_start,
            line_end=l_end,
        ),
        score=1.0,
    )


def test_resolve_sources_maps_markers_to_sourceref() -> None:
    chunks = [
        _result("a", "adr-001.md", 1, 5),
        _result("b", "glossary.md", 10, 12),
    ]
    raw = _RawMeetingInsights(
        decisions=[
            _RawDecision(title="D", description="...", sources=["#1", "#2"]),
        ],
        action_items=[
            _RawActionItem(description="T", sources=["#2"]),
        ],
        topics=["x"],
        summary="s",
    )
    out = InsightsExtractor._resolve_sources(raw, chunks)

    assert [s.source_path for s in out.decisions[0].sources] == ["adr-001.md", "glossary.md"]
    assert out.decisions[0].sources[0].line_start == 1
    assert out.action_items[0].sources[0].source_path == "glossary.md"


def test_resolve_sources_drops_out_of_range_markers() -> None:
    chunks = [_result("a", "x.md", 1, 1)]
    raw = _RawMeetingInsights(
        decisions=[_RawDecision(title="D", description="d", sources=["#1", "#99", "#0"])],
    )
    out = InsightsExtractor._resolve_sources(raw, chunks)
    assert len(out.decisions[0].sources) == 1


def test_resolve_sources_handles_duplicate_markers() -> None:
    chunks = [_result("a", "x.md", 1, 1)]
    raw = _RawMeetingInsights(
        decisions=[_RawDecision(title="D", description="d", sources=["#1", "#1"])],
    )
    out = InsightsExtractor._resolve_sources(raw, chunks)
    assert len(out.decisions[0].sources) == 1


def test_resolve_sources_handles_no_sources() -> None:
    chunks: list[RetrievalResult] = []
    raw = _RawMeetingInsights(
        decisions=[_RawDecision(title="D", description="d")],
        action_items=[_RawActionItem(description="T")],
    )
    out = InsightsExtractor._resolve_sources(raw, chunks)
    assert out.decisions[0].sources == []
    assert out.action_items[0].sources == []
