"""Carga y prepara datos de reuniones procesadas para la UI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..analysis.schemas import MeetingInsights


@dataclass
class MeetingSummary:
    """Resumen de una reunión disponible en disco."""

    meeting_id: str
    meeting_dir: Path
    result_path: Path
    n_decisions: int
    n_actions: int
    has_generated_docs: bool
    mtime: float


@dataclass
class GeneratedDocView:
    """Vista de un documento generado (ADR o Acta)."""

    filename: str
    kind: str  # "adr" | "acta"
    markdown_content: str


@dataclass
class MeetingData:
    """Datos cargados de una reunión procesada."""

    meeting_id: str
    result: dict[str, object]
    insights: MeetingInsights
    metadata: dict[str, object]
    transcript_segments: list[dict[str, object]]


def list_meetings(base_dir: Path) -> list[MeetingSummary]:
    """Escanea base_dir y devuelve reuniones con *_result.json, de más reciente a más antigua."""
    summaries: list[MeetingSummary] = []
    if not base_dir.is_dir():
        return summaries
    for subdir in base_dir.iterdir():
        if not subdir.is_dir():
            continue
        result_files = list(subdir.glob("*_result.json"))
        if not result_files:
            continue
        result_path = result_files[0]
        try:
            raw = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        insights_raw = raw.get("insights", {}) if isinstance(raw, dict) else {}
        n_decisions = (
            len(insights_raw.get("decisions", []))
            if isinstance(insights_raw, dict)
            else 0
        )
        n_actions = (
            len(insights_raw.get("action_items", []))
            if isinstance(insights_raw, dict)
            else 0
        )
        has_docs = (subdir / "adr").is_dir() or (subdir / "acta").is_dir()
        summaries.append(
            MeetingSummary(
                meeting_id=subdir.name,
                meeting_dir=subdir,
                result_path=result_path,
                n_decisions=n_decisions,
                n_actions=n_actions,
                has_generated_docs=has_docs,
                mtime=result_path.stat().st_mtime,
            )
        )
    summaries.sort(key=lambda s: s.mtime, reverse=True)
    return summaries


def load_meeting(meeting_dir: Path) -> MeetingData:
    """Carga el result.json de meeting_dir y devuelve un MeetingData."""
    result_files = list(meeting_dir.glob("*_result.json"))
    if not result_files:
        raise FileNotFoundError(f"No se encontró *_result.json en {meeting_dir}")
    result_path = result_files[0]
    raw: dict[str, object] = json.loads(result_path.read_text(encoding="utf-8"))
    insights = MeetingInsights.model_validate(raw.get("insights", {}))
    transcript_raw = raw.get("transcript", {})
    segments: list[dict[str, object]] = []
    if isinstance(transcript_raw, dict):
        segs = transcript_raw.get("segments", [])
        if isinstance(segs, list):
            segments = [s for s in segs if isinstance(s, dict)]
    metadata_raw = raw.get("metadata", {})
    metadata: dict[str, object] = metadata_raw if isinstance(metadata_raw, dict) else {}
    return MeetingData(
        meeting_id=meeting_dir.name,
        result=raw,
        insights=insights,
        metadata=metadata,
        transcript_segments=segments,
    )


def load_generated_docs(meeting_dir: Path) -> list[GeneratedDocView]:
    """Lee todos los .md en adr/ y acta/ de meeting_dir. Tolera ausencia de subdirs."""
    docs: list[GeneratedDocView] = []
    for kind in ("adr", "acta"):
        kind_dir = meeting_dir / kind
        if not kind_dir.is_dir():
            continue
        for md_file in sorted(kind_dir.glob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError:
                continue
            docs.append(
                GeneratedDocView(
                    filename=md_file.name,
                    kind=kind,
                    markdown_content=content,
                )
            )
    return docs
