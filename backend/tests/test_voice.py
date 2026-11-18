"""Voice: /voice/transcribe, /voice/speak, /voice/config and the STT/TTS adapters.

Everything is offline: fake providers or httpx.MockTransport. Audio clips are synthesized in
memory (no audio files in the repo).
"""

import json
import logging
import struct
import tempfile
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.models.content import ProfileResponse, ProjectSummary
from app.services.voice_service import CharBudget, build_vocabulary
from app.voice.audio import inspect_audio
from app.voice.base import (
    Transcription,
    VoiceQuotaError,
    VoiceUnavailableError,
)
from app.voice.elevenlabs import ElevenLabsTTS
from app.voice.fake import FakeSTT, FakeTTS
from app.voice.text import clean_for_speech
from app.voice.whisper import WhisperSTT

TRANSCRIBE = "/api/v1/voice/transcribe"
SPEAK = "/api/v1/voice/speak"
CONFIG = "/api/v1/voice/config"
SECRET = "placeholder-voice-credential"


# --- synthetic audio ---------------------------------------------------------------------------


def wav(ms: int, rate: int = 16_000) -> bytes:
    """16-bit mono PCM WAV of `ms` milliseconds (a quiet ramp, not real speech)."""
    samples = rate * ms // 1000
    pcm = bytes((i // 7) % 3 for i in range(samples * 2))
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data"
    body += struct.pack("<I", len(pcm)) + pcm
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _ebml(element_id: bytes, payload: bytes, unknown_size: bool = False) -> bytes:
    size = (
        b"\x01\xff\xff\xff\xff\xff\xff\xff"
        if unknown_size
        else b"\x01" + len(payload).to_bytes(7, "big")
    )
    return element_id + size + payload


def webm(ms: int) -> bytes:
    """MediaRecorder-style WebM: unknown-size Segment/Cluster and no Duration element."""
    header = _ebml(b"\x1a\x45\xdf\xa3", _ebml(b"\x42\x82", b"webm"))
    blocks = b""
    for timecode in range(0, ms + 1, 20):
        relative = timecode % 10_000  # a new cluster every 10 s
        if relative == 0:
            blocks += _ebml(b"\x1f\x43\xb6\x75", b"", unknown_size=True)
            blocks += _ebml(b"\xe7", timecode.to_bytes(4, "big"))
        block = b"\x81" + struct.pack(">h", relative) + b"\x80" + b"\x00" * 8
        blocks += _ebml(b"\xa3", block)
    return header + _ebml(b"\x18\x53\x80\x67", blocks, unknown_size=True)


def ogg(ms: int) -> bytes:
    """Two Ogg pages; the last granule position (48 kHz for Opus) gives the duration."""

    def page(granule: int, payload: bytes) -> bytes:
        return b"OggS\x00\x00" + struct.pack("<q", granule) + b"\x00" * 13 + payload

    return page(0, b"OpusHead" + b"\x00" * 11) + page(ms * 48, b"\x00" * 64)


def upload(
    client: TestClient,
    data: bytes,
    content_type: str = "audio/wav",
    **fields: str,
) -> httpx.Response:
    return client.post(
        TRANSCRIBE, files={"audio": ("clip", data, content_type)}, data=fields or None
    )


@pytest.fixture
def stt() -> FakeSTT:
    return FakeSTT(text="What did he build?", language="en", duration_ms=2000)


@pytest.fixture
def tts() -> FakeTTS:
    return FakeTTS()


@pytest.fixture
def voice_client(make_client, fixture_kb: Path, stt: FakeSTT, tts: FakeTTS) -> TestClient:
    return make_client(fixture_kb, stt=stt, tts=tts)


# --- audio inspection --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("make", "fmt"), [(wav, "wav"), (webm, "webm"), (ogg, "ogg")], ids=["wav", "webm", "ogg"]
)
def test_inspect_audio_reads_format_and_duration(make: Callable[[int], bytes], fmt: str) -> None:
    info = inspect_audio(make(2500))
    assert info is not None
    assert info.format == fmt
    assert info.duration_ms is not None and abs(info.duration_ms - 2500) <= 20


def test_inspect_audio_m4a_and_unknown() -> None:
    mvhd = b"mvhd" + b"\x00" * 4 + struct.pack(">IIII", 0, 0, 1000, 4200)
    m4a = b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 12 + b"\x00\x00\x00\x6cmoov" + mvhd
    assert inspect_audio(m4a) == inspect_audio(m4a)
    info = inspect_audio(m4a)
    assert info is not None and info.format == "m4a" and info.duration_ms == 4200
    assert inspect_audio(b"ID3\x04" + b"\x00" * 100) is None  # MP3 is not accepted
    assert inspect_audio(b"") is None


# --- transcribe: validation --------------------------------------------------------------------


def test_transcribe_happy_path(voice_client: TestClient, stt: FakeSTT) -> None:
    response = upload(voice_client, wav(2000), language_hint="en")
    assert response.status_code == 200
    assert response.json() == {"text": "What did he build?", "language": "en", "duration_ms": 2000}
    assert stt.calls[0]["language"] == "en"
    assert stt.calls[0]["content_type"] == "audio/wav"
    # The vocabulary hint comes from the knowledge base (fixture names, not real facts).
    assert "Test Person" in str(stt.calls[0]["prompt"])


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (webm(1500), "audio/webm;codecs=opus"),
        (webm(1500), "video/webm"),
        (ogg(1500), "audio/ogg; codecs=opus"),
        (wav(1500), "audio/x-wav"),
    ],
    ids=["webm-opus", "webm-video-label", "ogg", "x-wav"],
)
def test_transcribe_accepts_browser_formats(
    voice_client: TestClient, stt: FakeSTT, data: bytes, content_type: str
) -> None:
    response = upload(voice_client, data, content_type)
    assert response.status_code == 200, response.json()
    assert stt.calls[0]["language"] is None  # language_hint defaults to auto
    assert abs(response.json()["duration_ms"] - 1500) <= 20


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (b"ID3\x04" + b"\x00" * 2000, "audio/mpeg"),  # MP3 is not an accepted format
        (b"plain text, not audio" * 50, "audio/wav"),  # lies about its type
        (wav(1000), "audio/webm"),  # real WAV declared as WebM
        (wav(1000), "text/plain"),
    ],
    ids=["mp3", "not-audio", "type-mismatch", "text-type"],
)
def test_transcribe_rejects_unsupported_types(
    voice_client: TestClient, stt: FakeSTT, data: bytes, content_type: str
) -> None:
    response = upload(voice_client, data, content_type)
    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_type"
    assert stt.calls == []


