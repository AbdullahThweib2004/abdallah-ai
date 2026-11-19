"""Voice orchestration: validate clips, call the STT/TTS adapters, enforce the TTS budget.

Privacy: audio bytes only ever live in memory for the duration of one request. Nothing here
writes audio to disk or logs it, and transcripts are not logged either (they are visitor
messages); only sizes, durations, languages and latencies are.
"""

import logging
import math
import re
import time
from collections import Counter
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Protocol

from app.core.limits import log_rate_limit
from app.core.redis import RedisError, UpstashRedis
from app.models.content import ProfileResponse, ProjectSummary
from app.models.voice import (
    AUDIO_MS_TOLERANCE,
    MAX_AUDIO_MS,
    MIN_AUDIO_MS,
    TranscribeResponse,
    VoiceErrorCode,
)
from app.services.answer_cache import AnswerCache
from app.services.language import detect_language
from app.services.rate_limit import DAY_SECONDS
from app.voice.audio import ALLOWED_TYPES, CANONICAL_TYPE, inspect_audio
from app.voice.base import (
    Language,
    LanguageHint,
    STTProvider,
    TTSProvider,
    VoiceError,
    VoiceQuotaError,
)
from app.voice.text import clean_for_speech

logger = logging.getLogger(__name__)

# Text Whisper is known to invent for silence or noise (subtitle credits from its training
# data). Nobody asks a portfolio these, so they are treated as "no speech".
_HALLUCINATIONS = {
    "ترجمة نانسي قنقر",
    "اشتركوا في القناة",
    "subtitles by the amara.org community",
    "thanks for watching",
    "thank you for watching",
}
_NORMALIZE = re.compile(r"[^\w\s.]+")
MAX_VOCABULARY_CHARS = 500


