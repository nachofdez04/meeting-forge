"""Memoria RAG de reuniones pasadas (UX-9).

Las actas y ADRs ya aprobados son la mejor evidencia para reuniones futuras ("esto ya se decidió el
12-05"). Este módulo indexa el contenido **efectivo** (con las ediciones humanas) de los documentos
aprobados en el corpus RAG principal, con un `source_path` estable por reunión/kind/fichero. Así el
extractor de futuras reuniones puede citarlos y detectar contradicciones con acuerdos previos.

`delete_by_source` evita duplicados al reindexar un documento reaprobado. Diseño tolerante a fallos:
el llamador invoca esto como paso best-effort tras aprobar/publicar; un fallo nunca rompe ese flujo.
"""

from __future__ import annotations

from loguru import logger

from .generation.schemas import GeneratedDocView
from .rag.chunker import MarkdownChunker
from .rag.embeddings import EmbeddingModel
from .rag.vector_store import VectorStore
from .validation.schemas import MeetingValidationState
from .validation.store import get_effective_content

# Prefijo del `source_path` de los documentos de reuniones dentro del corpus RAG, para distinguirlos
# de la documentación del producto y poder podarlos/filtrarlos.
_MEMORY_PREFIX = "meetings"


def memory_source_path(meeting_id: str, kind: str, filename: str) -> str:
    """`source_path` estable de un documento de reunión en el corpus RAG (UX-9)."""
    return f"{_MEMORY_PREFIX}/{meeting_id}/{kind}/{filename}"


def index_approved_documents(
    meeting_id: str,
    docs: list[GeneratedDocView],
    validation_state: MeetingValidationState,
    *,
    store: VectorStore,
    embeddings: EmbeddingModel,
    chunker: MarkdownChunker | None = None,
) -> int:
    """Indexa en el corpus RAG el contenido efectivo de los documentos aprobados. Devuelve chunks.

    Solo se indexan los documentos aprobados/editados (los `approved_records`). Cada documento se
    reindexa limpio (`delete_by_source` previo) para no dejar chunks obsoletos si su contenido
    cambió entre aprobaciones.
    """
    approved_filenames = {r.filename for r in validation_state.approved_records()}
    if not approved_filenames:
        return 0

    chunker = chunker or MarkdownChunker()
    total = 0
    for doc in docs:
        if doc.filename not in approved_filenames:
            continue
        source_path = memory_source_path(meeting_id, doc.kind, doc.filename)
        content = get_effective_content(validation_state, doc.filename, doc.markdown_content)
        store.delete_by_source(source_path)
        chunks = chunker.chunk_file(source_path, content)
        if not chunks:
            continue
        store.add(chunks, embeddings.embed_texts([c.text for c in chunks]))
        total += len(chunks)
    if total:
        logger.info(
            "Memoria RAG: indexados {n} chunks de documentos aprobados de '{m}'",
            n=total,
            m=meeting_id,
        )
    return total