def test_transcribe_rejects_too_large(voice_client: TestClient, stt: FakeSTT) -> None:
    too_big = wav(10_000) + b"\x00" * (2 * 1024 * 1024)
    response = upload(voice_client, too_big)
    assert response.status_code == 413
    assert response.json()["code"] == "too_large"
    assert stt.calls == []


def test_transcribe_rejects_large_content_length_early(voice_client: TestClient) -> None:
    response = voice_client.post(
        TRANSCRIBE,
        content=b"x" * 10,
        headers={
            "Content-Type": "multipart/form-data; boundary=abc",
            "Content-Length": str(5 * 1024 * 1024),
        },
    )
    assert response.status_code == 413


@pytest.mark.parametrize("make", [wav, webm, ogg], ids=["wav", "webm", "ogg"])
def test_transcribe_rejects_too_long_before_calling_stt(
    voice_client: TestClient, stt: FakeSTT, make: Callable[[int], bytes]
) -> None:
    response = upload(voice_client, make(31_000), "audio/" + make.__name__)
    assert response.status_code == 413
    assert response.json()["code"] == "too_long"
    assert stt.calls == []


def test_transcribe_uses_provider_duration_when_container_has_none(
    make_client, fixture_kb: Path
) -> None:
    stt = FakeSTT(duration_ms=45_000)
    client = make_client(fixture_kb, stt=stt)
    m4a_without_mvhd = b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 200
    response = upload(client, m4a_without_mvhd, "audio/mp4")
    assert response.status_code == 413
    assert response.json()["code"] == "too_long"


