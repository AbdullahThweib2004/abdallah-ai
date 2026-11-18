"""Hybrid retrieval: vector search + BM25 keyword search, fused with Reciprocal Rank Fusion.

Exact names (Nawa, MCP, FastAPI, Bank of Palestine) are what BM25 is good at; paraphrases
and Arabic questions are what the multilingual embeddings are good at. Arabic queries are
expanded with English terms (glossary + generic vocabulary) before searching.
"""

import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from rank_bm25 import BM25Okapi

from app.core.tokens import estimate_tokens
from app.rag.chunking import Chunk
from app.rag.embeddings import Embedder
from app.rag.index import KnowledgeIndex
from app.rag.query_expansion import expand_query, normalize_arabic

logger = logging.getLogger(__name__)

RRF_K = 60  # standard Reciprocal Rank Fusion constant
CANDIDATES = 20  # results taken from each ranked list before fusion
# At most this many of the top_k chunks may come from one document, so a question about two
# projects ("compare A with B") also gets B's sections instead of six sections of A.
MAX_CHUNKS_PER_DOC = 4

_WORD = re.compile(r"[^\W_]+(?:[+#.][^\W_]+|\+\+)?")
_STOPWORDS = {
    "a", "an", "and", "are", "about", "as", "at", "be", "by", "can", "did", "do", "does", "for",
    "from", "has", "have", "he", "his", "him", "how", "i", "in", "is", "it", "its", "me", "of",
    "on", "or", "tell", "that", "the", "to", "was", "what", "which", "who", "with", "you", "your",
}  # fmt: skip


def tokenize(text: str) -> list[str]:
    words = _WORD.findall(normalize_arabic(text))
    return [word for word in words if word not in _STOPWORDS]


Ranking = list[tuple[str, int]]  # (chunk id, rank starting at 1); equal scores share a rank


def ranks_from_scores(scored: Sequence[tuple[str, float]]) -> Ranking:
    """Competition ranking ("1, 1, 3"): ties get the same rank instead of an arbitrary order,
    so e.g. a follow-up's earlier topic can break the tie during fusion."""
    ranking: Ranking = []
    previous: float | None = None
    rank = 0
    for position, (item, score) in enumerate(scored, start=1):
        if score != previous:
            rank, previous = position, score
        ranking.append((item, rank))
    return ranking


def reciprocal_rank_fusion(rankings: Sequence[Ranking], k: int = RRF_K) -> dict[str, float]:
    """Fuse rankings: score(id) = Σ 1 / (k + rank)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for item, rank in ranking:
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return scores


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float  # fused RRF score
    vector_score: float | None = None  # cosine similarity of the best vector hit, if any


@dataclass
class RetrievalResult:
    chunks: list[ScoredChunk]
    latency_ms: int
    expanded_query: str = ""
    dropped_for_budget: int = 0
    notes: list[str] = field(default_factory=list)


def diversify(ranked: list[str], doc_of, top_k: int) -> list[str]:
    """The best `top_k` ids in rank order, at most MAX_CHUNKS_PER_DOC per document; slots
    nobody else can fill go back to the capped documents, in rank order."""
    picked: list[str] = []
    overflow: list[str] = []
    per_doc: dict[str, int] = {}
    for chunk_id in ranked:
        if len(picked) == top_k:
            break
        doc = doc_of(chunk_id)
        if per_doc.get(doc, 0) >= MAX_CHUNKS_PER_DOC:
            overflow.append(chunk_id)
            continue
        per_doc[doc] = per_doc.get(doc, 0) + 1
        picked.append(chunk_id)
    picked += overflow[: top_k - len(picked)]
    position = {chunk_id: index for index, chunk_id in enumerate(ranked)}
    return sorted(picked, key=position.__getitem__)


class Retriever:
    def __init__(
        self,
        chunks: Sequence[Chunk],
        *,
        index: KnowledgeIndex | None,
        embedder: Embedder | None,
        glossary: dict[str, str],
        top_k: int = 6,
        max_context_tokens: int = 2000,
        min_score: float = 0.0,
    ) -> None:
        self._chunks = {chunk.id: chunk for chunk in chunks}
        self._ids = [chunk.id for chunk in chunks]
        self._bm25 = BM25Okapi([tokenize(chunk.text) for chunk in chunks]) if chunks else None
        self._index = index
        self._embedder = embedder
        self._glossary = glossary
        self.top_k = top_k
        self.max_context_tokens = max_context_tokens
        self.min_score = min_score

    @property
    def vector_enabled(self) -> bool:
        return self._index is not None and self._embedder is not None

    def _bm25_ranking(self, query: str) -> Ranking:
        tokens = tokenize(query)
        if not self._bm25 or not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return ranks_from_scores(
            [(self._ids[i], scores[i]) for i in ranked[:CANDIDATES] if scores[i] > 0]
        )

    def _vector_ranking(self, query: str, best: dict[str, float]) -> Ranking:
        if not self.vector_enabled:
            return []
        assert self._index is not None and self._embedder is not None
        hits = self._index.search(self._embedder.embed_query(query), CANDIDATES)
        kept = []
        for chunk_id, score in hits:
            if score >= self.min_score and chunk_id in self._chunks:
                kept.append((chunk_id, score))
                best[chunk_id] = max(score, best.get(chunk_id, 0.0))
        return ranks_from_scores(kept)

    def retrieve(self, message: str, previous_message: str | None = None) -> RetrievalResult:
        """Rank chunks for `message`; a previous user message helps resolve follow-ups."""
        started = time.perf_counter()
        current = expand_query(message, self._glossary)
        vector_scores: dict[str, float] = {}
        rankings = [self._vector_ranking(current, vector_scores), self._bm25_ranking(current)]
        if previous_message:
            # Follow-ups ("what language is it written in?") need the earlier topic. The
            # current message keeps its own lists, so a topic change still wins.
            combined = expand_query(f"{message} {previous_message}", self._glossary)
            rankings += [
                self._vector_ranking(combined, vector_scores),
                self._bm25_ranking(combined),
            ]

        fused = reciprocal_rank_fusion(rankings)
        ranked = diversify(
            sorted(fused, key=fused.__getitem__, reverse=True),
            lambda chunk_id: self._chunks[chunk_id].doc_id,
            self.top_k,
        )

        # Trim to the token budget: keep the best-scored chunks that fit.
        selected: list[ScoredChunk] = []
        used = dropped = 0
        for chunk_id in ranked:
            cost = estimate_tokens(self._chunks[chunk_id].text)
            if used + cost > self.max_context_tokens:
                dropped += 1
                continue
            used += cost
            selected.append(
                ScoredChunk(self._chunks[chunk_id], fused[chunk_id], vector_scores.get(chunk_id))
            )

        return RetrievalResult(
            chunks=selected,
            latency_ms=round((time.perf_counter() - started) * 1000),
            expanded_query=current,
            dropped_for_budget=dropped,
            notes=[] if self.vector_enabled else ["vector search unavailable: BM25 only"],
        )
