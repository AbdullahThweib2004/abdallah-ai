"""Provider-neutral speech interfaces (STT and TTS). Business logic depends only on this module.

Audio is passed around as bytes in memory. Providers must never write it to disk or log it.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

Language = Literal["en", "ar"]
LanguageHint = Literal["en", "ar", "auto"]


@dataclass(frozen=True)
class Transcription:
    text: str
    # ISO 639-1 code as reported by the provider ("en", "ar", "fa", ...), or None if unknown.
    language: str | None
    duration_ms: int | None
    # True when the provider is confident the clip contains no speech.
    no_speech: bool = False


@dataclass
class Alignment:
    """Character timestamps of synthesized speech, in seconds from the start of the clip:
    `chars[i]` is spoken from `starts[i]` to `ends[i]`."""

    chars: list[str]
    starts: list[float]
    ends: list[float]

    def to_json(self) -> dict[str, list]:
        return {
            "chars": self.chars,
            "starts": [round(t, 3) for t in self.starts],
            "ends": [round(t, 3) for t in self.ends],
        }

    @classmethod
    def from_json(cls, data: dict) -> "Alignment":
        return cls(list(data["chars"]), list(data["starts"]), list(data["ends"]))

    def extend(self, other: "Alignment") -> None:
        self.chars += other.chars
        self.starts += other.starts
        self.ends += other.ends


@dataclass(frozen=True)
class SpeechChunk:
    """A piece of synthesized audio, with the timestamps of the characters it completes."""

    audio: bytes
    alignment: Alignment | None = None


class VoiceError(Exception):
    """Provider failure. Messages must never contain secrets, audio or raw provider responses."""


class VoiceConfigError(VoiceError):
    """The provider is misconfigured (missing key, model or voice)."""


class VoiceUnavailableError(VoiceError):
    """The provider timed out, returned a 5xx/4xx, or could not be reached."""


class VoiceQuotaError(VoiceError):
    """The provider's quota or rate limit is exhausted (e.g. a free tier ran out)."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class VoiceRateLimitError(VoiceUnavailableError):
    """A short-lived provider limit (too many concurrent requests): retry later; the daily
    quota is fine."""


class STTProvider(Protocol):
    name: str
    model: str

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language: Language | None,
        prompt: str | None = None,
    ) -> Transcription:
        """Transcribe one short clip. `language=None` lets the provider detect it.

        `prompt` is a short vocabulary hint (names, technical terms) to improve spelling.
        """
        ...

    async def aclose(self) -> None: ...


class TTSProvider(Protocol):
    name: str
    model: str
    media_type: str

    def stream(self, text: str, *, language: Language) -> AsyncIterator[bytes]:
        """Synthesize already-cleaned text and yield audio bytes as they arrive."""
        ...

    def stream_timed(self, text: str, *, language: Language) -> AsyncIterator[SpeechChunk]:
        """Like `stream`, with character timestamps (seconds from the start of this clip)."""
        ...

    async def aclose(self) -> None: ...
