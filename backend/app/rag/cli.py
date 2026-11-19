"""RAG command line tools.

uv run python -m app.rag.cli build             # (re)build the index artifact (build hook)
uv run python -m app.rag.cli stats             # what is indexed
uv run python -m app.rag.cli query "<text>"    # ranked chunks with scores (debugging)
uv run python -m app.rag.cli download-models   # pre-fetch the embedding model
"""

import argparse
import sys
from collections.abc import Sequence

from app.core.config import get_settings
from app.rag.chunking import chunk_documents
from app.rag.embeddings import download_model
from app.rag.index import KnowledgeIndex, content_hash
from app.rag.service import build_embedder, build_retriever
from app.services.knowledge_service import load_knowledge_service


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.rag.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build", help="rebuild the index from approved documents")
    commands.add_parser("stats", help="show what is indexed")
    query = commands.add_parser("query", help="show ranked chunks for a question")
    query.add_argument("text")
    query.add_argument("--previous", help="previous user message (follow-up)")
    commands.add_parser("download-models", help="pre-fetch the embedding model files")
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.command == "download-models":
        download_model(settings.rag_embedding_model, settings.rag_models_dir)
        print(f"Cached {settings.rag_embedding_model} in {settings.rag_models_dir}")
        return 0

    knowledge = load_knowledge_service(settings.knowledge_base_dir)
    if knowledge is None:
        print("Knowledge base failed to load", file=sys.stderr)
        return 1

    if args.command == "build":
        chunks = chunk_documents(knowledge.documents)
        index = KnowledgeIndex(settings.rag_index_dir, build_embedder(settings))
        index.build(chunks)
        if not (settings.rag_index_dir / "index.json").is_file():
            print(f"Could not write the index to {settings.rag_index_dir}", file=sys.stderr)
            return 1
        print(f"Built index: {len(chunks)} chunks in {settings.rag_index_dir}")
        return 0

    if args.command == "stats":
        chunks = chunk_documents(knowledge.documents)
        index = KnowledgeIndex(settings.rag_index_dir, build_embedder(settings))
        up_to_date = index.stored_hash() == content_hash(chunks, index.stats()["embedder"])
        stats = index.stats()
        print(f"Index:        {settings.rag_index_dir}")
        for key, value in stats.items():
            print(f"{key + ':':13} {value}")
        print(f"{'up to date:':13} {up_to_date}")
        by_type: dict[str, int] = {}
        for chunk in chunks:
            by_type[chunk.type] = by_type.get(chunk.type, 0) + 1
        print("chunks/type:  " + ", ".join(f"{k} {v}" for k, v in sorted(by_type.items())))
        return 0

    retriever = build_retriever(knowledge.documents, settings)
    result = retriever.retrieve(args.text, args.previous)
    print(f"Query:    {args.text}")
    if result.expanded_query != args.text:
        print(f"Expanded: {result.expanded_query}")
    print(
        f"Latency:  {result.latency_ms} ms"
        + (f"  ({'; '.join(result.notes)})" if result.notes else "")
    )
    for rank, hit in enumerate(result.chunks, start=1):
        vector = f"{hit.vector_score:.3f}" if hit.vector_score is not None else "  -  "
        print(
            f"{rank:2}. rrf={hit.score:.4f} cos={vector}  {hit.chunk.doc_id} › {hit.chunk.heading}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
