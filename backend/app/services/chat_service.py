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
import math
import re
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
from app.services.answer_cache import AnswerCache, CachedReply
from app.services.answer_quality import answer_problems
from app.services.chat_messages import ErrorCode, message
from app.services.language import Language, detect_language

logger = logging.getLogger("app.chat")

LANGUAGE_NAMES = {"en": "English", "ar": "Arabic"}
ARABIC_REMINDER = (
    'Write "عبدالله" as one word, and always put a space between an Arabic word or letter '
    '(و، ب، ل) and a following English word: "و React"، "و AI Developer Assistant"، never '
    '"وReact".'
)

# His email address (abdullahthweib…) sits in the context, so models drift to "Abdullah Thuweb".
ENGLISH_REMINDER = 'Write his name exactly "Abdallah" or "Abdallah Thuieb".'
# Answers are plain text: shown as subtitles now, spoken in step 7. Despite the prompt, models
# occasionally emit markdown emphasis or code marks; drop those characters before they reach
# the visitor. Removing them per character also handles "**" split across two tokens.
_MARKDOWN_MARKERS = str.maketrans("", "", "*`")
# Wait suggested to the visitor when a provider 429 names no Retry-After.
DEFAULT_BUSY_SECONDS = 20
# Cached answers are replayed in small pieces so they still "type in" like a live answer.
_CACHED_PIECE = re.compile(r"\S+\s*")
CACHED_WORDS_PER_TOKEN = 3


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
    # The most-missed rules, repeated where the model reads them last.
    system += " " + (ARABIC_REMINDER if language == "ar" else ENGLISH_REMINDER)
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


async def replay_cached(
    reply: CachedReply, started: float, delay_seconds: float
) -> AsyncIterator[str]:
    """The same events as a live answer: `action`, `token`s, `done` (with `cached: true`)."""
    yield sse("action", {"actions": reply.actions})
    words = _CACHED_PIECE.findall(reply.text)
    for index in range(0, len(words), CACHED_WORDS_PER_TOKEN):
        if index and delay_seconds:
            await asyncio.sleep(delay_seconds)
        yield sse("token", {"text": "".join(words[index : index + CACHED_WORDS_PER_TOKEN])})
    yield sse(
        "done",
        {
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "sources": reply.sources,
            "cached": True,
        },
    )


async def chat_events(
    request_id: str,
    request: ChatRequest,
    *,
    provider: LLMProvider | None,
    retriever: Retriever | None,
    identity: str,
    settings: Settings,
    projects: Sequence[tuple[str, str]] = (),
    cache: AnswerCache | None = None,
) -> AsyncIterator[str]:
    """`projects` = approved (project_id, title) pairs: the prompt's catalog and the only ids
    a `show_project` action may use. `cache`: first-turn answers are served from / stored in
    it (questions with history never are)."""
    language = detect_language(request.message, request.ui_language)
    project_ids = frozenset(project_id for project_id, _ in projects)
    action_types: list[str] = []
    started = time.perf_counter()
    usage = Usage()
    model = provider.model if provider else "none"
    status = "ok"

    def error(code: ErrorCode, retry_after: int | None = None) -> str:
        payload: dict[str, Any] = {"code": code, "message": message(code, request.ui_language)}
        if retry_after is not None:
            payload["retry_after"] = retry_after
        return sse("error", payload)

    yield sse("start", {"request_id": request_id, "language": language})

    # `is not None`: an empty cache is falsy (it has a length).
    cache_key = (
        cache.key_for(request.message, language)
        if cache is not None and not request.history
        else None
    )
    if cache is not None and cache_key and (cached := await cache.get(cache_key)):
        async for event in replay_cached(
            cached, started, settings.answer_cache_stream_delay_ms / 1000
        ):
            yield event
        action_types.extend(action["type"] for action in cached.actions)
        _log(request_id, language, "cache", usage, started, "cached", action_types)
        return

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

    answered = False
    answer_parts: list[str] = []
    dumped_actions: list[dict[str, Any]] = []

    def decision(result: PrefixResult) -> list[str]:
        actions = validate_actions(result.raw, project_ids)
        action_types.extend(action.type for action in actions)
        dumped_actions.extend(dump_actions(actions))
        events = [sse("action", {"actions": dump_actions(actions)})]
        if result.text:
            nonlocal answered
            answered = True
            answer_parts.append(result.text)
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
                    answered = True
                    answer_parts.append(fed)
                    yield sse("token", {"text": fed})
            if chunk.usage:
                usage, model = chunk.usage, chunk.model or model
        if isinstance(rest := parser.finish(), PrefixResult):
            for event in decision(rest):
                yield event
        if not answered:
            # e.g. only an ACTIONS line: never leave the visitor with a blank answer.
            status = "empty_answer"
            logger.warning("chat request_id=%s the model returned no answer text", request_id)
            yield error("unavailable")
            return
        sources = sources_of(retrieval)
        if (
            cache is not None
            and cache_key
            and _cacheable(request_id, model, provider.model, answer_parts)
        ):
            await cache.put(
                cache_key,
                CachedReply(
                    text="".join(answer_parts),
                    actions=dumped_actions,
                    sources=sources,
                    language=language,
                    model=model,
                ),
            )
        yield sse(
            "done",
            {
                "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "sources": sources,
            },
        )
    except (TimeoutError, LLMTimeoutError):
        status = "timeout"
        yield error("timeout")
    except LLMRateLimitError as exc:
        status = "busy"
        # The UI counts this down and re-enables the composer (Retry-After, else a default).
        yield error("busy", math.ceil(exc.retry_after or DEFAULT_BUSY_SECONDS))
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


def _cacheable(request_id: str, model: str, primary: str, parts: list[str]) -> bool:
    """A cached answer is replayed to everyone who asks the same first question, so only an
    answer from the main model that passes every global rule check is stored."""
    if model != primary:
        logger.info("chat request_id=%s answer not cached: fallback model %s", request_id, model)
        return False
    if problems := answer_problems("".join(parts)):
        # Rule names only (the answer is model output, but keep logs short and text-free).
        kinds = sorted({problem.split(" ")[0] for problem in problems})
        logger.warning(
            "chat request_id=%s answer not cached: failed rule checks %s", request_id, kinds
        )
        return False
    return True


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
