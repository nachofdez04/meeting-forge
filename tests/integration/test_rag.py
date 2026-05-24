"""Test de integración del pipeline RAG end-to-end.

Skipped por defecto: requiere descargar el modelo de embeddings y escribir
ChromaDB en disco. Habilítalo manualmente cuando esas piezas estén presentes.
"""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "sample_docs"


@pytest.mark.integration
@pytest.mark.skip(reason="Requires sentence-transformers model download and ChromaDB")
def test_index_and_retrieve_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Indexar fixtures → retrieve produce los chunks esperados."""
    # Redirigir ChromaDB a tmp_path
    from meeting_forge import config as cfg

    monkeypatch.setattr(cfg.settings, "chromadb_path", tmp_path / "chromadb")
    cfg.settings.chromadb_path.mkdir(parents=True, exist_ok=True)

    from meeting_forge.ingestion.schemas import Transcript, TranscriptSegment
    from meeting_forge.rag.embeddings import SentenceTransformerEmbeddings
    from meeting_forge.rag.indexer import DocumentIndexer
    from meeting_forge.rag.retriever import Retriever
    from meeting_forge.rag.vector_store import ChromaVectorStore

    store = ChromaVectorStore(collection_name="test_collection")
    embeddings = SentenceTransformerEmbeddings()
    indexer = DocumentIndexer(store=store, embeddings=embeddings)
    n = indexer.index_paths([FIXTURES], root=FIXTURES)
    assert n > 0

    retriever = Retriever(store=store, embeddings=embeddings)
    transcript = Transcript(
        segments=[
            TranscriptSegment(
                start=0,
                end=10,
                text="Hablemos de RAG y de cómo enriquecer el LLM con contexto.",
            )
        ],
        duration_seconds=10.0,
    )
    results = retriever.retrieve_for_transcript(transcript, k_total=3)
    assert results, "Esperaba al menos un chunk recuperado"
    # El chunk de RAG del glossary debería estar entre los top
    paths = [r.chunk.source_path for r in results]
    assert any("glossary" in p for p in paths)
