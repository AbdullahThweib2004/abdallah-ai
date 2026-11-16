"""Streams one chat turn as Server-Sent Events.

Events: `start` {request_id, language} → `token` {text}… → `done` {usage, latency_ms}, or an
`error` {code, message} at any point. The visitor's text is never logged.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

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
from app.services.chat_messages import ErrorCode, message
from app.services.language import Language, detect_language

logger = logging.getLogger("app.chat")

LANGUAGE_NAMES = {"en": "English", "ar": "Arabic"}


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def build_messages(
    system_prompt: str, request: ChatRequest, language: Language
) -> list[ChatMessage]:
    # The reply-language line goes last so the long prompt prefix stays identical (cacheable).
    system = f"{system_prompt}\n\n# Reply language\nReply in {LANGUAGE_NAMES[language]}."
    messages: list[ChatMessage] = [{"role": "system", "content": system}]
    messages += [{"role": turn.role, "content": turn.content} for turn in request.history]
    messages.append({"role": "user", "content": request.message})
    return messages


async def chat_events(
    request_id: str,
    request: ChatRequest,
    *,
    provider: LLMProvider | None,
    system_prompt: str | None,
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

    if provider is None or system_prompt is None:
        status = "unavailable"
        yield error("unavailable")
        _log(request_id, language, model, usage, started, status)
        return

    stream = provider.stream(
        build_messages(system_prompt, request, language),
        max_tokens=settings.llm_max_output_tokens,
        temperature=settings.llm_temperature,
    )
    try:
        while True:
            try:
                # Inactivity timeout: the server never waits forever on a silent provider.
                chunk = await asyncio.wait_for(anext(stream), timeout=settings.llm_timeout_seconds)
            except StopAsyncIteration:
                break
            if chunk.text:
                yield sse("token", {"text": chunk.text})
            if chunk.usage:
                usage, model = chunk.usage, chunk.model or model
        yield sse(
            "done",
            {
                "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
                "latency_ms": round((time.perf_counter() - started) * 1000),
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
    except GeneratorExit:
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
