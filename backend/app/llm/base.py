"""Provider-neutral LLM interface. Business logic depends only on this module."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class LLMChunk:
    """A piece of the final answer. The last chunk of a stream carries `usage` (and `model`)."""

    text: str = ""
    usage: Usage | None = None
    model: str | None = None


class LLMError(Exception):
    """Provider failure. Messages must never contain secrets or raw provider responses."""


class LLMConfigError(LLMError):
    """The provider is misconfigured (missing key, model or base URL)."""


class LLMTimeoutError(LLMError):
    """The provider did not respond in time."""


class LLMRateLimitError(LLMError):
    """The provider rejected the request with 429."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMUnavailableError(LLMError):
    """The provider returned a 5xx or could not be reached."""


class LLMProvider(Protocol):
    name: str
    model: str

    def stream(
        self, messages: list[ChatMessage], *, max_tokens: int, temperature: float
    ) -> AsyncIterator[LLMChunk]:
        """Stream the answer text only (never reasoning), ending with a usage chunk."""
        ...

    async def aclose(self) -> None: ...