class VoiceRequestError(Exception):
    def __init__(
        self, code: VoiceErrorCode, status: int, detail: str, retry_after: int | None = None
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.status = status
        self.detail = detail
        self.retry_after = retry_after


# --- STT ----------------------------------------------------------------------------------------


def build_vocabulary(profile: ProfileResponse | None, projects: list[ProjectSummary]) -> str:
    """A short spelling hint for Whisper built from the knowledge base (names, project names,
    frequent technologies), e.g. so "عبدالله" is not transcribed as "عبد الله"."""
    terms: list[str] = []
    if profile:
        terms += [profile.name] + ([profile.name_ar] if profile.name_ar else [])
    # Short project names: "Nawa: Neural Network ..." -> "Nawa".
    terms += [re.split(r"[:(]", p.title)[0].strip() for p in projects]
    counts = Counter(tech for p in projects for tech in p.technologies)
    terms += [tech for tech, _ in counts.most_common(25)]
    vocabulary = ""
    for term in dict.fromkeys(t for t in terms if t):
        candidate = f"{vocabulary}, {term}" if vocabulary else term
        if len(candidate) > MAX_VOCABULARY_CHARS:
            break
        vocabulary = candidate
    return vocabulary + "." if vocabulary else ""


def validate_audio(data: bytes, content_type: str) -> tuple[str, int | None]:
    """Check the clip's real format and duration. Returns (canonical type, duration_ms)."""
    info = inspect_audio(data)
    declared = content_type.split(";")[0].strip().lower()
    if info is None or declared not in ALLOWED_TYPES[info.format]:
        raise VoiceRequestError(
            "unsupported_type", 415, "Audio must be webm/opus, ogg, wav or m4a."
        )
    if info.duration_ms is not None:
        _check_duration(info.duration_ms)
    return CANONICAL_TYPE[info.format], info.duration_ms


def _check_duration(duration_ms: int) -> None:
    if duration_ms > MAX_AUDIO_MS + AUDIO_MS_TOLERANCE:
        raise VoiceRequestError("too_long", 413, "Audio must be 30 seconds or shorter.")
    if duration_ms < MIN_AUDIO_MS:
        raise VoiceRequestError("no_speech", 422, "No speech was detected.")


def _is_hallucination(text: str) -> bool:
    normalized = _NORMALIZE.sub("", text).strip(" .").lower()
    return normalized in _HALLUCINATIONS


async def transcribe(
    stt: STTProvider | None,
    data: bytes,
    content_type: str,
    hint: LanguageHint,
    vocabulary: str,
) -> TranscribeResponse:
    if stt is None:
        raise VoiceRequestError("stt_unavailable", 503, "Voice input is not available.")
    media_type, container_ms = validate_audio(data, content_type)
    extension = media_type.split("/")[1].replace("mp4", "m4a")

    async def run(language: Language | None):
        return await stt.transcribe(
            data,
            filename=f"clip.{extension}",
            content_type=media_type,
            language=language,
            prompt=vocabulary or None,
        )

    started = time.perf_counter()
    try:
        result = await run(None if hint == "auto" else hint)
        # Auto-detection on a short clip sometimes picks a neighbouring language (Persian,
        # Urdu, ...). The site only speaks en/ar, so retry once with the script's language.
        if hint == "auto" and result.text and result.language not in (None, "en", "ar"):
            retry_language = detect_language(result.text, "en")
            logger.info("STT detected %s; retrying as %s", result.language, retry_language)
            result = await run(retry_language)
    except VoiceQuotaError as exc:
        # Groq's audio limit (logged by the adapter): a short wait, not a broken feature.
        raise VoiceRequestError(
            "rate_limited",
            429,
            "Too many voice requests. Please wait a moment.",
            math.ceil(exc.retry_after or 30),
        ) from None
    except VoiceError as exc:
        logger.warning("STT failed: %s", exc)
        raise VoiceRequestError(
            "stt_unavailable", 503, "Voice input is not available right now."
        ) from None

    duration_ms = container_ms if container_ms is not None else result.duration_ms
    if duration_ms is not None:
        _check_duration(duration_ms)
    text = result.text.strip()
    if not text or result.no_speech or _is_hallucination(text):
        raise VoiceRequestError("no_speech", 422, "No speech was detected.")

    if result.language in ("en", "ar"):
        language: Language = result.language  # type: ignore[assignment]
    else:
        language = detect_language(text, "ar" if hint == "ar" else "en")
    logger.info(
        "STT ok provider=%s model=%s bytes=%d audio_ms=%s language=%s latency_ms=%d",
        stt.name,
        stt.model,
        len(data),
        duration_ms,
        language,
        (time.perf_counter() - started) * 1000,
    )
    return TranscribeResponse(text=text, language=language, duration_ms=duration_ms or 0)


# --- TTS ----------------------------------------------------------------------------------------


class TTSBudget(Protocol):
    """Global daily budget of synthesized characters (UTC day)."""

    async def try_consume(self, chars: int) -> bool: ...

    async def refund(self, chars: int) -> None: ...

    async def exhaust(self) -> None: ...


class CharBudget:
    """In-memory budget (one process: local dev and tests)."""

    def __init__(self, per_day: int, clock: Callable[[], float] = time.time) -> None:
        self._per_day = per_day
        self._clock = clock
        self._day = -1
        self._used = 0

    def _roll(self) -> None:
        day = int(self._clock() // DAY_SECONDS)
        if day != self._day:
            self._day, self._used = day, 0

    def consume_now(self, chars: int) -> bool:
        self._roll()
        if self._used + chars > self._per_day:
            return False
        self._used += chars
        return True

    async def try_consume(self, chars: int) -> bool:
        return self.consume_now(chars)

    async def refund(self, chars: int) -> None:
        self._used = max(0, self._used - chars)

    async def exhaust(self) -> None:
        """The provider said its quota is gone: stop calling it until tomorrow."""
        self._roll()
        self._used = self._per_day

    @property
    def remaining(self) -> int:
        self._roll()
        return max(0, self._per_day - self._used)


# KEYS: today's counter. ARGV: chars, per_day, ttl seconds.
_CONSUME_SCRIPT = """
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
if used + tonumber(ARGV[1]) > tonumber(ARGV[2]) then return 0 end
redis.call('INCRBY', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 1
"""
_REFUND_SCRIPT = """
local left = tonumber(redis.call('GET', KEYS[1]) or '0') - tonumber(ARGV[1])
if left < 0 then left = 0 end
redis.call('SET', KEYS[1], left, 'EX', ARGV[2])
return left
"""


class RedisCharBudget:
    """The same budget shared by every serverless instance (Upstash Redis). Falls back to an
    in-memory budget (per instance) if Redis is unreachable."""

    def __init__(
        self,
        redis: UpstashRedis,
        per_day: int,
        *,
        scope: str,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._redis = redis
        self._per_day = per_day
        self._prefix = f"aa:{scope}:tts_chars"
        self._clock = clock
        self._fallback = CharBudget(per_day, clock)

    def _key(self) -> tuple[str, int]:
        now = self._clock()
        day = int(now // DAY_SECONDS)
        return f"{self._prefix}:{day}", int((day + 1) * DAY_SECONDS - now) + 3600

    async def try_consume(self, chars: int) -> bool:
        key, ttl = self._key()
        try:
            return bool(await self._redis.eval(_CONSUME_SCRIPT, [key], [chars, self._per_day, ttl]))
        except RedisError as exc:
            logger.warning("TTS budget: Redis unavailable (%s); in-memory fallback", exc)
            return self._fallback.consume_now(chars)

    async def refund(self, chars: int) -> None:
        key, ttl = self._key()
        try:
            await self._redis.eval(_REFUND_SCRIPT, [key], [chars, ttl])
        except RedisError:
            await self._fallback.refund(chars)

    async def exhaust(self) -> None:
        key, ttl = self._key()
        try:
            await self._redis.execute("SET", key, self._per_day, "EX", ttl)
        except RedisError:
            await self._fallback.exhaust()


@dataclass(frozen=True)
class SpeechStream:
    media_type: str
    chunks: AsyncIterator[bytes]


async def speak(
    tts: TTSProvider | None,
    budget: TTSBudget,
    text: str,
    language: Language,
    *,
    cache: AnswerCache | None = None,
    voice: str = "",
) -> SpeechStream:
    """Clean the text and start synthesis. Errors before the first audio byte raise
    VoiceRequestError (the browser then speaks this answer itself); later errors end the
    stream early and are only logged.

    Sentences of cached answers are served from `cache` (no provider call, no characters
    used); the first synthesis of such a sentence is stored once it completes. `voice`
    identifies the provider voice in the audio key."""
    if tts is None:
        raise VoiceRequestError("tts_unavailable", 503, "Server voice is not enabled.")
    spoken = clean_for_speech(text, language)
    if not spoken:
        raise VoiceRequestError("nothing_to_say", 422, "Nothing speakable in this text.")
    audio_key: str | None = None
    if cache is not None and await cache.speech_cacheable(text, language):
        audio_key = cache.audio_key(spoken, language, voice)
        if (audio := await cache.get_audio(audio_key)) is not None:
            logger.info("TTS cache hit chars=%d language=%s", len(spoken), language)

            async def cached() -> AsyncIterator[bytes]:
                yield audio

            return SpeechStream(tts.media_type, cached())
    if not await budget.try_consume(len(spoken)):
        log_rate_limit("app", "tts_daily_chars", route="tts")
        raise VoiceRequestError("tts_quota", 429, "Today's voice budget is used up.")

    started = time.perf_counter()
    chunks = tts.stream(spoken, language=language)
    try:
        first = await anext(chunks)
    except (VoiceError, StopAsyncIteration) as exc:
        await budget.refund(len(spoken))
        if isinstance(exc, VoiceQuotaError):
            await budget.exhaust()
        logger.warning("TTS failed before audio (%s); browser voice fallback", exc or "empty")
        raise VoiceRequestError(
            "tts_unavailable", 503, "Server voice is not available right now."
        ) from None
    logger.info(
        "TTS first byte provider=%s model=%s chars=%d language=%s ttfb_ms=%d",
        tts.name,
        tts.model,
        len(spoken),
        language,
        (time.perf_counter() - started) * 1000,
    )

    async def body() -> AsyncIterator[bytes]:
        parts = [first]
        yield first
        try:
            async for chunk in chunks:
                if audio_key:
                    parts.append(chunk)
                yield chunk
        except VoiceError as exc:
            logger.warning("TTS stream ended early: %s", exc)
            return
        if audio_key and cache is not None:  # only complete audio is ever cached
            await cache.put_audio(audio_key, b"".join(parts))

    return SpeechStream(tts.media_type, body())
