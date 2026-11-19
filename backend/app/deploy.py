"""Build step for serverless deploys (Vercel runs it after installing dependencies):

    uv run python -m app.deploy            # what the Vercel build hook runs
    uv run python -m app.deploy --prewarm  # also pre-warm the answer cache now

1. Make the backend self-contained: copy the repo's `knowledge_base/` into `backend/` (the
   function bundle only contains the service directory), without `_private/`.
2. Download the embedding model (pinned revision) into `RAG_MODELS_DIR`.
3. Build the index artifact (vectors + BM25 tokens + content hash) into `RAG_INDEX_DIR`.
4. On production builds with Redis and an LLM configured: pre-warm the shared answer cache
   with the home page's suggestion chips (skips answers already cached; never fails the
   build). This replaces the startup pre-warm of a long-running server.
"""

import argparse
import asyncio
import logging
import os
import shutil
import sys
import time
from pathlib import Path

logger = logging.getLogger("app.deploy")

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_KB = BACKEND_DIR.parent / "knowledge_base"
BUNDLED_KB = BACKEND_DIR / "knowledge_base"
PRIVATE_PARTS = {"_private"}


def bundle_knowledge_base() -> None:
    if not REPO_KB.is_dir():
        if BUNDLED_KB.is_dir():
            logger.info("Knowledge base already bundled at %s", BUNDLED_KB)
            return
        raise SystemExit(f"Knowledge base not found at {REPO_KB}")
    if BUNDLED_KB.exists():
        shutil.rmtree(BUNDLED_KB)
    shutil.copytree(REPO_KB, BUNDLED_KB, ignore=shutil.ignore_patterns(*PRIVATE_PARTS))
    files = sum(1 for path in BUNDLED_KB.rglob("*.md"))
    logger.info("Knowledge base bundled: %d Markdown files -> %s", files, BUNDLED_KB)


async def prewarm_answers() -> None:
    from app.main import create_app
    from app.services.prewarm import prewarm

    app = create_app()
    async with app.router.lifespan_context(app):
        state = app.state
        if state.answer_cache is None or state.llm is None or state.retriever is None:
            logger.info("Pre-warm skipped (no answer cache, LLM or retriever)")
            return
        report = await prewarm(
            provider=state.llm,
            retriever=state.retriever,
            identity=state.identity,
            settings=state.settings,
            projects=state.projects,
            cache=state.answer_cache,
        )
        logger.info("Pre-warm: %s", report)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="app.deploy", description=__doc__)
    parser.add_argument("--prewarm", action="store_true", help="pre-warm even outside production")
    args = parser.parse_args(argv)
    started = time.perf_counter()

    if os.environ.get("VERCEL"):
        bundle_knowledge_base()
        os.environ.setdefault("KNOWLEDGE_BASE_DIR", str(BUNDLED_KB))

    from app.core.config import get_settings
    from app.rag.cli import main as rag_cli

    settings = get_settings()
    if rag_cli(["download-models"]) or rag_cli(["build"]):
        return 1

    production = os.environ.get("VERCEL_ENV") == "production"
    if (args.prewarm or production) and settings.redis_rest_url:
        try:
            asyncio.run(prewarm_answers())
        except Exception:  # noqa: BLE001 - a cold cache is fine; a failed deploy is not
            logger.exception("Pre-warm failed; the cache fills on first visits instead")
    logger.info("Deploy build step done in %.1fs", time.perf_counter() - started)
    return 0


if __name__ == "__main__":
    sys.exit(main())
