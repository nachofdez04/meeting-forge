"""Chat de preguntas y respuestas sobre una reunión (UX-11).

Permite preguntar en lenguaje natural ("¿qué dijo Marta del presupuesto?") sin leer el transcript
entero. Selecciona los segmentos más relevantes a la pregunta (por solape de tokens, determinista y
sin embeddings pesados), construye un prompt con los insights + esos segmentos indexados `[S<n>]` +
el historial, y responde con `provider.complete()` citando los `[S<n>]` usados para poder saltar al
minuto del audio. Lógica pura y testeable; la UI solo pinta y contabiliza el coste.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .analysis.llm_client import LLMProvider
from .analysis.schemas import MeetingInsights
from .ingestion.schemas import Transcript

_CHAT_SYSTEM = (
    "Eres un asistente que responde preguntas sobre una reunión técnica basándote ÚNICAMENTE en la "
    "información proporcionada (resumen, decisiones, tareas y fragmentos del transcript). Responde en "
    "español, de forma concisa. Cuando uses un fragmento del transcript, cita su marcador [S<n>]. Si "
    "la información no está disponible, dilo claramente en vez de inventar."
)
_SEGMENT_MARKER_RE = re.compile(r"S(\d+)")
_MAX_HISTORY_TURNS = 6


@dataclass
class ChatMessage:
    """Un turno de la conversación."""

    role: str  # "user" | "assistant"
    content: str
    cited_segments: list[int] = field(default_factory=list)


@dataclass
class ChatAnswer:
    """Respuesta del asistente + los segmentos que citó (para el reproductor de audio)."""

    text: str
    cited_segments: list[int]


def _normalize(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]+", " ", ascii_text.lower())


def _tokens(text: str) -> set[str]:
    return {t for t in _normalize(text).split() if len(t) > 2}


def overlap_score(question_tokens: set[str], segment_text: str) -> int:
    """Nº de tokens compartidos entre la pregunta y un segmento (relevancia simple)."""
    return len(question_tokens & _tokens(segment_text))


def select_relevant_segments(transcript: Transcript, question: str, top_k: int = 6) -> list[int]:
    """Índices de los segmentos más relevantes a la pregunta (orden de aparición).

    Puntúa por solape de tokens y devuelve hasta `top_k` con puntuación positiva; si ninguno
    solapa (pregunta genérica), devuelve los primeros `top_k` como contexto mínimo.
    """
    if not transcript.segments:
        return []
    q_tokens = _tokens(question)
    scored = [(i, overlap_score(q_tokens, seg.text)) for i, seg in enumerate(transcript.segments)]
    positive = [(i, s) for i, s in scored if s > 0]
    chosen = positive if positive else scored
    chosen.sort(key=lambda pair: (-pair[1], pair[0]))
    return sorted(i for i, _ in chosen[:top_k])


def _insights_block(insights: MeetingInsights) -> str:
    parts: list[str] = []
    if insights.summary:
        parts.append(f"Resumen: {insights.summary}")
    if insights.topics:
        parts.append("Temas: " + ", ".join(insights.topics))
    for dec in insights.decisions:
        parts.append(f"Decisión: {dec.title} — {dec.description}")
    for act in insights.action_items:
        who = f" (@{act.assignee})" if act.assignee else ""
        parts.append(f"Tarea: {act.description}{who}")
    return "\n".join(parts) if parts else "(sin insights)"


def _segments_block(transcript: Transcript, indices: list[int]) -> str:
    lines: list[str] = []
    for i in indices:
        seg = transcript.segments[i]
        speaker = f"{seg.speaker}: " if seg.speaker else ""
        lines.append(f"[S{i}] {speaker}{seg.text}")
    return "\n".join(lines) if lines else "(sin fragmentos relevantes)"


def _history_block(history: list[ChatMessage]) -> str:
    recent = history[-_MAX_HISTORY_TURNS:]
    if not recent:
        return ""
    label = {"user": "Usuario", "assistant": "Asistente"}
    lines = [f"{label.get(m.role, m.role)}: {m.content}" for m in recent]
    return "\n".join(lines)


def build_chat_prompt(
    transcript: Transcript,
    insights: MeetingInsights,
    question: str,
    segment_indices: list[int],
    history: list[ChatMessage] | None = None,
) -> str:
    """Construye el prompt de chat (función pura)."""
    sections = [
        "## Información de la reunión",
        _insights_block(insights),
        "",
        "## Fragmentos relevantes del transcript",
        _segments_block(transcript, segment_indices),
    ]
    history_block = _history_block(history or [])
    if history_block:
        sections += ["", "## Conversación previa", history_block]
    sections += ["", "## Pregunta", question]
    return "\n".join(sections)


def parse_cited_segments(answer: str, n_segments: int) -> list[int]:
    """Extrae los marcadores `S<n>` válidos citados en la respuesta (ordenados, sin duplicados)."""
    found: list[int] = []
    seen: set[int] = set()
    for m in _SEGMENT_MARKER_RE.finditer(answer):
        idx = int(m.group(1))
        if 0 <= idx < n_segments and idx not in seen:
            seen.add(idx)
            found.append(idx)
    return sorted(found)


def answer_question(
    provider: LLMProvider,
    transcript: Transcript,
    insights: MeetingInsights,
    question: str,
    history: list[ChatMessage] | None = None,
    *,
    top_k: int = 6,
) -> ChatAnswer:
    """Responde una pregunta sobre la reunión con el `provider` dado."""
    indices = select_relevant_segments(transcript, question, top_k=top_k)
    prompt = build_chat_prompt(transcript, insights, question, indices, history)
    text = provider.complete(prompt, system=_CHAT_SYSTEM)
    cited = parse_cited_segments(text, len(transcript.segments))
    return ChatAnswer(text=text, cited_segments=cited)
