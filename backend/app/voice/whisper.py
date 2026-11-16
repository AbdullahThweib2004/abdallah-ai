"""Whisper speech-to-text over an OpenAI-compatible `/audio/transcriptions` endpoint (Groq,
OpenAI, or a local whisper server), using plain httpx. The audio stays in memory."""

import logging
from typing import Any

import httpx

from app.voice.base import (
    Language,
    Transcription,
    VoiceError,
    VoiceQuotaError,
    VoiceUnavailableError,
)

logger = logging.getLogger(__name__)

# Whisper's verbose_json reports the language as an English name on some servers (Groq:
# "Arabic") and as an ISO code on others; normalize the ones we care about.
_LANGUAGE_NAMES = {"english": "en", "arabic": "ar"}

# A segment counts as non-speech above this probability (Whisper's own default threshold).
NO_SPEECH_THRESHOLD = 0.6


def _language_code(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip().lower()
    return _LANGUAGE_NAMES.get(value, value if len(value) <= 3 else None)


def _no_speech(segments: list[dict[str, Any]]) -> bool:
    if not segments:
        return True
    return all(float(s.get("no_speech_prob", 0)) > NO_SPEECH_THRESHOLD for s in segments)


class WhisperSTT:
    name = "groq"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language: Language | None,
        prompt: str | None = None,
    ) -> Transcription:
        data = {"model": self.model, "response_format": "verbose_json", "temperature": "0"}
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt
        try:
            response = await self._client.post(
                "/audio/transcriptions",
                data=data,
                files={"file": (filename, audio, content_type)},
            )
        except httpx.TimeoutException:
            raise VoiceUnavailableError("speech-to-text timed out") from None
        except httpx.TransportError:
            raise VoiceUnavailableError("speech-to-text connection failed") from None

        if response.status_code == 429:
            raise VoiceQuotaError("speech-to-text rate limit (429)")
        if response.status_code != 200:
            raise VoiceUnavailableError(f"speech-to-text failed ({response.status_code})")
        try:
            payload = response.json()
        except ValueError:
            raise VoiceError("speech-to-text returned invalid JSON") from None

        duration = payload.get("duration")
        return Transcription(
            text=str(payload.get("text") or "").strip(),
            language=_language_code(payload.get("language")),
            duration_ms=round(float(duration) * 1000) if duration is not None else None,
            no_speech=_no_speech(payload.get("segments") or []),
        )
