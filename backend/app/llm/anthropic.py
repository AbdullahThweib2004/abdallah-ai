"""Anthropic Messages API streaming over plain httpx (optional provider).

Only `text_delta` content is forwarded; `thinking` blocks are discarded.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.base import (
    ChatMessage,
    LLMChunk,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    Usage,
)

API_VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.anthropic.com",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"x-api-key": api_key, "anthropic-version": API_VERSION},
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def stream(
        self, messages: list[ChatMessage], *, max_tokens: int, temperature: float
    ) -> AsyncIterator[LLMChunk]:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "messages": [
                {"role": m["role"], "content": m["content"]}
                for m in messages
                if m["role"] != "system"
            ],
        }
        if system:
            body["system"] = system

        input_tokens = output_tokens = 0
        try:
            async with self._client.stream("POST", "/v1/messages", json=body) as response:
                if response.status_code != 200:
                    await response.aread()
                    if response.status_code == 429:
                        raise LLMRateLimitError("provider rate limit (429)")
                    if response.status_code >= 500:
                        raise LLMUnavailableError(f"provider unavailable ({response.status_code})")
                    raise LLMError(f"provider rejected the request ({response.status_code})")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line.removeprefix("data:").strip())
                    kind = event.get("type")
                    if kind == "message_start":
                        usage = event.get("message", {}).get("usage", {})
                        input_tokens = int(usage.get("input_tokens", 0))
                    elif kind == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            yield LLMChunk(text=delta["text"])
                    elif kind == "message_delta":
                        output_tokens = int(event.get("usage", {}).get("output_tokens", 0))
                    elif kind == "error":
                        raise LLMUnavailableError("provider reported an error in the stream")
        except httpx.TimeoutException:
            raise LLMTimeoutError("provider timed out") from None
        except (httpx.TransportError, json.JSONDecodeError):
            raise LLMUnavailableError("provider connection failed") from None

        yield LLMChunk(usage=Usage(input_tokens, output_tokens), model=self.model)
