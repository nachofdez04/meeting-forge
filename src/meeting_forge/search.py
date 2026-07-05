"""Búsqueda semántica entre reuniones (UX-8).

Indexa un resumen textual de cada reunión (summary + temas + decisiones + tareas + un extracto del
transcript) en una **colección Chroma separada** (`meeting_forge_meetings`), distinta del corpus de
documentación del RAG. Así "¿en qué reunión hablamos de la migración?" tiene respuesta sin abrir
reunión por reunión. Reutiliza `ChromaVectorStore` (un chunk por reunión, `chunk_id = meeting_id`)
y el modelo de embeddings ya cargado; `delete_by_source` evita duplicados al reindexar.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from .rag.embeddings import EmbeddingModel
from .rag.schemas import DocumentChunk
from .rag.vector_store import VectorStore

_MEETINGS_COLLECTION = "meeting_forge_meetings"
_INDEX_TEXT_MAX_CHARS = 4000


@dataclass
class MeetingSearchHit:
    """Reunión que casa con una búsqueda, con su score y un fragmento representativo."""

    meeting_id: str
    score: float
    snippet: str


def build_index_text(result: dict[str, object]) -> str:
    """Construye el texto indexable de una reunión a partir de su `result.json` (función pura).

    Prioriza lo semánticamente denso (resumen, temas, decisiones, tareas) y añade un extracto del
    transcript al final, todo acotado a `_INDEX_TEXT_MAX_CHARS`.
    """
    parts: list[str] = []
    insights = result.get("insights")
    if isinstance(insights, dict):
        summary = str(insights.get("summary") or "").strip()
        if summary:
            parts.append(summary)
        topics = insights.get("topics")
        if isinstance(topics, list) and topics:
            parts.append("Temas: " + ", ".join(str(t) for t in topics))
        decisions = insights.get("decisions")
        if isinstance(decisions, list):
            for dec in decisions:
                if isinstance(dec, dict):
                    title = str(dec.get("title") or "").strip()
                    desc = str(dec.get("description") or "").strip()
                    if title or desc:
                        parts.append(f"Decisión: {title}. {desc}".strip())
        actions = insights.get("action_items")
        if isinstance(actions, list):
            for act in actions:
                if isinstance(act, dict):
                    desc = str(act.get("description") or "").strip()
                    if desc:
                        parts.append(f"Tarea: {desc}")

    transcript = result.get("transcript")
    if isinstance(transcript, dict):
        segments = transcript.get("segments")
        if isinstance(segments, list):
            texts = [str(s.get("text") or "") for s in segments if isinstance(s, dict)]
            joined = " ".join(t for t in texts if t).strip()
            if joined:
                parts.append(joined)

    return "\n".join(parts)[:_INDEX_TEXT_MAX_CHARS].strip()


def _default_store() -> VectorStore:
    from .rag.vector_store import ChromaVectorStore  # import perezoso (dependencia pesada)

    return ChromaVectorStore(collection_name=_MEETINGS_COLLECTION)


def _default_embeddings() -> EmbeddingModel:
    from .rag.embeddings import SentenceTransformerEmbeddings  # import perezoso

    return SentenceTransformerEmbeddings()


def index_meeting(
    meeting_id: str,
    result: dict[str, object],
    *,
    store: VectorStore | None = None,
    embeddings: EmbeddingModel | None = None,
) -> bool:
    """Indexa (o reindexa) una reunión en la colección de búsqueda. False si no hay texto útil."""
    text = build_index_text(result)
    if not text:
        logger.debug("Reunión '{m}' sin texto indexable para búsqueda", m=meeting_id)
        return False
    store = store or _default_store()
    embeddings = embeddings or _default_embeddings()
    store.delete_by_source(meeting_id)  # evita duplicados al reindexar
    chunk = DocumentChunk(
        chunk_id=meeting_id,
        source_path=meeting_id,
        section_path=[],
        text=text,
        line_start=0,
        line_end=0,
    )
    store.add([chunk], embeddings.embed_texts([text]))
    return True


def index_all_meetings(
    outputs_dir: Path,
    *,
    store: VectorStore | None = None,
    embeddings: EmbeddingModel | None = None,
) -> int:
    """Reindexa todas las reuniones presentes en `outputs_dir`. Devuelve cuántas indexó."""
    import json

    if not outputs_dir.is_dir():
        return 0
    store = store or _default_store()
    embeddings = embeddings or _default_embeddings()
    indexed = 0
    for subdir in sorted(outputs_dir.iterdir()):
        if not subdir.is_dir():
            continue
        result_files = sorted(subdir.glob("*_result.json"))
        if not result_files:
            continue
        try:
            raw = json.loads(result_files[0].read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Búsqueda: ignorando {p} ({e})", p=result_files[0], e=exc)
            continue
        if isinstance(raw, dict) and index_meeting(
            subdir.name, raw, store=store, embeddings=embeddings
        ):
            indexed += 1
    logger.info("Índice de búsqueda: {n} reunión(es) indexada(s)", n=indexed)
    return indexed


def search_meetings(
    query: str,
    top_k: int = 5,
    *,
    store: VectorStore | None = None,
    embeddings: EmbeddingModel | None = None,
) -> list[MeetingSearchHit]:
    """Busca reuniones relevantes para `query`. Lista vacía si la query está vacía."""
    if not query.strip():
        return []
    store = store or _default_store()
    embeddings = embeddings or _default_embeddings()
    results = store.query(embeddings.embed_query(query), top_k)
    hits: list[MeetingSearchHit] = []
    for res in results:
        snippet = res.chunk.text[:200].strip()
        hits.append(
            MeetingSearchHit(meeting_id=res.chunk.source_path, score=res.score, snippet=snippet)
        )
    return hits


def substring_search(outputs_dir: Path, query: str) -> list[str]:
    """Fallback por subcadena sobre el texto indexable (sin embeddings). Devuelve meeting_ids."""
    import json

    q = query.strip().lower()
    if not q or not outputs_dir.is_dir():
        return []
    matches: list[str] = []
    for subdir in sorted(outputs_dir.iterdir()):
        if not subdir.is_dir():
            continue
        result_files = sorted(subdir.glob("*_result.json"))
        if not result_files:
            continue
        try:
            raw = json.loads(result_files[0].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(raw, dict) and q in build_index_text(raw).lower():
            matches.append(subdir.name)
    return matches
