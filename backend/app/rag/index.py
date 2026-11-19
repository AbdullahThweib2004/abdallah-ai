"""Precomputed vector index over knowledge chunks (a small artifact, no database).

The artifact is a directory with two files, written at build time (`app.rag.cli build`, run by
the Vercel build hook) and shipped inside the serverless function:

    index.json   format version, content hash (chunks + embedder + chunker version), embedder
                 name, chunk ids, and the BM25 token lists of the chunks
    vectors.npy  float32 matrix (chunks x dim), L2-normalized: cosine = dot product

At request time only the query is embedded; search is one matrix-vector product. `ensure()`
rebuilds when the content hash changed (knowledge edit, model or chunker change). On a
read-only filesystem (a serverless function) a stale index is rebuilt in memory and the
failure to write it is logged, so retrieval still works.
"""

import hashlib
import json
import logging
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from app.rag.chunking import CHUNKER_VERSION, Chunk
from app.rag.embeddings import Embedder

logger = logging.getLogger(__name__)

ARTIFACT_FORMAT = 1
META_FILE = "index.json"
VECTORS_FILE = "vectors.npy"


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
        self._path = path
        self._embedder = embedder
        self._hash: str | None = None
        self._ids: list[str] = []
        self._vectors = np.zeros((0, 0), dtype=np.float32)
        self.bm25_tokens: list[list[str]] | None = None
        self._load()

    # --- persistence -----------------------------------------------------------------------

    def _load(self) -> None:
        meta_path, vectors_path = self._path / META_FILE, self._path / VECTORS_FILE
        if not (meta_path.is_file() and vectors_path.is_file()):
            return
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("format") != ARTIFACT_FORMAT:
                return
            vectors = np.load(vectors_path, allow_pickle=False)
        except (OSError, ValueError) as exc:
            logger.warning("RAG index artifact unreadable (%s); it will be rebuilt", exc)
            return
        self._hash, self._ids = meta["content_hash"], list(meta["ids"])
        self._vectors = vectors.astype(np.float32, copy=False)
        self.bm25_tokens = meta.get("bm25_tokens")

    def _save(self, embedder_name: str) -> None:
        self._path.mkdir(parents=True, exist_ok=True)
        np.save(self._path / VECTORS_FILE, self._vectors, allow_pickle=False)
        meta = {
            "format": ARTIFACT_FORMAT,
            "content_hash": self._hash,
            "embedder": embedder_name,
            "dim": int(self._vectors.shape[1]) if self._vectors.size else 0,
            "ids": self._ids,
            "bm25_tokens": self.bm25_tokens,
        }
        (self._path / META_FILE).write_text(json.dumps(meta, ensure_ascii=False), "utf-8")

    def stored_hash(self) -> str | None:
        return self._hash

    # --- build -----------------------------------------------------------------------------

    def ensure(self, chunks: Sequence[Chunk]) -> bool:
        """Rebuild the index if the knowledge or the model changed. Returns True if rebuilt."""
        wanted = content_hash(chunks, self._embedder.name)
        if self._hash == wanted and len(self._ids) == len(chunks):
            return False
        self.build(chunks, wanted)
        return True

    def build(self, chunks: Sequence[Chunk], hash_value: str | None = None) -> None:
        from app.rag.retriever import tokenize  # the retriever owns BM25 tokenization

        started = time.perf_counter()
        vectors = self._embedder.embed_passages([c.text for c in chunks]) if chunks else []
        self._vectors = np.asarray(vectors, dtype=np.float32).reshape(len(chunks), -1)
        norms = np.linalg.norm(self._vectors, axis=1, keepdims=True)
        self._vectors /= np.clip(norms, 1e-12, None)
        self._ids = [c.id for c in chunks]
        self.bm25_tokens = [tokenize(c.text) for c in chunks]
        self._hash = hash_value or content_hash(chunks, self._embedder.name)
        try:
            self._save(self._embedder.name)
        except OSError as exc:  # read-only filesystem (serverless): keep it in memory
            logger.warning("RAG index kept in memory only (could not write: %s)", exc)
        logger.info(
            "RAG index built: %d chunks with %s in %.1fs",
            len(chunks),
            self._embedder.name,
            time.perf_counter() - started,
        )

    # --- search ----------------------------------------------------------------------------

    def search(self, query_embedding: list[float], k: int) -> list[tuple[str, float]]:
        """Nearest chunks as (chunk_id, cosine similarity), best first."""
        if not self._ids:
            return []
        query = np.asarray(query_embedding, dtype=np.float32)
        query /= max(float(np.linalg.norm(query)), 1e-12)
        scores = self._vectors @ query
        top = np.argsort(-scores)[: min(k, len(self._ids))]
        return [(self._ids[i], float(scores[i])) for i in top]

    def stats(self) -> dict[str, object]:
        doc_ids = {chunk_id.split("::", 1)[0] for chunk_id in self._ids}
        return {
            "chunks": len(self._ids),
            "documents": len(doc_ids),
            "embedder": self._embedder.name,
            "dim": int(self._vectors.shape[1]) if self._vectors.size else 0,
            "content_hash": (self._hash or "")[:12],
        }
