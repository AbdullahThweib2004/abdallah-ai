"""Deterministic speech providers for tests and for running the app without any API key."""

from collections.abc import AsyncIterator

from app.voice.base import Alignment, Language, SpeechChunk, Transcription, VoiceError

# Fake timestamps: every character takes this long (tests, local demos).
FAKE_SECONDS_PER_CHAR = 0.06

# One MPEG-1 Layer III frame (128 kb/s, 44.1 kHz, mono) of digital silence: a 4-byte header
# followed by zeroed side info and data, which decoders play as ~26 ms of silence.
_SILENT_FRAME = bytes.fromhex("fffb90c4") + bytes(413)
SILENT_MP3 = _SILENT_FRAME * 20  # ~0.5 s


class FakeSTT:
    name = "fake"
    model = "fake-stt"

    def __init__(
        self,
        *,
        text: str = "What projects has he built?",
        language: str | None = "en",
        duration_ms: int | None = 2000,
        no_speech: bool = False,
        error: VoiceError | None = None,
    ) -> None:
        self._result = Transcription(text, language, duration_ms, no_speech)
        self._error = error
        self.calls: list[dict[str, object]] = []

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language: Language | None,
        prompt: str | None = None,
    ) -> Transcription:
        # Record only metadata, never the audio itself.
        self.calls.append(
            {
                "bytes": len(audio),
                "content_type": content_type,
                "language": language,
                "prompt": prompt,
            }
        )
        if self._error:
            raise self._error
        return self._result

    async def aclose(self) -> None:
        return None


class FakeTTS:
    name = "fake"
    model = "fake-tts"
    media_type = "audio/mpeg"

    def __init__(
        self, *, error: VoiceError | None = None, error_after_chunks: int | None = None
    ) -> None:
        self._error = error
        self._error_after_chunks = error_after_chunks
        self.calls: list[tuple[str, str]] = []

    async def stream(self, text: str, *, language: Language) -> AsyncIterator[bytes]:
        self.calls.append((text, language))
        chunks = [SILENT_MP3[i : i + 2090] for i in range(0, len(SILENT_MP3), 2090)]
        for index, chunk in enumerate(chunks):
            if self._error and (self._error_after_chunks or 0) == index:
                raise self._error
            yield chunk

    async def stream_timed(self, text: str, *, language: Language) -> AsyncIterator[SpeechChunk]:
        """The same audio; the alignment comes in two halves (chunk times are absolute)."""
        step = FAKE_SECONDS_PER_CHAR
        middle = len(text) // 2
        halves = [(0, middle), (middle, len(text))]
        index = -1
        async for chunk in self.stream(text, language=language):
            index += 1
            alignment = None
            if index < len(halves):
                start, end = halves[index]
                alignment = Alignment(
                    list(text[start:end]),
                    [i * step for i in range(start, end)],
                    [(i + 1) * step for i in range(start, end)],
                )
            yield SpeechChunk(chunk, alignment)

    async def aclose(self) -> None:
        return None
