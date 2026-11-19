"""Limit-aware routing: Groq rate-limit headers → per-model budget → route before sending."""

import json
import logging

import httpx
import pytest

from app.core.limits import groq_limit_type, parse_duration
from app.llm.base import LLMChunk, LLMRateLimitError, Usage
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.llm.rate_limits import RateLimitTracker
from app.models.chat import ChatRequest
from app.services.chat_service import chat_events
from tests.conftest import make_settings

MESSAGES = [{"role": "system", "content": "rules " * 100}, {"role": "user", "content": "hi"}]


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def headers(remaining_tokens: int, *, limit: int = 8000, reset: str = "7.5s", requests: int = 900):
    return {
        "x-ratelimit-limit-tokens": str(limit),
        "x-ratelimit-remaining-tokens": str(remaining_tokens),
        "x-ratelimit-reset-tokens": reset,
        "x-ratelimit-limit-requests": "1000",
        "x-ratelimit-remaining-requests": str(requests),
        "x-ratelimit-reset-requests": "2h38m24s",
    }


# --- parsing --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("547ms", 0.547), ("7.66s", 7.66), ("2m59.56s", 179.56), ("2h38m24s", 9504.0), ("12", 12.0)],
)
def test_parse_duration(value: str, seconds: float) -> None:
    assert parse_duration(value) == pytest.approx(seconds)


@pytest.mark.parametrize("value", [None, "", "soon", "5x"])
def test_parse_duration_rejects_garbage(value: str | None) -> None:
    assert parse_duration(value) is None


def test_groq_limit_type_is_read_from_the_429_message() -> None:
    body = json.dumps(
        {
            "error": {
                "message": "Rate limit reached for model `openai/gpt-oss-120b` in organization "
                "`org_secret` on tokens per minute (TPM): Limit 8000, Used 7000, Requested 2500.",
                "code": "rate_limit_exceeded",
            }
        }
    )
    assert groq_limit_type(body.encode()) == "TPM"
    assert groq_limit_type(b'{"error": {"message": "... requests per day (RPD) ..."}}') == "RPD"
    assert groq_limit_type(b"not json") == "unknown"


# --- routing decision -----------------------------------------------------------------------


def test_unknown_budget_is_available_and_keeps_the_preference_order() -> None:
    decision = RateLimitTracker().route(["120b", "20b"], needed_tokens=2000)
    assert decision.models == ["120b", "20b"] and decision.skipped == []


def test_model_near_its_tpm_limit_is_skipped_before_sending() -> None:
    clock = Clock()
    tracker = RateLimitTracker(clock)
    tracker.observe("120b", headers(1500))  # 1,500 tokens left this minute
    decision = tracker.route(["120b", "20b"], needed_tokens=2000)
    assert decision.models == ["20b"]
    assert decision.skipped[0].model == "120b" and decision.skipped[0].reason == "TPM"
    # 6,500 missing tokens refill in 7.5 s: 500 more tokens take ~0.58 s.
    assert decision.skipped[0].wait_seconds == pytest.approx(500 / (6500 / 7.5), rel=1e-3)


def test_tokens_refill_linearly_until_the_reset() -> None:
    clock = Clock()
    tracker = RateLimitTracker(clock)
    tracker.observe("120b", headers(1500))
    clock.now += 1.0  # +867 tokens
    assert tracker.check("120b", 2000) is None
    clock.now += 60
    assert tracker.budget("120b").tokens.projected(clock.now) == 8000


def test_generated_tokens_are_subtracted_after_the_answer() -> None:
    clock = Clock()
    tracker = RateLimitTracker(clock)
    tracker.observe("120b", headers(2600, reset="60s"))
    assert tracker.check("120b", 2000) is None
    tracker.spend("120b", 700)  # the answer + reasoning
    assert tracker.check("120b", 2000) is not None


def test_no_requests_left_today_skips_the_model() -> None:
    tracker = RateLimitTracker(Clock())
    tracker.observe("120b", headers(8000, requests=0))
    skip = tracker.check("120b", 100)
    assert skip is not None and skip.reason == "RPD"


def test_a_429_blocks_the_model_for_retry_after() -> None:
    clock = Clock()
    tracker = RateLimitTracker(clock)
    tracker.block("120b", 12)
    assert tracker.check("120b", 1).reason == "429"
    clock.now += 12.1
    assert tracker.check("120b", 1) is None


def test_all_models_over_their_limits_reports_the_shortest_wait() -> None:
    clock = Clock()
    tracker = RateLimitTracker(clock)
    tracker.block("120b", 30)
    tracker.block("20b", 9)
    decision = tracker.route(["120b", "20b"], needed_tokens=10)
    assert decision.models == []
    assert decision.wait_seconds == pytest.approx(9)


# --- provider integration -------------------------------------------------------------------