@pytest.mark.parametrize(
    "result",
    [
        Transcription("", "en", 2000),
        Transcription("   ", None, 2000),
        Transcription("you", "en", 2000, no_speech=True),
        Transcription("ترجمة نانسي قنقر", "ar", 2000),
        Transcription("Thanks for watching!", "en", 2000),
    ],
    ids=["empty", "blank", "no-speech", "hallucination-ar", "hallucination-en"],
)
def test_transcribe_rejects_empty_or_silent_results(
    make_client, fixture_kb: Path, result: Transcription
) -> None:
    stt = FakeSTT(
        text=result.text,
        language=result.language,
        duration_ms=result.duration_ms,
        no_speech=result.no_speech,
    )
    response = upload(make_client(fixture_kb, stt=stt), wav(2000))
    assert response.status_code == 422
    assert response.json()["code"] == "no_speech"


def test_transcribe_rejects_tiny_and_empty_clips(voice_client: TestClient, stt: FakeSTT) -> None:
    assert upload(voice_client, wav(100)).json()["code"] == "no_speech"
    assert upload(voice_client, b"").json()["code"] == "no_speech"
    assert stt.calls == []


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"json": {"audio": "aGVsbG8="}},
        {"data": {"language_hint": "en"}},  # no file
        {"files": {"audio": ("c", wav(1000), "audio/wav")}, "data": {"language_hint": "fr"}},
        {"files": {"audio": ("c", wav(1000), "audio/wav")}, "data": {"model": "whisper"}},
        {"files": {"recording": ("c", wav(1000), "audio/wav")}},
    ],
    ids=["json-body", "no-file", "bad-hint", "extra-field", "wrong-field-name"],
)
def test_transcribe_rejects_malformed_requests(
    voice_client: TestClient, stt: FakeSTT, request_kwargs: dict
) -> None:
    response = voice_client.post(TRANSCRIBE, **request_kwargs)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert stt.calls == []


class _SequenceSTT(FakeSTT):
    def __init__(self, results: list[Transcription]) -> None:
        super().__init__()
        self._results = results

    async def transcribe(self, audio: bytes, **kwargs) -> Transcription:  # type: ignore[override]
        await super().transcribe(audio, **kwargs)
        return self._results[len(self.calls) - 1]


def test_transcribe_retries_when_auto_detects_another_language(
    make_client, fixture_kb: Path
) -> None:
    stt = _SequenceSTT(
        [Transcription("چه پروژه‌هایی ساخته؟", "fa", 2000), Transcription("ما مشاريعه؟", "ar", 2000)]
    )
    response = upload(make_client(fixture_kb, stt=stt), wav(2000), language_hint="auto")
    assert response.status_code == 200
    assert response.json()["text"] == "ما مشاريعه؟"
    assert response.json()["language"] == "ar"
    assert [call["language"] for call in stt.calls] == [None, "ar"]


def test_transcribe_language_falls_back_to_script(make_client, fixture_kb: Path) -> None:
    stt = FakeSTT(text="شو خبرته في FastAPI؟", language=None)
    response = upload(make_client(fixture_kb, stt=stt), wav(2000), language_hint="ar")
    assert response.json()["language"] == "ar"


def test_transcribe_provider_failure_is_a_friendly_503(make_client, fixture_kb: Path) -> None:
    stt = FakeSTT(error=VoiceUnavailableError("speech-to-text failed (500)"))
    response = upload(make_client(fixture_kb, stt=stt), wav(2000))
    assert response.status_code == 503
    assert response.json()["code"] == "stt_unavailable"


def test_transcribe_misconfigured_provider_disables_voice_input(
    make_client, fixture_kb: Path
) -> None:
    client = make_client(fixture_kb, stt_provider="groq", llm_base_url=None, llm_api_key=None)
    assert client.get(CONFIG).json()["stt"]["provider"] == "none"
    response = upload(client, wav(2000))
    assert response.status_code == 503
    assert response.json()["code"] == "stt_unavailable"


def test_transcribe_rate_limit(make_client, fixture_kb: Path) -> None:
    client = make_client(fixture_kb, stt=FakeSTT(), voice_rate_per_minute=2)
    assert upload(client, wav(1000)).status_code == 200
    assert upload(client, wav(1000)).status_code == 200
    limited = upload(client, wav(1000))
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"
    assert "Retry-After" in limited.headers


# --- transcribe: privacy -----------------------------------------------------------------------


