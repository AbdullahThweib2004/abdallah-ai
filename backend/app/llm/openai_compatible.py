"""OpenAI-compatible chat completions (Groq, OpenRouter, OpenAI, Ollama) over plain httpx.

Only `choices[0].delta.content` is ever forwarded. Reasoning output (`reasoning`,
`reasoning_content`, `thinking`, ...) is discarded and never logged.
"""

import copy
import json
import logging
import math
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.limits import groq_limit_type, log_rate_limit
from app.core.tokens import estimate_tokens
from app.llm.base import (
    ChatMessage,
    LLMChunk,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    Usage,
)
from app.llm.rate_limits import RateLimitTracker

logger = logging.getLogger(__name__)


class _FailedBeforeFirstTokenError(Exception):
    """Internal: the attempt failed before any text was streamed, so a fallback is safe."""

    def __init__(self, error: LLMError) -> None:
        self.error = error


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return float(response.headers["retry-after"])
    except (KeyError, ValueError):
        return None


def estimate_input_tokens(messages: list[ChatMessage]) -> int:
    """Roughly what the provider will charge for the prompt (chat-template overhead incl.)."""
    return sum(estimate_tokens(message["content"]) + 4 for message in messages)


def _source_name(base_url: str) -> str:
    host = urlparse(base_url).hostname or "llm"
    return "groq" if host.endswith("groq.com") else host


def _usage_from(payload: dict[str, Any]) -> Usage | None:
    # OpenAI/OpenRouter put usage at the top level; Groq also sends it under `x_groq`.
    usage = payload.get("usage") or (payload.get("x_groq") or {}).get("usage")
    if not usage:
        return None
    return Usage(int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        fallback_model: str | None = None,
        reasoning_effort: str | None = None,
        timeout_seconds: float = 30.0,
        headroom_tokens: int = 300,
        tracker: RateLimitTracker | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._fallback_model = fallback_model if fallback_model != model else None
        self._reasoning_effort = reasoning_effort
        self._source = _source_name(base_url)
        # Tokens kept free on top of the prompt estimate (the answer, concurrent visitors).
        self._headroom = headroom_tokens
        self.tracker = tracker or RateLimitTracker()
        headers = {"Accept": "text/event-stream"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def primary_only(self) -> "OpenAICompatibleProvider":
        """The same provider (client, rate-limit tracker) without the fallback model: for
        background work such as the cache pre-warm, which only wants main-model answers."""
        clone = copy.copy(self)
        clone._fallback_model = None
        return clone

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        max_tokens: int,
        temperature: float,
        reasoning_effort: str | None = None,
    ) -> AsyncIterator[LLMChunk]:
        effort = reasoning_effort or self._reasoning_effort
        preferred = [self.model] + ([self._fallback_model] if self._fallback_model else [])
        needed = estimate_input_tokens(messages) + self._headroom
        decision = self.tracker.route(preferred, needed)
        for skip in decision.skipped:
            logger.info(
                "LLM routing: %s is near its %s limit (needs ~%d tokens, frees in %.1fs)%s",
                skip.model,
                skip.reason,
                needed,
                skip.wait_seconds,
                f"; using {decision.models[0]}" if decision.models else "",
            )
        if not decision.models:
            # Every model is predicted to be over its limit: answer "busy" without sending.
            wait = math.ceil(min(decision.wait_seconds or 60.0, 3600.0))
            first = decision.skipped[0]
            log_rate_limit("router", first.reason, model=first.model, retry_after=wait)
            raise LLMRateLimitError("all models near their rate limits", wait, first.reason)
        models = decision.models
        for attempt, model in enumerate(models):
            try:
                async for chunk in self._stream_model(
                    model, messages, max_tokens, temperature, effort
                ):
                    yield chunk
                return
            except _FailedBeforeFirstTokenError as failure:
                if attempt == len(models) - 1:
                    raise failure.error from None
                logger.warning(
                    "LLM model %s failed before the first token (%s); retrying once with %s",
                    model,
                    type(failure.error).__name__,
                    models[attempt + 1],
                )

    async def _stream_model(
        self,
        model: str,
        messages: list[ChatMessage],
        max_tokens: int,
        temperature: float,
        reasoning_effort: str | None,
    ) -> AsyncIterator[LLMChunk]:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream_options": {"include_usage": True},
        }
        if reasoning_effort:
            body["reasoning_effort"] = reasoning_effort

        streamed_text = False
        usage: Usage | None = None
        try:
            async with self._client.stream("POST", "/chat/completions", json=body) as response:
                self.tracker.observe(model, response.headers)
                if response.status_code != 200:
                    await response.aread()
                    raise self._status_error(response, model)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    payload = json.loads(data)
                    if "error" in payload:
                        raise LLMUnavailableError("provider reported an error in the stream")
                    usage = _usage_from(payload) or usage
                    choices = payload.get("choices") or []
                    delta = (choices[0].get("delta") or {}) if choices else {}
                    text = delta.get("content")
                    if text:
                        streamed_text = True
                        yield LLMChunk(text=text)
        except httpx.TimeoutException:
            error: LLMError = LLMTimeoutError("provider timed out")
            if streamed_text:
                raise error from None
            raise _FailedBeforeFirstTokenError(error) from None
        except (httpx.TransportError, json.JSONDecodeError):
            error = LLMUnavailableError("provider connection failed")
            if streamed_text:
                raise error from None
            raise _FailedBeforeFirstTokenError(error) from None
        except (LLMRateLimitError, LLMUnavailableError) as error:
            if streamed_text:
                raise
            raise _FailedBeforeFirstTokenError(error) from None

        if usage:
            self.tracker.spend(model, usage.output_tokens)
        yield LLMChunk(usage=usage or Usage(), model=model)

    def _status_error(self, response: httpx.Response, model: str) -> LLMError:
        status = response.status_code
        if status == 429:
            retry_after = _retry_after(response)
            limit = groq_limit_type(response.content)
            self.tracker.block(model, retry_after)
            log_rate_limit(self._source, limit, model=model, retry_after=retry_after)
            return LLMRateLimitError("provider rate limit (429)", retry_after, limit)
        if status >= 500:
            return LLMUnavailableError(f"provider unavailable ({status})")
        # 4xx: bad key, bad model or bad parameters. Retrying another model will not help.
        return LLMError(f"provider rejected the request ({status})")