def stream_body() -> bytes:
    payloads = [
        {"choices": [{"index": 0, "delta": {"content": "ok"}}]},
        {"choices": [], "x_groq": {"usage": {"prompt_tokens": 600, "completion_tokens": 50}}},
    ]
    return ("".join(f"data: {json.dumps(p)}\n\n" for p in payloads) + "data: [DONE]\n\n").encode()


class Groq:
    """Mock transport: answers per model with given rate-limit headers (or a 429)."""

    def __init__(self, replies: dict[str, list[httpx.Response]]) -> None:
        self.replies = replies
        self.models: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        self.models.append(model)
        return self.replies[model].pop(0)


def provider(groq: Groq, clock: Clock) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url="https://api.groq.com/openai/v1",
        model="120b",
        fallback_model="20b",
        api_key="sk-test",
        tracker=RateLimitTracker(clock),
        transport=httpx.MockTransport(groq),
    )


async def run(p: OpenAICompatibleProvider) -> list[LLMChunk]:
    return [chunk async for chunk in p.stream(MESSAGES, max_tokens=100, temperature=0.3)]


@pytest.mark.anyio
async def test_provider_routes_to_the_fallback_before_sending_when_main_is_near_its_limit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = Clock()
    groq = Groq(
        {
            "120b": [httpx.Response(200, content=stream_body(), headers=headers(300))],
            "20b": [httpx.Response(200, content=stream_body(), headers=headers(7000))],
        }
    )
    p = provider(groq, clock)
    await run(p)  # 120b answers, but only 300 tokens remain this minute
    with caplog.at_level(logging.INFO):
        chunks = await run(p)
    assert groq.models == ["120b", "20b"]  # the second request never went to 120b
    assert chunks[-1].model == "20b"
    assert "120b is near its TPM limit" in caplog.text
    await p.aclose()


@pytest.mark.anyio
async def test_a_429_is_logged_with_source_and_limit_and_blocks_the_model(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = Clock()
    body = b'{"error": {"message": "Rate limit ... in organization `org_x` on tokens per minute (TPM): Limit 8000"}}'  # noqa: E501
    groq = Groq(
        {
            "120b": [httpx.Response(429, content=body, headers={"retry-after": "8"})],
            "20b": [
                httpx.Response(200, content=stream_body(), headers=headers(7000)),
                httpx.Response(200, content=stream_body(), headers=headers(7000)),
            ],
        }
    )
    p = provider(groq, clock)
    with caplog.at_level(logging.INFO):
        await run(p)
        await run(p)
    assert groq.models == ["120b", "20b", "20b"]  # 120b blocked for 8 s after its 429
    assert "rate_limit source=groq model=120b limit=TPM retry_after=8" in caplog.text
    assert "org_x" not in caplog.text  # the provider's message is never logged
    await p.aclose()


@pytest.mark.anyio
async def test_all_models_limited_answers_busy_without_sending(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = Clock()
    groq = Groq({})
    p = provider(groq, clock)
    p.tracker.block("120b", 30)
    p.tracker.block("20b", 6.2)
    with caplog.at_level(logging.INFO), pytest.raises(LLMRateLimitError) as raised:
        await run(p)
    assert groq.models == []
    assert raised.value.retry_after == 7  # rounded up
    assert "rate_limit source=router model=120b limit=429" in caplog.text
    await p.aclose()


class LimitedProvider:
    name = "limited"
    model = "limited-model"

    async def stream(self, messages, *, max_tokens, temperature, reasoning_effort=None):
        raise LLMRateLimitError("provider rate limit (429)", 7.2, "TPM")
        yield LLMChunk(usage=Usage())  # pragma: no cover - makes this an async generator

    async def aclose(self) -> None:
        pass


@pytest.mark.anyio
async def test_busy_error_event_carries_retry_after(fixture_kb) -> None:
    from app.rag.service import build_retriever
    from app.services.knowledge_service import load_knowledge_service

    settings = make_settings(fixture_kb)
    knowledge = load_knowledge_service(fixture_kb)
    retriever = build_retriever(knowledge.documents, settings)
    events = [
        event
        async for event in chat_events(
            "r1",
            ChatRequest(message="hello"),
            provider=LimitedProvider(),
            retriever=retriever,
            identity="",
            settings=settings,
        )
    ]
    error = json.loads(events[-1].split("data: ", 1)[1])
    assert events[-1].startswith("event: error")
    assert error["code"] == "busy" and error["retry_after"] == 8


@pytest.mark.anyio
async def test_primary_only_view_never_uses_the_fallback() -> None:
    clock = Clock()
    groq = Groq({"120b": [httpx.Response(429, content=b"{}", headers={"retry-after": "4"})]})
    p = provider(groq, clock)
    with pytest.raises(LLMRateLimitError):
        await run(p.primary_only())
    assert groq.models == ["120b"]  # no fallback request
    assert p.tracker.check("120b", 1) is not None  # shares the tracker: 120b is now blocked
    await p.aclose()
