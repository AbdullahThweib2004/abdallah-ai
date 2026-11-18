"""Streams one chat turn as Server-Sent Events.

Retrieve the chunks relevant to the question, build the prompt from them, stream the answer.
Events: `start` {request_id, language} → `action` {actions} → `token` {text}… → `done`
{usage, latency_ms, sources}, or an `error` {code, message} at any point. The model's
`ACTIONS:` first line is cut from the stream, validated against the allowlist and sent as the
single `action` event before any token (see app/agents/actions.py). The visitor's text is
never logged.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import suppress
from typing import Any

from app.agents.actions import (
    PREFIX_DEADLINE_SECONDS,
    ActionPrefixParser,
    PrefixResult,
    dump_actions,
    validate_actions,
)
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
    system = (
        f"{system_prompt}\n\n# Reply language\nReply in {LANGUAGE_NAMES[language]}. "
        "Start with the ACTIONS line."
    )
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
    projects: Sequence[tuple[str, str]] = (),
) -> AsyncIterator[str]:
    """`projects` = approved (project_id, title) pairs: the prompt's catalog and the only ids
    a `show_project` action may use."""
    language = detect_language(request.message, request.ui_language)
    project_ids = frozenset(project_id for project_id, _ in projects)
    action_types: list[str] = []
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
        _log(request_id, language, model, usage, started, status, action_types)
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
    system_prompt = build_system_prompt(identity, retrieval.chunks, projects)

    stream = provider.stream(
        build_messages(system_prompt, request, language),
        max_tokens=settings.llm_max_output_tokens,
        temperature=settings.llm_temperature,
        reasoning_effort=reasoning_effort_for(language, settings),
    )
    parser = ActionPrefixParser()
    prefix_deadline: float | None = None
    pending: asyncio.Future | None = None

    def decision(result: PrefixResult) -> list[str]:
        actions = validate_actions(result.raw, project_ids)
        action_types.extend(action.type for action in actions)
        events = [sse("action", {"actions": dump_actions(actions)})]
        if result.text:
            events.append(sse("token", {"text": result.text}))
        return events

    try:
        while True:
            # A pending task (not wait_for) so the prefix deadline can fire without
            # cancelling the provider stream.
            if pending is None:
                pending = asyncio.ensure_future(anext(stream))
            timeout = settings.llm_timeout_seconds
            if prefix_deadline is not None and not parser.decided:
                timeout = min(timeout, max(0.0, prefix_deadline - time.monotonic()))
            done, _ = await asyncio.wait({pending}, timeout=timeout)
            if not done:
                if prefix_deadline is not None and not parser.decided:
                    if result := parser.deadline():
                        for event in decision(result):
                            yield event
                    continue
                # Inactivity timeout: the server never waits forever on a silent provider.
                raise TimeoutError
            finished, pending = pending, None
            try:
                chunk = finished.result()
            except StopAsyncIteration:
                break
            text = chunk.text.translate(_MARKDOWN_MARKERS)
            if text:
                if prefix_deadline is None:
                    prefix_deadline = time.monotonic() + PREFIX_DEADLINE_SECONDS
                fed = parser.feed(text)
                if isinstance(fed, PrefixResult):
                    for event in decision(fed):
                        yield event
                elif fed:
                    yield sse("token", {"text": fed})
            if chunk.usage:
                usage, model = chunk.usage, chunk.model or model
        if isinstance(rest := parser.finish(), PrefixResult):
            for event in decision(rest):
                yield event
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
        if pending is not None:
            pending.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await pending
        await stream.aclose()
        _log(request_id, language, model, usage, started, status, action_types)


def _log(
    request_id: str,
    language: str,
    model: str,
    usage: Usage,
    started: float,
    status: str,
    action_types: list[str],
) -> None:
    # Action TYPES only: never project ids from the model or anything the visitor wrote.
    logger.info(
        "chat request_id=%s language=%s model=%s input_tokens=%d output_tokens=%d "
        "latency_ms=%d status=%s actions=%s",
        request_id,
        language,
        model,
        usage.input_tokens,
        usage.output_tokens,
        round((time.perf_counter() - started) * 1000),
        status,
        ",".join(action_types) or "-",
    )
