"""Pre-warm the answer cache at startup with the home page's suggestion chips (EN + AR).

Runs in the background, one question at a time, through the normal chat pipeline (so the
cached replies are exactly what a visitor would get). It never competes for the provider's
rate limits: the limit-aware router answers "busy" (with a wait) instead of sending when a
model is near its limit, and then this task waits and retries. Questions already in the
cache (e.g. loaded from disk) cost nothing.
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from app.core.config import Settings
from app.llm.base import LLMProvider
from app.models.chat import ChatRequest
from app.rag.retriever import Retriever
from app.services.answer_cache import AnswerCache
from app.services.chat_service import chat_events
from app.services.language import detect_language

logger = logging.getLogger(__name__)

# The suggestion chips of the home page, exactly as in frontend/lib/i18n/{en,ar}.ts
# (tests/test_answer_cache.py checks that both stay in sync).
SUGGESTIONS: dict[str, list[str]] = {
    "en": [
        "What's his strongest project?",
        "Tell me about his training at Bank of Palestine",
        "What does he know about RAG and MCP?",
        "How can I contact him?",
    ],
    "ar": [
        "ما أقوى مشاريعه؟",
        "حدّثني عن تدريبه في بنك فلسطين",
        "ماذا يعرف عن RAG و MCP؟",
        "كيف يمكنني التواصل معه؟",
    ],
}

MAX_ATTEMPTS = 4
MAX_WAIT_SECONDS = 120.0
PAUSE_SECONDS = 2.0  # between questions, leaving room for visitors


@dataclass(frozen=True)
class PrewarmReport:
    cached: int = 0  # newly answered and stored
    already: int = 0  # were in the cache already
    failed: int = 0


def suggestion_requests() -> list[ChatRequest]:
    return [
        ChatRequest(message=text, ui_language=language)  # type: ignore[arg-type]
        for language, texts in SUGGESTIONS.items()
        for text in texts
    ]


async def _ask_once(
    request: ChatRequest,
    *,
    provider: LLMProvider,
    retriever: Retriever,
    identity: str,
    settings: Settings,
    projects: Sequence[tuple[str, str]],
    cache: AnswerCache,
) -> tuple[bool, float | None]:
    """(answered, retry_after if the provider was busy)."""
    async for event in chat_events(
        f"prewarm-{uuid.uuid4().hex[:8]}",
        request,
        provider=provider,
        retriever=retriever,
        identity=identity,
        settings=settings,
        projects=projects,
        cache=cache,
    ):
        if event.startswith("event: done"):
            return True, None
        if event.startswith("event: error"):
            payload = json.loads(event.split("data: ", 1)[1])
            if payload.get("code") == "busy":
                return False, float(payload.get("retry_after") or 20)
            return False, None
    return False, None


async def prewarm(
    *,
    provider: LLMProvider,
    retriever: Retriever,
    identity: str,
    settings: Settings,
    projects: Sequence[tuple[str, str]],
    cache: AnswerCache,
    requests: Sequence[ChatRequest] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    delay_seconds: float = 0.0,
) -> PrewarmReport:
    cached = already = failed = 0
    sent_any = False
    # Only main-model answers are cached, so never spend fallback-model tokens here: a limit
    # on the main model comes back as `busy` and the pre-warm waits instead.
    provider = getattr(provider, "primary_only", lambda: provider)()
    if delay_seconds:
        await sleep(delay_seconds)
    for request in requests if requests is not None else suggestion_requests():
        language = detect_language(request.message, request.ui_language)
        if await cache.get(cache.key_for(request.message, language)) is not None:
            already += 1
            continue
        if sent_any:
            await sleep(PAUSE_SECONDS)
        sent_any = True
        for _attempt in range(MAX_ATTEMPTS):
            answered, retry_after = await _ask_once(
                request,
                provider=provider,
                retriever=retriever,
                identity=identity,
                settings=settings,
                projects=projects,
                cache=cache,
            )
            if answered:
                # Answered, but stored only if it came from the main model and passed the rule
                # checks (see chat_service._cacheable).
                key = cache.key_for(request.message, language)
                if await cache.get(key) is not None:
                    cached += 1
                else:
                    failed += 1
                break
            if retry_after is None:  # a real failure, not a limit: skip this question
                failed += 1
                break
            await sleep(min(retry_after, MAX_WAIT_SECONDS))
        else:
            failed += 1
    report = PrewarmReport(cached, already, failed)
    logger.info(
        "Answer cache pre-warm done: %d new, %d already cached, %d failed",
        report.cached,
        report.already,
        report.failed,
    )
    return report
