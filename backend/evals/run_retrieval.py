"""Retrieval eval: Recall@3, Recall@6 and MRR, split by language.

    cd backend && uv run python -m evals.run_retrieval [--model MODEL] [--bm25-only]

Uses a throwaway index directory, so comparing models never touches the app's index.
"""

import argparse
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.core.config import get_settings
from app.rag.chunking import Chunk
from app.rag.service import build_retriever
from app.services.knowledge_service import load_knowledge_service

CASES_FILE = Path(__file__).parent / "retrieval_cases.yaml"
K = 6


@dataclass
class Outcome:
    case_id: str
    lang: str
    rank: int | None  # 1-based rank of the first relevant chunk within the top K
    top: list[str]


def relevant(chunk: Chunk, expect: list[dict]) -> bool:
    return any(
        chunk.doc_id == item["doc_id"]
        and ("heading" not in item or chunk.heading == item["heading"])
        for item in expect
    )


def summarize(outcomes: list[Outcome]) -> tuple[float, float, float]:
    n = max(len(outcomes), 1)
    recall3 = sum(1 for o in outcomes if o.rank and o.rank <= 3) / n
    recall6 = sum(1 for o in outcomes if o.rank and o.rank <= 6) / n
    mrr = sum(1 / o.rank for o in outcomes if o.rank) / n
    return recall3, recall6, mrr


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="embedding model id (default: RAG_EMBEDDING_MODEL)")
    parser.add_argument("--embedder", choices=["onnx", "fake"], help="override RAG_EMBEDDER")
    parser.add_argument("--bm25-only", action="store_true", help="disable vector search")
    parser.add_argument("--min-score", type=float, help="override RAG_MIN_SCORE")
    parser.add_argument("--top-k", type=int, help="override RAG_TOP_K for the app-settings recall")
    parser.add_argument(
        "--max-context-tokens",
        type=int,
        help="override RAG_MAX_CONTEXT_TOKENS (app-settings recall)",
    )
    args = parser.parse_args()

    settings = get_settings()
    # What the chat really sends: the configured top_k and token budget (reported separately).
    app_top_k = args.top_k or settings.rag_top_k
    app_budget = args.max_context_tokens or settings.rag_max_context_tokens
    updates: dict[str, object] = {
        "rag_index_dir": Path(tempfile.mkdtemp(prefix="rag-eval-")),
        "rag_max_context_tokens": 100_000,  # rank quality only: no budget trimming
        "rag_top_k": K,
    }
    if args.model:
        updates["rag_embedding_model"] = args.model
    if args.embedder:
        updates["rag_embedder"] = args.embedder
    if args.min_score is not None:
        updates["rag_min_score"] = args.min_score
    settings = settings.model_copy(update=updates)

    knowledge = load_knowledge_service(settings.knowledge_base_dir)
    if knowledge is None:
        print("Knowledge base failed to load", file=sys.stderr)
        return 2
    retriever = build_retriever(knowledge.documents, settings)
    if args.bm25_only:
        retriever = build_retriever(
            knowledge.documents, settings.model_copy(update={"rag_embedder": "fake"})
        )
        retriever._index = None  # noqa: SLF001 - eval-only switch
    label = (
        "bm25-only"
        if args.bm25_only
        else ("fake" if settings.rag_embedder == "fake" else settings.rag_embedding_model)
    )

    app_retriever = build_retriever(
        knowledge.documents,
        settings.model_copy(update={"rag_top_k": app_top_k, "rag_max_context_tokens": app_budget}),
    )
    if args.bm25_only:
        app_retriever._index = None  # noqa: SLF001 - eval-only switch

    cases = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))["cases"]
    outcomes: list[Outcome] = []
    app_hits: dict[str, list[bool]] = {"en": [], "ar": []}
    app_misses: list[str] = []
    latencies: list[int] = []
    for case in cases:
        result = retriever.retrieve(case["query"], case.get("previous"))
        latencies.append(result.latency_ms)
        ranks = [
            i for i, hit in enumerate(result.chunks, start=1) if relevant(hit.chunk, case["expect"])
        ]
        top = [f"{h.chunk.doc_id}›{h.chunk.heading}"[:42] for h in result.chunks[:3]]
        outcomes.append(Outcome(case["id"], case["lang"], ranks[0] if ranks else None, top))
        sent = app_retriever.retrieve(case["query"], case.get("previous")).chunks
        hit = any(relevant(h.chunk, case["expect"]) for h in sent)
        app_hits[case["lang"]].append(hit)
        if not hit:
            app_misses.append(case["id"])

    average = sum(latencies) / len(latencies)
    print(f"Embedder: {label}   cases: {len(outcomes)}   avg latency: {average:.0f} ms\n")
    width = max(len(o.case_id) for o in outcomes)
    print(f"{'CASE'.ljust(width)}  LANG  RANK  TOP-3")
    for o in outcomes:
        rank = str(o.rank) if o.rank else "MISS"
        print(f"{o.case_id.ljust(width)}  {o.lang:4}  {rank:4}  {' | '.join(o.top)}")

    print(f"\n{'':6}{'Recall@3':>10}{'Recall@6':>10}{'MRR':>8}")
    for lang in ["en", "ar", "all"]:
        subset = [o for o in outcomes if lang == "all" or o.lang == lang]
        r3, r6, mrr = summarize(subset)
        print(f"{lang:6}{r3:>10.3f}{r6:>10.3f}{mrr:>8.3f}   (n={len(subset)})")
    total = [hit for hits in app_hits.values() for hit in hits]
    print(
        f"\nApp settings (top_k={app_top_k}, budget={app_budget} tokens): recall of what the "
        f"chat really sends = {sum(total) / len(total):.3f} "
        f"(en {sum(app_hits['en']) / max(len(app_hits['en']), 1):.3f}, "
        f"ar {sum(app_hits['ar']) / max(len(app_hits['ar']), 1):.3f})"
        + (f"  misses: {', '.join(app_misses)}" if app_misses else "")
    )
    en, ar = (summarize([o for o in outcomes if o.lang == lang])[1] for lang in ["en", "ar"])
    return 0 if en >= 0.9 and ar >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(main())
