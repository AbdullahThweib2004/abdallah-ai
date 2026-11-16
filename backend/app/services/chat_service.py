"""Streams one chat turn as Server-Sent Events.

Retrieve the chunks relevant to the question, build the prompt from them, stream the answer.
Events: `start` {request_id, language} → `token` {text}… → `done` {usage, latency_ms, sources},
or an `error` {code, message} at any point. The visitor's text is never logged.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from app.agents.prompt import build_system_prompt
from app.core.config import Settings
from app.llm.base import (
    ChatMessage,
    LLMError,
    LLMProvider,
    LLMRateLimitError,
    LLMTimeoutError,
    Usage,
)
from app.models.chat import ChatRequest
from app.rag.retriever import RetrievalResult, Retriever
from app.services.chat_messages import ErrorCode, message
from app.services.language import Language, detect_language

logger = logging.getLogger("app.chat")

LANGUAGE_NAMES = {"en": "English", "ar": "Arabic"}

# Answers are plain text: shown as subtitles now, spoken in step 7. Despite the prompt, models
# occasionally emit markdown emphasis or code marks; drop those characters before they reach
# the visitor. Removing them per character also handles "**" split across two tokens.
_MARKDOWN_MARKERS = str.maketrans("", "", "*`")


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def previous_user_message(request: ChatRequest) -> str | None:
    return next((turn.content for turn in reversed(request.history) if turn.role == "user"), None)


def build_messages(
    system_prompt: str, request: ChatRequest, language: Language
) -> list[ChatMessage]:
    # The reply-language line goes last so the long prompt prefix stays identical (cacheable).
    system = f"{system_prompt}\n\n# Reply language\nReply in {LANGUAGE_NAMES[language]}."
    messages: list[ChatMessage] = [{"role": "system", "content": system}]
    messages += [{"role": turn.role, "content": turn.content} for turn in request.history]
    messages.append({"role": "user", "content": request.message})
    return messages


def sources_of(retrieval: RetrievalResult) -> list[dict[str, str]]:
    """Deduplicated sources for the UI (the retrieved set; the pinned identity is excluded)."""
    sources: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for hit in retrieval.chunks:
        key = (hit.chunk.doc_id, hit.chunk.heading)
        if key in seen:
            continue
        seen.add(key)
        source = {
            "doc_id": hit.chunk.doc_id,
            "title": hit.chunk.title,
            "heading": hit.chunk.heading,
        }
        if hit.chunk.project_id:
            source["project_id"] = hit.chunk.project_id
        sources.append(source)
    return sources


def reasoning_effort_for(language: Language, settings: Settings) -> str | None:
    if language == "ar" and settings.llm_reasoning_effort_ar:
        return settings.llm_reasoning_effort_ar
    return None  # the provider's default (LLM_REASONING_EFFORT)


async def chat_events(
    request_id: str,
    request: ChatRequest,
    *,
    provider: LLMProvider | None,
    retriever: Retriever | None,
    identity: str,
    settings: Settings,
) -> AsyncIterator[str]:
    language = detect_language(request.message, request.ui_language)
    started = time.perf_counter()
    usage = Usage()
    model = provider.model if provider else "none"
    status = "ok"

    def error(code: ErrorCode) -> str:
        return sse("error", {"code": code, "message": message(code, request.ui_language)})

    yield sse("start", {"request_id": request_id, "language": language})

    if provider is None or retriever is None:
        status = "unavailable"
        yield error("unavailable")
        _log(request_id, language, model, usage, started, status)
        return

    # Embedding a query is CPU work: keep it off the event loop.
    retrieval = await asyncio.to_thread(
        retriever.retrieve, request.message, previous_user_message(request)
    )
    logger.info(
        "retrieval request_id=%s latency_ms=%d chunks=%s dropped_for_budget=%d%s",
        request_id,
        retrieval.latency_ms,
        [f"{hit.chunk.id}:{hit.score:.4f}" for hit in retrieval.chunks],
        retrieval.dropped_for_budget,
        f" notes={retrieval.notes}" if retrieval.notes else "",
    )
    system_prompt = build_system_prompt(identity, retrieval.chunks)

    stream = provider.stream(
        build_messages(system_prompt, request, language),
        max_tokens=settings.llm_max_output_tokens,
        temperature=settings.llm_temperature,
        reasoning_effort=reasoning_effort_for(language, settings),
    )
    try:
        while True:
            try:
                # Inactivity timeout: the server never waits forever on a silent provider.
                chunk = await asyncio.wait_for(anext(stream), timeout=settings.llm_timeout_seconds)
            except StopAsyncIteration:
                break
            text = chunk.text.translate(_MARKDOWN_MARKERS)
            if text:
                yield sse("token", {"text": text})
            if chunk.usage:
                usage, model = chunk.usage, chunk.model or model
        yield sse(
            "done",
            {
                "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "sources": sources_of(retrieval),
            },
        )
    except (TimeoutError, LLMTimeoutError):
        status = "timeout"
        yield error("timeout")
    except LLMRateLimitError:
        status = "busy"
        yield error("busy")
    except LLMError as exc:
        status = "unavailable"
        logger.warning("chat request_id=%s provider error: %s", request_id, exc)
        yield error("unavailable")
    except (GeneratorExit, asyncio.CancelledError):
        # The visitor stopped or left: the provider stream is closed in `finally`.
        status = "client_disconnected"
        raise
    except Exception:
        status = "unavailable"
        logger.exception("chat request_id=%s unexpected failure", request_id)
        yield error("unavailable")
    finally:
        await stream.aclose()
        _log(request_id, language, model, usage, started, status)


def _log(
    request_id: str, language: str, model: str, usage: Usage, started: float, status: str
) -> None:
    logger.info(
        "chat request_id=%s language=%s model=%s input_tokens=%d output_tokens=%d "
        "latency_ms=%d status=%s",
        request_id,
        language,
        model,
        usage.input_tokens,
        usage.output_tokens,
        round((time.perf_counter() - started) * 1000),
        status,
    )
