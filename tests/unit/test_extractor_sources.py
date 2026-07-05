"""Tests del post-procesado de marcadores `#N` → SourceRef en el extractor."""

from __future__ import annotations

from meeting_forge.analysis.extractor import (
    InsightsExtractor,
    _RawActionItem,
    _RawDecision,
    _RawMeetingInsights,
)
from meeting_forge.ingestion.schemas import Transcript, TranscriptSegment
from meeting_forge.rag.schemas import DocumentChunk, RetrievalResult


def _transcript(n: int = 4) -> Transcript:
    return Transcript(
        segments=[
            TranscriptSegment(start=float(i * 5), end=float(i * 5 + 5), text=f"seg {i}")
            for i in range(n)
        ],
        duration_seconds=float(n * 5),
        language="es",
    )


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


# ---------------------------------------------------------------------------
# UX-6 · transcript_refs (marcadores S<n> → TranscriptRef con timestamps)
# ---------------------------------------------------------------------------


def test_resolve_transcript_refs_maps_segment_markers() -> None:
    raw = _RawMeetingInsights(
        decisions=[_RawDecision(title="D", description="d", transcript_refs=["S1", "S3"])],
        action_items=[_RawActionItem(description="T", transcript_refs=["S0"])],
    )
    out = InsightsExtractor._resolve_sources(raw, [], _transcript(4))

    dec_refs = out.decisions[0].transcript_refs
    assert [r.segment_index for r in dec_refs] == [1, 3]
    assert dec_refs[0].start == 5.0 and dec_refs[0].end == 10.0
    assert dec_refs[0].text == "seg 1"
    assert out.action_items[0].transcript_refs[0].segment_index == 0


def test_resolve_transcript_refs_drops_out_of_range_and_dupes() -> None:
    raw = _RawMeetingInsights(
        decisions=[
            _RawDecision(title="D", description="d", transcript_refs=["S0", "S0", "S99", "Sx"])
        ],
    )
    out = InsightsExtractor._resolve_sources(raw, [], _transcript(2))
    assert [r.segment_index for r in out.decisions[0].transcript_refs] == [0]


def test_resolve_transcript_refs_empty_without_transcript() -> None:
    raw = _RawMeetingInsights(
        decisions=[_RawDecision(title="D", description="d", transcript_refs=["S0"])],
    )
    out = InsightsExtractor._resolve_sources(raw, [])
    assert out.decisions[0].transcript_refs == []
