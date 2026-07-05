"""Tests del chat de Q&A sobre la reunión (UX-11)."""

from __future__ import annotations

from meeting_forge.analysis.schemas import ActionItem, Decision, MeetingInsights
from meeting_forge.chat import (
    ChatMessage,
    answer_question,
    build_chat_prompt,
    parse_cited_segments,
    select_relevant_segments,
)
from meeting_forge.ingestion.schemas import Transcript, TranscriptSegment


def _transcript() -> Transcript:
    texts = [
        "Hablamos del presupuesto para el próximo trimestre",
        "Marta propuso reducir el gasto en infraestructura",
        "Decidimos migrar a microservicios el año que viene",
        "El café de la máquina está muy malo últimamente",
    ]
    return Transcript(
        segments=[
            TranscriptSegment(start=float(i * 10), end=float(i * 10 + 10), text=t)
            for i, t in enumerate(texts)
        ],
        duration_seconds=40.0,
        language="es",
    )


def _insights() -> MeetingInsights:
    return MeetingInsights(
        decisions=[Decision(title="Migrar a microservicios", description="El año que viene")],
        action_items=[ActionItem(description="Revisar presupuesto", assignee="Marta")],
        topics=["presupuesto", "arquitectura"],
        summary="Reunión sobre presupuesto y arquitectura.",
    )


class _EchoProvider:
    """LLMProvider falso: devuelve una respuesta fija que cita segmentos."""

    def __init__(self, reply: str = "Según [S1], Marta propuso recortar gasto.") -> None:
        self.reply = reply
        self.last_prompt = ""

    def complete(
        self, prompt: str, system: str | None = None, max_tokens: int | None = None
    ) -> str:
        self.last_prompt = prompt
        return self.reply

    def complete_structured(self, *args: object, **kwargs: object) -> object:  # pragma: no cover
        raise NotImplementedError


class TestSelectRelevantSegments:
    def test_picks_segments_overlapping_the_question(self) -> None:
        idxs = select_relevant_segments(_transcript(), "¿Qué dijo Marta del presupuesto?", top_k=2)
        # Segmentos 0 (presupuesto) y 1 (Marta) son los más afines; el del café no.
        assert 0 in idxs or 1 in idxs
        assert 3 not in idxs

    def test_returns_sorted_indices(self) -> None:
        idxs = select_relevant_segments(_transcript(), "presupuesto microservicios", top_k=4)
        assert idxs == sorted(idxs)

    def test_generic_question_falls_back_to_first_segments(self) -> None:
        idxs = select_relevant_segments(_transcript(), "xyz zzz qqq", top_k=2)
        assert len(idxs) == 2

    def test_empty_transcript(self) -> None:
        empty = Transcript(segments=[], duration_seconds=0.0, language="es")
        assert select_relevant_segments(empty, "algo") == []


class TestParseCitedSegments:
    def test_extracts_valid_markers(self) -> None:
        assert parse_cited_segments("Según [S1] y [S3] ...", n_segments=4) == [1, 3]

    def test_ignores_out_of_range_and_dupes(self) -> None:
        assert parse_cited_segments("[S0] [S0] [S99]", n_segments=2) == [0]

    def test_no_markers(self) -> None:
        assert parse_cited_segments("Sin citas aquí", n_segments=4) == []


class TestBuildChatPrompt:
    def test_includes_insights_segments_and_question(self) -> None:
        prompt = build_chat_prompt(_transcript(), _insights(), "¿Presupuesto?", [0, 1])
        assert "presupuesto" in prompt.lower()
        assert "[S0]" in prompt and "[S1]" in prompt
        assert "¿Presupuesto?" in prompt

    def test_includes_history_when_present(self) -> None:
        history = [
            ChatMessage(role="user", content="Hola"),
            ChatMessage(role="assistant", content="Qué tal"),
        ]
        prompt = build_chat_prompt(_transcript(), _insights(), "Sigue", [0], history)
        assert "Conversación previa" in prompt
        assert "Hola" in prompt


class TestAnswerQuestion:
    def test_returns_answer_and_cited_segments(self) -> None:
        provider = _EchoProvider("La respuesta está en [S1].")
        ans = answer_question(provider, _transcript(), _insights(), "¿Qué dijo Marta?")
        assert ans.text == "La respuesta está en [S1]."
        assert ans.cited_segments == [1]
        # El prompt que recibió el provider contiene los segmentos indexados.
        assert "[S" in provider.last_prompt
