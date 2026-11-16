"""Assemble the retriever from settings: chunks → embedder → persistent index → hybrid search."""

import logging
from collections.abc import Sequence

from app.core.config import Settings
from app.knowledge.loader import KnowledgeDocument
from app.rag.chunking import chunk_documents
from app.rag.embeddings import Embedder, FakeEmbedder, FastEmbedEmbedder
from app.rag.index import KnowledgeIndex
from app.rag.query_expansion import glossary_terms
from app.rag.retriever import Retriever

logger = logging.getLogger(__name__)


def build_embedder(settings: Settings) -> Embedder:
    if settings.rag_embedder == "fake":
        return FakeEmbedder()
    return FastEmbedEmbedder(settings.rag_embedding_model, settings.rag_models_dir)


def build_retriever(
    documents: Sequence[KnowledgeDocument], settings: Settings, *, embedder: Embedder | None = None
) -> Retriever:
    """Build (or reuse) the index. If the model or index fails, fall back to BM25 only."""
    chunks = chunk_documents(documents)
    index: KnowledgeIndex | None = None
    try:
        embedder = embedder or build_embedder(settings)
        index = KnowledgeIndex(settings.rag_index_dir, embedder)
        if index.ensure(chunks):
            logger.info("RAG index rebuilt (knowledge or model changed)")
        else:
            logger.info("RAG index up to date (%d chunks)", len(chunks))
    except Exception:
        logger.exception("Vector search unavailable; retrieval falls back to BM25 only")
        index, embedder = None, None

    return Retriever(
        chunks,
        index=index,
        embedder=embedder,
        glossary=glossary_terms(documents),
        top_k=settings.rag_top_k,
        max_context_tokens=settings.rag_max_context_tokens,
        min_score=settings.rag_min_score,
    )