def test_no_audio_is_written_to_disk_or_logged(
    voice_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Every temporary file Python creates now lands here. 1.9 MB is above the 1 MB that
    # Starlette's UploadFile would spool to disk.
    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(spool))
    clip = wav(29_000, rate=32_000)
    assert 1_800_000 < len(clip) < 2 * 1024 * 1024

    with caplog.at_level(logging.DEBUG):
        response = upload(voice_client, clip)

    assert response.status_code == 200
    assert list(spool.iterdir()) == []
    log = caplog.text
    assert "What did he build?" not in log  # transcripts are visitor messages
    assert clip[44:80].hex() not in log
    assert "bytes=" in log  # metadata only


# --- speak: text cleaning ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "language", "expected"),
    [
        (
            "See his code at https://github.com/example/repo.",
            "en",
            "See his code.",
        ),
        (
            "His GitHub is github.com/example, and LinkedIn too.",
            "en",
            "His GitHub is, and LinkedIn too.",
        ),
        ("Email test@example.com to reach him.", "en", "Email his email to reach him."),
        ("Write to mailto:test@example.com.", "en", "Write to his email."),
        ("راسله على test@example.com.", "ar", "راسله على بريده الإلكتروني."),
        ("**Nawa** is a `C++` engine.", "en", "Nawa is a C++ engine."),
        ("## Projects\n- Alpha\n- Beta", "en", "Projects Alpha Beta"),
        ("Read the [docs](https://example.com/docs) first.", "en", "Read the docs first."),
        (
            "Recall@5 reached 97.15 percent [source: nawa › Results].",
            "en",
            "Recall@5 reached 97.15 percent.",
        ),
        ("It uses Node.js and ASP.NET.", "en", "It uses Node.js and ASP.NET."),
        (
            "بنى نظام RAG بلغة Python (المصدر: rag-ai-assistant › Summary).",
            "ar",
            "بنى نظام RAG بلغة Python.",
        ),
        (
            "المشروع على https://github.com/x، وهو مفتوح المصدر.",
            "ar",
            "المشروع على، وهو مفتوح المصدر.",
        ),
        ("استخدم Python وReact بـMCP.", "ar", "استخدم Python و React بـ MCP."),
        ("https://example.com", "en", ""),
        ("*** --- ***", "en", ""),
    ],
    ids=[
        "url",
        "bare-domain",
        "email-en",
        "mailto",
        "email-ar",
        "markdown-inline",
        "markdown-block",
        "markdown-link",
        "source-label-and-decimal",
        "dotted-terms",
        "arabic-source-label",
        "arabic-url",
        "arabic-latin-spacing",
        "only-url",
        "only-symbols",
    ],
)
def test_clean_for_speech(text: str, language: str, expected: str) -> None:
    assert clean_for_speech(text, language) == expected  # type: ignore[arg-type]


# --- speak: endpoint ---------------------------------------------------------------------------


