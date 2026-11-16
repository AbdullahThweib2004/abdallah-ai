"""LLM adapters against a fake HTTP transport (no network)."""

import json
import logging
from collections.abc import Callable

import httpx
import pytest

from app.llm.anthropic import AnthropicProvider
from app.llm.base import LLMChunk, LLMError, LLMUnavailableError
from app.llm.openai_compatible import OpenAICompatibleProvider

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


MESSAGES = [{"role": "system", "content": "rules"}, {"role": "user", "content": "hi"}]


def sse_body(*payloads: dict | str) -> bytes:
    lines = [f"data: {p if isinstance(p, str) else json.dumps(p)}\n\n" for p in payloads]
    return "".join(lines).encode()


def delta(**fields: str) -> dict:
    return {"choices": [{"index": 0, "delta": fields}]}


class Recorder:
    """Mock transport handler that records request bodies and answers per model."""

    def __init__(self, answers: dict[str, Callable[[httpx.Request], httpx.Response]]) -> None:
        self.answers = answers
        self.bodies: list[dict] = []
        self.headers: list[httpx.Headers] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        self.headers.append(request.headers)
        return self.answers[body["model"]](request)


def provider(recorder: Recorder, **kwargs) -> OpenAICompatibleProvider:
    options = {"base_url": "https://llm.test/v1", "model": "main", "api_key": "sk-test-SECRET"}
    options.update(kwargs)
    return OpenAICompatibleProvider(transport=httpx.MockTransport(recorder), **options)


async def collect(p) -> tuple[str, list[LLMChunk]]:
    chunks = [chunk async for chunk in p.stream(MESSAGES, max_tokens=100, temperature=0.3)]
    return "".join(c.text for c in chunks), chunks


def ok_stream(*parts: str) -> Callable[[httpx.Request], httpx.Response]:
    body = sse_body(
        *(delta(content=part) for part in parts),
        {"choices": [], "x_groq": {"usage": {"prompt_tokens": 11, "completion_tokens": 7}}},
        "[DONE]",
    )
    return lambda request: httpx.Response(200, content=body)


async def test_reasoning_fields_in_the_stream_are_discarded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    body = sse_body(
        delta(role="assistant", reasoning="SECRET-THOUGHT-1"),
        delta(reasoning_content="SECRET-THOUGHT-2"),
        delta(thinking="SECRET-THOUGHT-3", content="Hello"),
        delta(content=" world"),
        "[DONE]",
    )
    recorder = Recorder({"main": lambda r: httpx.Response(200, content=body)})

    text, chunks = await collect(provider(recorder))

    assert text == "Hello world"
    assert "SECRET-THOUGHT" not in "".join(repr(c) for c in chunks)
    assert "SECRET-THOUGHT" not in caplog.text


async def test_usage_is_read_from_groq_x_groq_field() -> None:
    recorder = Recorder({"main": ok_stream("Hi")})

    _, chunks = await collect(provider(recorder))

    assert chunks[-1].usage is not None
    assert (chunks[-1].usage.input_tokens, chunks[-1].usage.output_tokens) == (11, 7)
    assert chunks[-1].model == "main"


async def test_reasoning_effort_is_sent_only_when_configured() -> None:
    with_effort = Recorder({"main": ok_stream("a")})
    without = Recorder({"main": ok_stream("a")})

    await collect(provider(with_effort, reasoning_effort="low"))
    await collect(provider(without, reasoning_effort=None))

    assert with_effort.bodies[0]["reasoning_effort"] == "low"
    assert "reasoning_effort" not in without.bodies[0]
    assert with_effort.headers[0]["authorization"] == "Bearer sk-test-SECRET"


@pytest.mark.parametrize(
    "failure",
    [
        lambda r: httpx.Response(429, headers={"retry-after": "2"}),
        lambda r: httpx.Response(503),
        lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=r)),
    ],
    ids=["429", "503", "timeout"],
)
async def test_falls_back_once_when_main_model_fails_before_first_token(failure) -> None:
    recorder = Recorder({"main": failure, "backup": ok_stream("From", " backup")})

    text, chunks = await collect(provider(recorder, fallback_model="backup"))

    assert text == "From backup"
    assert [body["model"] for body in recorder.bodies] == ["main", "backup"]
    assert chunks[-1].model == "backup"


async def test_never_switches_model_mid_answer() -> None:
    body = sse_body(delta(content="Partial"), {"error": {"message": "overloaded"}})
    recorder = Recorder(
        {"main": lambda r: httpx.Response(200, content=body), "backup": ok_stream("x")}
    )
    received: list[str] = []

    with pytest.raises(LLMUnavailableError):
        async for chunk in provider(recorder, fallback_model="backup").stream(
            MESSAGES, max_tokens=100, temperature=0.3
        ):
            received.append(chunk.text)

    assert received == ["Partial"]
    assert [body["model"] for body in recorder.bodies] == ["main"]


async def test_client_errors_are_not_retried_with_fallback() -> None:
    recorder = Recorder(
        {"main": lambda r: httpx.Response(401, json={"error": "bad key sk-test-SECRET"})}
    )

    with pytest.raises(LLMError) as raised:
        await collect(provider(recorder, fallback_model="backup"))

    assert len(recorder.bodies) == 1
    assert "sk-test-SECRET" not in str(raised.value)


async def test_anthropic_streams_text_only_and_reports_usage() -> None:
    events = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 20}}},
        {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "SECRET"}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hi"}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": " there"}},
        {"type": "message_delta", "usage": {"output_tokens": 5}},
        {"type": "message_stop"},
    ]
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=sse_body(*events))

    anthropic = AnthropicProvider(
        api_key="k", model="claude-test", transport=httpx.MockTransport(handler)
    )
    text, chunks = await collect(anthropic)

    assert text == "Hi there"
    assert chunks[-1].usage is not None and chunks[-1].usage.output_tokens == 5
    assert seen[0]["system"] == "rules"
    assert all(message["role"] != "system" for message in seen[0]["messages"])
