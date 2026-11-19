"""Voice endpoints: speech-to-text, text-to-speech and the active-provider config.

Audio is read into memory with a hard size cap, parsed in memory, sent to the STT provider
and dropped at the end of the request. It is never written to disk or logged.
"""

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from app.api.v1.chat import _client_key
from app.core.limits import log_rate_limit
from app.models.voice import (
    MAX_AUDIO_BYTES,
    MAX_AUDIO_MS,
    MAX_SPEAK_CHARS,
    SpeakRequest,
    STTConfig,
    TranscribeForm,
    TranscribeResponse,
    TTSConfig,
    VoiceConfigResponse,
    VoiceErrorCode,
    VoiceErrorResponse,
)
from app.services.multipart import MultipartError, parse_multipart
from app.services.rate_limit import LIMIT_NAMES
from app.services.voice_service import VoiceRequestError, speak, transcribe

router = APIRouter(prefix="/voice", tags=["voice"])

# Multipart framing (boundaries, headers, the language field) on top of the audio itself.
MAX_BODY_BYTES = MAX_AUDIO_BYTES + 16 * 1024

_LIMIT_DETAILS = {
    "rate_limited": "Too many voice requests. Please wait a minute.",
    "daily_limit": "Daily voice limit reached for this visitor.",
    "daily_cap": "Daily voice limit reached.",
}

_ERRORS = {
    status.HTTP_413_CONTENT_TOO_LARGE: {"model": VoiceErrorResponse},
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"model": VoiceErrorResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": VoiceErrorResponse},
    status.HTTP_429_TOO_MANY_REQUESTS: {"model": VoiceErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": VoiceErrorResponse},
}


def _error(code: VoiceErrorCode, status_code: int, detail: str, **headers: str) -> JSONResponse:
    payload = VoiceErrorResponse(detail=detail, code=code)
    return JSONResponse(payload.model_dump(), status_code=status_code, headers=headers or None)


def _rate_limited(request: Request, limiter_name: str) -> JSONResponse | None:
    decision = getattr(request.app.state, limiter_name).check(_client_key(request))
    if decision.allowed:
        return None
    assert decision.reason is not None
    route = "tts" if limiter_name == "tts_rate_limiter" else "voice"
    log_rate_limit(
        "app", LIMIT_NAMES[decision.reason], route=route, retry_after=decision.retry_after
    )
    return _error(
        decision.reason,
        status.HTTP_429_TOO_MANY_REQUESTS,
        _LIMIT_DETAILS[decision.reason],
        **{"Retry-After": str(decision.retry_after or 60)},
    )


async def _read_capped_body(request: Request) -> bytes | None:
    """The raw body, or None as soon as it exceeds MAX_BODY_BYTES."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        return None
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    responses=_ERRORS,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["audio"],
                        "properties": {
                            "audio": {
                                "type": "string",
                                "format": "binary",
                                "description": "webm/opus, ogg, wav or m4a; ≤ 30 s, ≤ 2 MB",
                            },
                            "language_hint": {"type": "string", "enum": ["en", "ar", "auto"]},
                        },
                    }
                }
            },
        }
    },
)
async def transcribe_audio(request: Request) -> TranscribeResponse | JSONResponse:
    if limited := _rate_limited(request, "voice_rate_limiter"):
        return limited
    body = await _read_capped_body(request)
    if body is None:
        return _error("too_large", 413, "Audio must be 2 MB or smaller.")
    try:
        parts = parse_multipart(body, request.headers.get("content-type", ""))
        audio = parts.pop("audio", None)
        if audio is None or audio.filename is None:
            raise MultipartError("missing audio file")
        form = TranscribeForm.model_validate(
            {name: part.data.decode("utf-8") for name, part in parts.items()}
        )
    except (MultipartError, ValidationError, UnicodeDecodeError):
        return _error("invalid_request", 422, "Send multipart form data with an audio file.")
    del body  # keep only one copy of the audio in memory

    data = audio.data
    if len(data) > MAX_AUDIO_BYTES:
        return _error("too_large", 413, "Audio must be 2 MB or smaller.")
    if not data:
        return _error("no_speech", 422, "No speech was detected.")
    try:
        return await transcribe(
            request.app.state.stt,
            data,
            audio.content_type,
            form.language_hint,
            request.app.state.stt_vocabulary,
        )
    except VoiceRequestError as exc:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else {}
        return _error(exc.code, exc.status, exc.detail, **headers)


@router.post(
    "/speak",
    response_class=StreamingResponse,
    response_model=None,
    responses={200: {"content": {"audio/mpeg": {}}, "description": "Streamed MP3"}, **_ERRORS},
)
async def speak_text(body: SpeakRequest, request: Request) -> StreamingResponse | JSONResponse:
    if limited := _rate_limited(request, "tts_rate_limiter"):
        return limited
    try:
        tts = request.app.state.tts
        settings = request.app.state.settings
        voice_id = settings.tts_voice_ar if body.language == "ar" else settings.tts_voice_en
        speech = await speak(
            tts,
            request.app.state.tts_budget,
            body.text,
            body.language,
            cache=request.app.state.answer_cache,
            voice=f"{tts.name}:{tts.model}:{voice_id}" if tts else "",
        )
    except VoiceRequestError as exc:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else {}
        return _error(exc.code, exc.status, exc.detail, **headers)
    return StreamingResponse(
        speech.chunks,
        media_type=speech.media_type,
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/config", response_model=VoiceConfigResponse)
def voice_config(request: Request) -> VoiceConfigResponse:
    stt = request.app.state.stt
    tts = request.app.state.tts
    return VoiceConfigResponse(
        stt=STTConfig(
            provider=stt.name if stt else "none",
            max_seconds=MAX_AUDIO_MS // 1000,
            max_bytes=MAX_AUDIO_BYTES,
        ),
        # A misconfigured server provider degrades to the browser voice.
        tts=TTSConfig(provider=tts.name if tts else "browser", max_chars=MAX_SPEAK_CHARS),
    )
