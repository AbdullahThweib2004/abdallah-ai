"""ElevenLabs streaming text-to-speech over plain httpx (no SDK).

The API key is sent only as the `xi-api-key` header and is never logged. Error bodies are
inspected only for their status code (e.g. `quota_exceeded`), never logged verbatim.
"""

import base64
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from app.core.limits import log_rate_limit, parse_duration
from app.voice.base import (
    Alignment,
    Language,
    SpeechChunk,
    VoiceQuotaError,
    VoiceRateLimitError,
    VoiceUnavailableError,
)

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.elevenlabs.io"
# 64 kb/s MP3 is plenty for speech and halves the bytes of the 128 kb/s default.
OUTPUT_FORMAT = "mp3_44100_64"
_QUOTA_CODES = {"quota_exceeded", "insufficient_credits", "payment_required"}


def _error_code(body: bytes) -> str:
    try:
        detail = json.loads(body).get("detail")
    except (ValueError, AttributeError):
        return ""
    if isinstance(detail, dict):
        return str(detail.get("status") or detail.get("code") or "")
    return ""


class ElevenLabsTTS:
    name = "elevenlabs"
    media_type = "audio/mpeg"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        voices: dict[Language, str],
        base_url: str = API_BASE_URL,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._voices = voices
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"xi-api-key": api_key},
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @asynccontextmanager
    async def _open(self, path: str, body: dict, accept: str) -> AsyncIterator[httpx.Response]:
        """POST and check the status; provider errors become VoiceErrors."""
        try:
            async with self._client.stream(
                "POST",
                path,
                params={"output_format": OUTPUT_FORMAT},
                json=body,
                headers={"Accept": accept},
            ) as response:
                if response.status_code != 200:
                    code = _error_code(await response.aread())
                    if response.status_code == 402 or code in _QUOTA_CODES:
                        log_rate_limit("elevenlabs", code or "quota", model=self.model)
                        raise VoiceQuotaError(f"text-to-speech quota ({response.status_code})")
                    if response.status_code == 429:
                        # Concurrency / system-busy limits: only this sentence falls back to
                        # the browser voice; the day's budget is NOT marked as used up.
                        retry_after = parse_duration(response.headers.get("retry-after"))
                        log_rate_limit(
                            "elevenlabs", code or "429", model=self.model, retry_after=retry_after
                        )
                        raise VoiceRateLimitError(f"text-to-speech rate limit (429, {code})")
                    suffix = f", {code}" if code else ""
                    raise VoiceUnavailableError(
                        f"text-to-speech failed ({response.status_code}{suffix})"
                    )
                yield response
        except httpx.TimeoutException:
            raise VoiceUnavailableError("text-to-speech timed out") from None
        except httpx.TransportError:
            raise VoiceUnavailableError("text-to-speech connection failed") from None

    def _body(self, text: str, language: Language) -> dict:
        return {"text": text, "model_id": self.model, "language_code": language}

    async def stream(self, text: str, *, language: Language) -> AsyncIterator[bytes]:
        url = f"/v1/text-to-speech/{self._voices[language]}/stream"
        async with self._open(url, self._body(text, language), "audio/mpeg") as response:
            async for chunk in response.aiter_bytes():
                if chunk:
                    yield chunk

    async def stream_timed(self, text: str, *, language: Language) -> AsyncIterator[SpeechChunk]:
        """`/stream/with-timestamps`: JSON objects with base64 audio and character alignment.

        Objects are read with `raw_decode`, so newline-delimited and back-to-back JSON both
        work. Chunk times are made absolute (from the start of the clip): a chunk whose times
        restart before the previous chunk ended is shifted by that end."""
        url = f"/v1/text-to-speech/{self._voices[language]}/stream/with-timestamps"
        decoder = json.JSONDecoder()
        buffer = ""
        offset = 0.0
        last_end = 0.0
        async with self._open(url, self._body(text, language), "application/json") as response:
            async for piece in response.aiter_text():
                buffer += piece
                while True:
                    buffer = buffer.lstrip()
                    if not buffer:
                        break
                    try:
                        item, size = decoder.raw_decode(buffer)
                    except ValueError:
                        break  # incomplete object: wait for more text
                    buffer = buffer[size:]
                    chunk, offset, last_end = _timed_chunk(item, offset, last_end)
                    if chunk is not None:
                        yield chunk


def _timed_chunk(
    item: object, offset: float, last_end: float
) -> tuple[SpeechChunk | None, float, float]:
    if not isinstance(item, dict):
        return None, offset, last_end
    audio = base64.b64decode(item.get("audio_base64") or "")
    raw = item.get("alignment")
    alignment = None
    if isinstance(raw, dict) and raw.get("characters"):
        starts = [float(t) for t in raw["character_start_times_seconds"]]
        ends = [float(t) for t in raw["character_end_times_seconds"]]
        if starts and starts[0] + offset < last_end - 0.05:
            offset = last_end  # chunk-relative times: continue from the previous chunk
        alignment = Alignment(
            list(raw["characters"]), [t + offset for t in starts], [t + offset for t in ends]
        )
        last_end = max(last_end, alignment.ends[-1])
    if not audio and alignment is None:
        return None, offset, last_end
    return SpeechChunk(audio, alignment), offset, last_end
