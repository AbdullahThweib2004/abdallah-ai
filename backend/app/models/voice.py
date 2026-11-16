from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

MAX_AUDIO_BYTES = 2 * 1024 * 1024
MAX_AUDIO_MS = 30_000
# Container timestamps can overshoot by a frame or two; allow a little slack.
AUDIO_MS_TOLERANCE = 500
# Shorter clips are a click, not a question.
MIN_AUDIO_MS = 300
MAX_SPEAK_CHARS = 600

VoiceErrorCode = Literal[
    "unsupported_type",
    "too_large",
    "too_long",
    "no_speech",
    "invalid_request",
    "nothing_to_say",
    "rate_limited",
    "daily_limit",
    "daily_cap",
    "tts_quota",
    "stt_unavailable",
    "tts_unavailable",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TranscribeForm(_Strict):
    """The non-file fields of the multipart transcribe request."""

    language_hint: Literal["en", "ar", "auto"] = "auto"


class TranscribeResponse(_Strict):
    text: str
    language: Literal["en", "ar"]
    duration_ms: int


class SpeakRequest(_Strict):
    text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_SPEAK_CHARS)
    ]
    language: Literal["en", "ar"]


class VoiceErrorResponse(_Strict):
    """`detail` is English for developers; the frontend shows its own text per `code`."""

    detail: str
    code: VoiceErrorCode


class STTConfig(_Strict):
    # "none": voice input is unavailable (misconfigured provider); the UI stays text-only.
    provider: Literal["fake", "groq", "none"]
    max_seconds: int
    max_bytes: int


class TTSConfig(_Strict):
    provider: Literal["fake", "browser", "elevenlabs"]
    max_chars: int


class VoiceConfigResponse(_Strict):
    stt: STTConfig
    tts: TTSConfig
