"""Módulo RAG: indexación y recuperación de documentación."""

from .embeddings import EmbeddingModel, SentenceTransformerEmbeddings
from .indexer import DocumentIndexer
from .retriever import Retriever
from .schemas import DocumentChunk, RetrievalResult, SourceRef
from .vector_store import ChromaVectorStore, VectorStore

__all__ = [
    "ChromaVectorStore",
    "DocumentChunk",
    "DocumentIndexer",
    "EmbeddingModel",
    "RetrievalResult",
    "Retriever",
    "SentenceTransformerEmbeddings",
    "SourceRef",
    "VectorStore",
]
