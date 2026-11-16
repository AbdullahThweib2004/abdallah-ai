"""Persistent vector index (ChromaDB) over knowledge chunks.

The index stores a content hash of the chunks + embedding model + chunker version; `ensure()`
rebuilds only when that hash changed, so restarts are fast and edits are picked up.
"""

import contextlib
import hashlib
import json
import logging
import time
from collections.abc import Sequence
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.rag.chunking import CHUNKER_VERSION, Chunk
from app.rag.embeddings import Embedder

logger = logging.getLogger(__name__)

COLLECTION = "knowledge"


def content_hash(chunks: Sequence[Chunk], embedder_name: str) -> str:
    payload = json.dumps(
        {
            "chunker": CHUNKER_VERSION,
            "embedder": embedder_name,
            "chunks": [[c.id, c.text, c.metadata()] for c in chunks],
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class KnowledgeIndex:
    def __init__(self, path: Path, embedder: Embedder) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self._embedder = embedder
        self._client = chromadb.PersistentClient(
            path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
        )

    def _collection(self):  # noqa: ANN202 - chromadb's Collection type
        return self._client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"}, embedding_function=None
        )

    def stored_hash(self) -> str | None:
        try:
            collection = self._client.get_collection(COLLECTION, embedding_function=None)
        except Exception:  # noqa: BLE001 - chromadb raises various "not found" errors
            return None
        return (collection.metadata or {}).get("content_hash")

    def ensure(self, chunks: Sequence[Chunk]) -> bool:
        """Rebuild the index if the knowledge or the model changed. Returns True if rebuilt."""
        wanted = content_hash(chunks, self._embedder.name)
        if self.stored_hash() == wanted:
            return False
        self.build(chunks, wanted)
        return True

    def build(self, chunks: Sequence[Chunk], hash_value: str | None = None) -> None:
        started = time.perf_counter()
        with contextlib.suppress(Exception):  # nothing to delete on the first build
            self._client.delete_collection(COLLECTION)
        collection = self._client.create_collection(
            COLLECTION,
            metadata={
                "hnsw:space": "cosine",
                "content_hash": hash_value or content_hash(chunks, self._embedder.name),
                "embedder": self._embedder.name,
            },
            embedding_function=None,
        )
        if chunks:
            collection.add(
                ids=[c.id for c in chunks],
                documents=[c.text for c in chunks],
                metadatas=[c.metadata() for c in chunks],
                embeddings=self._embedder.embed_passages([c.text for c in chunks]),
            )
        logger.info(
            "RAG index built: %d chunks with %s in %.1fs",
            len(chunks),
            self._embedder.name,
            time.perf_counter() - started,
        )

    def search(self, query_embedding: list[float], k: int) -> list[tuple[str, float]]:
        """Nearest chunks as (chunk_id, cosine similarity), best first."""
        collection = self._collection()
        count = collection.count()
        if count == 0:
            return []
        result = collection.query(query_embeddings=[query_embedding], n_results=min(k, count))
        return [
            (cid, 1.0 - dist)
            for cid, dist in zip(result["ids"][0], result["distances"][0], strict=True)
        ]

    def stats(self) -> dict[str, object]:
        collection = self._collection()
        metadata = collection.metadata or {}
        doc_ids = {m["doc_id"] for m in collection.get(include=["metadatas"])["metadatas"] or []}
        return {
            "chunks": collection.count(),
            "documents": len(doc_ids),
            "embedder": metadata.get("embedder"),
            "content_hash": str(metadata.get("content_hash", ""))[:12],
        }
