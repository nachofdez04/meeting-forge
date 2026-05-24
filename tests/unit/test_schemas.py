"""Tests de round-trip para los schemas Pydantic."""

from meeting_forge.analysis.schemas import ActionItem, Decision, MeetingInsights
from meeting_forge.ingestion.schemas import Transcript, TranscriptSegment


def test_transcript_to_text_concatenates_segments() -> None:
    t = Transcript(
        segments=[
            TranscriptSegment(start=0.0, end=1.0, text="Hola"),
            TranscriptSegment(start=1.0, end=2.0, text="mundo"),
        ],
        duration_seconds=2.0,
        language="es",
    )
    assert t.to_text() == "Hola\nmundo"


def test_transcript_roundtrip() -> None:
    t = Transcript(
        segments=[TranscriptSegment(start=0.0, end=1.0, text="hi")],
        duration_seconds=1.0,
        language="en",
    )
    payload = t.model_dump_json()
    restored = Transcript.model_validate_json(payload)
    assert restored == t


def test_meeting_insights_defaults_empty() -> None:
    insights = MeetingInsights()
    assert insights.decisions == []
    assert insights.action_items == []
    assert insights.topics == []
    assert insights.summary == ""


def test_meeting_insights_roundtrip() -> None:
    insights = MeetingInsights(
        decisions=[
            Decision(
                title="Adoptar uv",
                description="Usar uv para gestión de dependencias",
                rationale="Rápido y reproducible",
                owners=["Nacho"],
                tags=["tooling"],
            )
        ],
        action_items=[
            ActionItem(description="Documentar setup", assignee="Nacho", deadline="2026-06-01")
        ],
        topics=["bootstrap"],
        summary="Decidimos stack inicial.",
    )
    payload = insights.model_dump_json()
    restored = MeetingInsights.model_validate_json(payload)
    assert restored == insights
