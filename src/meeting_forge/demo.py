"""Generador de una reunión de ejemplo reproducible y sin LLM (F10).

Crea un meeting en `data/outputs/` con insights de muestra y un **acta determinística** (cero
llamadas al LLM), para poder lanzar la UI y ver el sistema funcionando sin API keys ni audio.
Útil como demo para el tribunal y como smoke test de la UI.
"""

from __future__ import annotations

import json
from pathlib import Path

from .analysis.schemas import ActionItem, Decision, MeetingInsights
from .generation.acta_strategy import ActaStrategy
from .generation.schemas import MeetingMetadata
from .rag.schemas import SourceRef

DEMO_MEETING_ID = "demo-reunion"


def _demo_insights() -> MeetingInsights:
    ref = SourceRef(
        source_path="docs/arquitectura.md",
        line_start=10,
        line_end=18,
        section_path=["Arquitectura", "Almacenamiento"],
    )
    return MeetingInsights(
        decisions=[
            Decision(
                title="Adoptar ChromaDB como vector store",
                description="Se usará ChromaDB persistente para el índice de documentación del RAG.",
                rationale="Setup local sencillo y sin coste; suficiente para el volumen previsto.",
                owners=["Nacho"],
                tags=["arquitectura", "rag"],
                sources=[ref],
            ),
            Decision(
                title="Transcripción local con faster-whisper",
                description="La transcripción se hará en local para privacidad y coste cero por minuto.",
                rationale=None,
                owners=["Equipo"],
                tags=["ingesta"],
            ),
        ],
        action_items=[
            ActionItem(
                description="Preparar el script de indexación de la documentación",
                assignee="Nacho",
                deadline="2026-06-10",
                sources=[ref],
            ),
        ],
        topics=["RAG", "transcripción", "arquitectura"],
        summary=(
            "Reunión de planificación: se decide la pila de RAG (ChromaDB) y la transcripción "
            "local con faster-whisper; se asigna la preparación del indexador."
        ),
    )


def build_demo_meeting(outputs_dir: Path) -> Path:
    """Crea una reunión de demostración en `outputs_dir/<demo>` y devuelve su directorio.

    Determinístico y sin red: genera el acta con `ActaStrategy` (sin LLM) y un `result.json`
    cargable por la UI.
    """
    meeting_dir = outputs_dir / DEMO_MEETING_ID
    meeting_dir.mkdir(parents=True, exist_ok=True)

    insights = _demo_insights()
    metadata = MeetingMetadata(
        meeting_id=DEMO_MEETING_ID,
        title="Reunión de demostración",
        date="2026-05-25",
        source_audio=None,
    )

    acta = ActaStrategy().generate(insights, metadata)
    acta.write_to(meeting_dir / acta.kind.value)

    result: dict[str, object] = {
        "audio_file": "(demo: sin audio)",
        "transcript": {
            "segments": [
                {
                    "start": 0.0,
                    "end": 5.0,
                    "text": "Hablemos de la arquitectura de RAG.",
                    "speaker": None,
                },
                {
                    "start": 5.0,
                    "end": 9.0,
                    "text": "Adoptamos ChromaDB como vector store.",
                    "speaker": None,
                },
            ],
            "duration_seconds": 9.0,
            "language": "es",
        },
        "insights": insights.model_dump(),
        "metadata": {
            "provider": "demo",
            "whisper_model": "—",
            "rag_enabled": True,
            "embedding_model": "—",
        },
        "meeting_metadata": metadata.model_dump(mode="json"),
        "retrieved_evidence": [],
        "generated_documents": [
            {
                "filename": acta.filename,
                "kind": acta.kind.value,
                "mode": acta.mode.value,
                "sources_count": len(acta.sources_used),
            }
        ],
        "run_meta": {"run_id": "demo", "phases": [], "llm_calls": []},
    }
    result_path = meeting_dir / f"{DEMO_MEETING_ID}_result.json"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return meeting_dir