def test_speak_streams_audio_of_the_cleaned_text(voice_client: TestClient, tts: FakeTTS) -> None:
    response = voice_client.post(
        SPEAK, json={"text": "**Hello**, email me at a@b.com.", "language": "en"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["cache-control"] == "no-store"
    assert response.content.startswith(b"\xff\xfb")
    assert tts.calls == [("Hello, email me at his email.", "en")]


@pytest.mark.parametrize(
    "body",
    [
        {"text": "", "language": "en"},
        {"text": "x" * 601, "language": "en"},
        {"text": "hi", "language": "fr"},
        {"text": "hi"},
        {"text": "hi", "language": "en", "voice": "someone-else"},
    ],
    ids=["empty", "too-long", "bad-language", "no-language", "extra-field"],
)
def test_speak_validation(voice_client: TestClient, tts: FakeTTS, body: dict) -> None:
    assert voice_client.post(SPEAK, json=body).status_code == 422
    assert tts.calls == []


def test_speak_nothing_speakable(voice_client: TestClient, tts: FakeTTS) -> None:
    response = voice_client.post(SPEAK, json={"text": "https://example.com", "language": "en"})
    assert response.status_code == 422
    assert response.json()["code"] == "nothing_to_say"
    assert tts.calls == []


def test_speak_daily_character_cap(make_client, fixture_kb: Path) -> None:
    tts = FakeTTS()
    client = make_client(fixture_kb, tts=tts, tts_max_chars_per_day=30)
    assert client.post(SPEAK, json={"text": "A" * 20, "language": "en"}).status_code == 200
    over = client.post(SPEAK, json={"text": "B" * 20, "language": "en"})
    assert over.status_code == 429
    assert over.json()["code"] == "tts_quota"
    assert len(tts.calls) == 1
    # A sentence that still fits the remaining budget is spoken.
    assert client.post(SPEAK, json={"text": "C" * 10, "language": "en"}).status_code == 200


def test_char_budget_resets_daily() -> None:
    now = [1_000_000.0]
    budget = CharBudget(100, clock=lambda: now[0])
    assert budget.try_consume(80)
    assert not budget.try_consume(30)
    budget.exhaust()
    assert budget.remaining == 0
    now[0] += 86_400
    assert budget.remaining == 100


def test_speak_rate_limit(make_client, fixture_kb: Path) -> None:
    client = make_client(fixture_kb, tts=FakeTTS(), tts_rate_per_minute=1)
    assert client.post(SPEAK, json={"text": "One.", "language": "en"}).status_code == 200
    limited = client.post(SPEAK, json={"text": "Two.", "language": "en"})
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"


def test_speak_provider_failure_is_503_and_refunds_budget(make_client, fixture_kb: Path) -> None:
    tts = FakeTTS(error=VoiceUnavailableError("text-to-speech failed (500)"))
    client = make_client(fixture_kb, tts=tts, tts_max_chars_per_day=10)
    response = client.post(SPEAK, json={"text": "Hello", "language": "en"})
    assert response.status_code == 503
    assert response.json()["code"] == "tts_unavailable"
    assert client.app.state.tts_budget.remaining == 10


def test_speak_provider_quota_stops_server_voice_for_the_day(make_client, fixture_kb: Path) -> None:
    tts = FakeTTS(error=VoiceQuotaError("text-to-speech quota (401)"))
    client = make_client(fixture_kb, tts=tts)
    assert client.post(SPEAK, json={"text": "Hello", "language": "en"}).status_code == 503
    second = client.post(SPEAK, json={"text": "Hello", "language": "en"})
    assert second.status_code == 429
    assert second.json()["code"] == "tts_quota"
    assert len(tts.calls) == 1  # the provider is not called again today


def test_speak_failure_mid_stream_ends_audio_early(make_client, fixture_kb: Path) -> None:
    tts = FakeTTS(error=VoiceUnavailableError("connection failed"), error_after_chunks=1)
    response = make_client(fixture_kb, tts=tts).post(
        SPEAK, json={"text": "Hello", "language": "en"}
    )
    assert response.status_code == 200
    assert 0 < len(response.content) < 20 * 417


def test_speak_in_browser_mode_is_unavailable(make_client, fixture_kb: Path) -> None:
    client = make_client(fixture_kb, tts_provider="browser")
    response = client.post(SPEAK, json={"text": "Hello", "language": "en"})
    assert response.status_code == 503
    assert response.json()["code"] == "tts_unavailable"


# --- config ------------------------------------------------------------------------------------


def test_config_reports_providers_without_secrets(make_client, fixture_kb: Path) -> None:
    client = make_client(
        fixture_kb,
        stt_provider="groq",
        llm_base_url="https://api.example.invalid/v1",
        llm_api_key=SECRET,
        tts_provider="elevenlabs",
        elevenlabs_api_key=SECRET + "-tts",
    )
    response = client.get(CONFIG)
    assert response.status_code == 200
    assert response.json() == {
        "stt": {"provider": "groq", "max_seconds": 30, "max_bytes": 2 * 1024 * 1024},
        "tts": {"provider": "elevenlabs", "max_chars": 600},
    }
    assert SECRET not in response.text
    assert "whisper" not in response.text and "iP95" not in response.text


def test_config_missing_tts_key_degrades_to_browser(make_client, fixture_kb: Path) -> None:
    client = make_client(fixture_kb, tts_provider="elevenlabs", elevenlabs_api_key=None)
    assert client.get(CONFIG).json()["tts"]["provider"] == "browser"


# --- adapters ----------------------------------------------------------------------------------


def test_build_vocabulary_is_short_and_from_data() -> None:
    profile = ProfileResponse.model_construct(name="Test Person", name_ar="شخص")
    projects = [
        ProjectSummary.model_construct(title=f"Proj{i}: long subtitle", technologies=["Py", "X"])
        for i in range(60)
    ]
    vocabulary = build_vocabulary(profile, projects)
    assert vocabulary.startswith("Test Person, شخص, Proj0, Proj1")
    assert "long subtitle" not in vocabulary
    assert len(vocabulary) <= 501
    assert build_vocabulary(None, []) == ""


@pytest.mark.anyio
async def test_whisper_adapter_request_and_parsing() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "text": " ما هي مشاريعه؟ ",
                "language": "Arabic",
                "duration": 2.72,
                "segments": [{"no_speech_prob": 0.01}],
            },
        )

    stt = WhisperSTT(
        base_url="https://stt.example/v1/",
        model="whisper-large-v3",
        api_key=SECRET,
        transport=httpx.MockTransport(handler),
    )
    result = await stt.transcribe(
        wav(500), filename="clip.wav", content_type="audio/wav", language="ar", prompt="Nawa."
    )
    await stt.aclose()
    assert result == Transcription("ما هي مشاريعه؟", "ar", 2720, no_speech=False)
    request = seen[0]
    assert str(request.url) == "https://stt.example/v1/audio/transcriptions"
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    body = request.content
    for expected in (b"whisper-large-v3", b"verbose_json", b'name="language"', b"Nawa."):
        assert expected in body


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "error"),
    [(429, VoiceQuotaError), (500, VoiceUnavailableError), (400, VoiceUnavailableError)],
)
async def test_whisper_adapter_errors(status: int, error: type[Exception]) -> None:
    stt = WhisperSTT(
        base_url="https://stt.example/v1",
        model="m",
        api_key=SECRET,
        transport=httpx.MockTransport(lambda _: httpx.Response(status, text=f"oops {SECRET}")),
    )
    with pytest.raises(error) as caught:
        await stt.transcribe(b"x", filename="c.wav", content_type="audio/wav", language=None)
    assert SECRET not in str(caught.value)


