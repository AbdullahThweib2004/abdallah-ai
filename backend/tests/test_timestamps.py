"""Character timestamps for word highlighting: provider parsing, /voice/speak NDJSON, cache."""

import base64
import json

import anyio
import httpx
import pytest

from app.voice.elevenlabs import ElevenLabsTTS
from app.voice.fake import FAKE_SECONDS_PER_CHAR, FakeTTS

SPEAK = "/api/v1/voice/speak"


def chunk(audio: bytes, chars: str, starts: list[float], ends: list[float]) -> dict:
    return {
        "audio_base64": base64.b64encode(audio).decode(),
        "alignment": {
            "characters": list(chars),
            "character_start_times_seconds": starts,
            "character_end_times_seconds": ends,
        },
    }


def provider(body: bytes) -> ElevenLabsTTS:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/stream/with-timestamps")
        return httpx.Response(200, content=body)

    return ElevenLabsTTS(
        api_key="key", model="m", voices={"en": "v", "ar": "v"},
        transport=httpx.MockTransport(handler),
    )  # fmt: skip


async def collect(tts: ElevenLabsTTS, text: str = "Hi yo"):
    return [item async for item in tts.stream_timed(text, language="en")]


@pytest.mark.anyio
@pytest.mark.parametrize("separator", [b"\n", b"", b"\n\n"])
async def test_elevenlabs_chunks_are_parsed_newline_delimited_or_back_to_back(separator):
    parts = [
        chunk(b"A", "Hi", [0.0, 0.1], [0.1, 0.2]),
        chunk(b"B", " yo", [0.2, 0.3, 0.4], [0.3, 0.4, 0.5]),
    ]
    items = await collect(provider(separator.join(json.dumps(p).encode() for p in parts)))
    assert b"".join(i.audio for i in items) == b"AB"
    assert [c for i in items for c in i.alignment.chars] == list("Hi yo")
    assert items[1].alignment.starts == [0.2, 0.3, 0.4]  # absolute times stay as they are


@pytest.mark.anyio
async def test_chunk_relative_times_are_made_absolute():
    parts = [
        chunk(b"A", "Hi", [0.0, 0.1], [0.1, 0.2]),
        chunk(b"B", " yo", [0.0, 0.1, 0.2], [0.1, 0.2, 0.3]),
    ]
    items = await collect(provider(b"\n".join(json.dumps(p).encode() for p in parts)))
    assert items[1].alignment.starts == pytest.approx([0.2, 0.3, 0.4])
    assert items[1].alignment.ends[-1] == pytest.approx(0.5)


@pytest.mark.anyio
async def test_a_json_object_split_across_network_reads_is_reassembled():
    raw = json.dumps(chunk(b"A", "Hi", [0.0, 0.1], [0.1, 0.2])).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(raw))  # parsed incrementally below

    tts = ElevenLabsTTS(api_key="k", model="m", voices={"en": "v", "ar": "v"},
                        transport=httpx.MockTransport(handler))  # fmt: skip
    items = await collect(tts, "Hi")
    assert items[0].alignment.chars == ["H", "i"]


def lines(response) -> list[dict]:
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_speak_with_timestamps_streams_audio_and_alignment(make_client, fixture_kb):
    client = make_client(fixture_kb, tts=FakeTTS())
    response = client.post(
        SPEAK, json={"text": "Hello there.", "language": "en", "timestamps": True}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    items = lines(response)
    audio = b"".join(base64.b64decode(i["audio"]) for i in items if "audio" in i)
    chars = [c for i in items if "alignment" in i for c in i["alignment"]["chars"]]
    assert audio and "".join(chars) == "Hello there."
    ends = [t for i in items if "alignment" in i for t in i["alignment"]["ends"]]
    assert ends[-1] == pytest.approx(len("Hello there.") * FAKE_SECONDS_PER_CHAR)


def test_speak_without_timestamps_is_still_plain_mp3(make_client, fixture_kb):
    client = make_client(fixture_kb, tts=FakeTTS())
    response = client.post(SPEAK, json={"text": "Hello there.", "language": "en"})
    assert response.headers["content-type"] == "audio/mpeg"
    assert not response.content.startswith(b"{")


def test_cached_sentence_audio_keeps_its_timestamps(make_client, fixture_kb):
    from app.services.answer_cache import CachedReply

    tts = FakeTTS()
    client = make_client(fixture_kb, tts=tts, answer_cache_enabled=True)
    cache = client.app.state.answer_cache
    anyio.run(cache.put, "k", CachedReply("Hello there. Bye.", [], [], "en", "m"))
    body = {"text": "Hello there.", "language": "en", "timestamps": True}
    first = lines(client.post(SPEAK, json=body))
    calls = len(tts.calls)
    second = lines(client.post(SPEAK, json=body))
    assert len(tts.calls) == calls  # served from the cache, no provider call

    def chars(items):
        return "".join(c for i in items if "alignment" in i for c in i["alignment"]["chars"])

    assert chars(second) == chars(first) == "Hello there."
