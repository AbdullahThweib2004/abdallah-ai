"""ElevenLabs streaming text-to-speech over plain httpx (no SDK).

The API key is sent only as the `xi-api-key` header and is never logged. Error bodies are
inspected only for their status code (e.g. `quota_exceeded`), never logged verbatim.
"""

import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.core.limits import log_rate_limit, parse_duration
from app.voice.base import (
    Language,
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
            headers={"xi-api-key": api_key, "Accept": "audio/mpeg"},
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def stream(self, text: str, *, language: Language) -> AsyncIterator[bytes]:
        body = {"text": text, "model_id": self.model, "language_code": language}
        url = f"/v1/text-to-speech/{self._voices[language]}/stream"
        try:
            async with self._client.stream(
                "POST", url, params={"output_format": OUTPUT_FORMAT}, json=body
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
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
        except httpx.TimeoutException:
            raise VoiceUnavailableError("text-to-speech timed out") from None
        except httpx.TransportError:
            raise VoiceUnavailableError("text-to-speech connection failed") from None