@pytest.mark.anyio
async def test_whisper_adapter_flags_silence() -> None:
    payload = {"text": "you", "language": "english", "segments": [{"no_speech_prob": 0.93}]}
    stt = WhisperSTT(
        base_url="https://stt.example/v1",
        model="m",
        api_key=None,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    )
    result = await stt.transcribe(b"x", filename="c.wav", content_type="audio/wav", language=None)
    assert result.no_speech and result.language == "en" and result.duration_ms is None


@pytest.mark.anyio
async def test_elevenlabs_adapter_streams_with_voice_per_language() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"\xff\xfb" + b"\x00" * 100)

    tts = ElevenLabsTTS(
        api_key=SECRET,
        model="eleven_v4_turbo",
        voices={"en": "voice-en", "ar": "voice-ar"},
        transport=httpx.MockTransport(handler),
    )
    audio = b"".join([chunk async for chunk in tts.stream("مرحبا", language="ar")])
    await tts.aclose()
    assert audio.startswith(b"\xff\xfb")
    request = seen[0]
    assert request.url.path == "/v1/text-to-speech/voice-ar/stream"
    assert request.url.params["output_format"] == "mp3_44100_64"
    assert request.headers["xi-api-key"] == SECRET
    assert json.loads(request.content) == {
        "text": "مرحبا",
        "model_id": "eleven_v4_turbo",
        "language_code": "ar",
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (401, {"detail": {"status": "quota_exceeded", "message": "no credits"}}, VoiceQuotaError),
        (429, {"detail": {"status": "too_many_concurrent_requests"}}, VoiceQuotaError),
        (401, {"detail": {"status": "invalid_api_key"}}, VoiceUnavailableError),
        (503, {}, VoiceUnavailableError),
    ],
    ids=["quota", "rate", "bad-key", "down"],
)
async def test_elevenlabs_adapter_errors(status: int, body: dict, error: type[Exception]) -> None:
    tts = ElevenLabsTTS(
        api_key=SECRET,
        model="m",
        voices={"en": "v", "ar": "v"},
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body)),
    )
    with pytest.raises(error) as caught:
        async for _ in tts.stream("Hello", language="en"):
            pass
    assert SECRET not in str(caught.value)
