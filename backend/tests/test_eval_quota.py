"""Quota-safe eval runner: model choice, case selection, early stop (no network)."""

import json

import pytest

from app.llm.base import LLMChunk, LLMRateLimitError, Usage
from app.llm.rate_limits import RateLimitTracker
from evals.quota import QuotaGuard, QuotaStop, eval_settings, select_cases
from evals.run_chat import Context, ask_with_backoff
from tests.conftest import make_settings

CASES = [
    {"id": "a-en", "language": "en"},
    {"id": "b-ar", "language": "ar"},
    {"id": "c-en", "language": "en"},
    {"id": "d-ar", "language": "ar"},
]


def test_default_model_is_the_fallback_and_the_fallback_is_off(fixture_kb) -> None:
    settings = make_settings(fixture_kb).model_copy(
        update={"llm_model": "big-120b", "llm_fallback_model": "small-20b"}
    )
    chosen = eval_settings(settings, None)
    assert chosen.llm_model == "small-20b" and chosen.llm_fallback_model is None
    explicit = eval_settings(settings, "big-120b")
    assert explicit.llm_model == "big-120b" and explicit.llm_fallback_model is None


def test_select_cases_by_ids_language_and_limit() -> None:
    assert [c["id"] for c in select_cases(CASES, only=["d-ar,a-en"])] == ["a-en", "d-ar"]
    assert [c["id"] for c in select_cases(CASES, only=["a-en", "c-en"])] == ["a-en", "c-en"]
    assert [c["id"] for c in select_cases(CASES, lang="ar")] == ["b-ar", "d-ar"]
    assert [c["id"] for c in select_cases(CASES, limit=3)] == ["a-en", "b-ar", "c-en"]
    with pytest.raises(SystemExit, match="Unknown case id"):
        select_cases(CASES, only=["nope"])


def test_daily_limit_stops_instead_of_waiting() -> None:
    with pytest.raises(QuotaStop, match="daily quota reached"):
        QuotaGuard().wait_for(LLMRateLimitError("429", 747, "TPD"), "120b")
    with pytest.raises(QuotaStop, match="daily quota"):
        QuotaGuard().wait_for(LLMRateLimitError("429", 3, "RPD"), "20b")


def test_short_per_minute_limit_waits_and_long_one_stops() -> None:
    guard = QuotaGuard(max_wait=90)
    assert guard.wait_for(LLMRateLimitError("429", 8, "TPM"), "20b") == 8
    with pytest.raises(QuotaStop, match="--max-wait"):
        guard.wait_for(LLMRateLimitError("429", 300, "TPM"), "20b")


class Provider:
    name = "fake"
    model = "20b"

    def __init__(self, errors: list[LLMRateLimitError], remaining: int = 900) -> None:
        self.errors = errors
        self.calls = 0
        self.tracker = RateLimitTracker()
        self.tracker.observe("20b", {"x-ratelimit-remaining-requests": str(remaining)})

    async def stream(self, messages, *, max_tokens, temperature, reasoning_effort=None):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        yield LLMChunk(text="ACTIONS: []\nok", usage=Usage(10, 2))

    async def aclose(self) -> None:
        pass


def test_low_remaining_requests_stop_the_run() -> None:
    QuotaGuard(reserve_requests=150).check_remaining(Provider([], remaining=900))
    with pytest.raises(QuotaStop, match="only 120 requests left"):
        QuotaGuard(reserve_requests=150).check_remaining(Provider([], remaining=120))


@pytest.fixture
def context(fixture_kb):
    from app.rag.service import build_retriever
    from app.services.knowledge_service import load_knowledge_service

    knowledge = load_knowledge_service(fixture_kb)
    return Context(build_retriever(knowledge.documents, make_settings(fixture_kb)), "")


@pytest.mark.anyio
async def test_backoff_waits_on_tpm_then_answers(fixture_kb, context, monkeypatch) -> None:
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("evals.run_chat.asyncio.sleep", sleep)
    provider = Provider([LLMRateLimitError("429", 4, "TPM")])
    reply = await ask_with_backoff(
        provider, context, {"id": "x", "message": "hi"}, make_settings(fixture_kb)
    )
    assert reply.error is None and reply.raw.endswith("ok")
    assert waits == [4] and provider.calls == 2


@pytest.mark.anyio
async def test_backoff_stops_on_a_daily_limit_without_waiting(fixture_kb, context) -> None:
    provider = Provider([LLMRateLimitError("429", 800, "TPD")])
    with pytest.raises(QuotaStop):
        await ask_with_backoff(
            provider, context, {"id": "x", "message": "hi"}, make_settings(fixture_kb)
        )
    assert provider.calls == 1


@pytest.mark.anyio
async def test_api_target_rebuilds_the_reply_from_the_sse_stream_and_maps_429() -> None:
    import httpx

    from evals.api_target import ApiTarget

    stream = (
        'event: start\ndata: {"request_id": "r"}\n\n'
        'event: action\ndata: {"actions": [{"type": "show_contact"}]}\n\n'
        'event: token\ndata: {"text": "Email or "}\n\n'
        'event: token\ndata: {"text": "LinkedIn."}\n\n'
        'event: done\ndata: {"usage": {"input_tokens": 0, "output_tokens": 0}, "cached": true}\n\n'
    )
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        if len(calls) == 2:
            return httpx.Response(429, headers={"retry-after": "7"}, json={"code": "rate_limited"})
        return httpx.Response(200, text=stream, headers={"content-type": "text/event-stream"})

    target = ApiTarget("https://site.example/", transport=httpx.MockTransport(handler))
    raw, _ = await target.ask({"message": "How can I contact him?", "language": "en"})
    assert raw == 'ACTIONS: [{"type": "show_contact"}]\nEmail or LinkedIn.'
    assert target.cached == 1 and calls[0]["ui_language"] == "en"
    with pytest.raises(LLMRateLimitError) as limited:
        await target.ask({"message": "again"})
    assert limited.value.retry_after == 7
    await target.aclose()
