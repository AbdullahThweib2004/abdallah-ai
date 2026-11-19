"""Answer cache (first-turn replies + their TTS audio), pre-warm, dev limits, 429 logging."""

import json
import logging
import re
import time
from pathlib import Path

import pytest

from app.llm.base import LLMChunk, LLMRateLimitError, Usage
from app.main import create_app
from app.models.chat import ChatRequest
from app.rag.service import build_retriever
from app.services.answer_cache import AnswerCache, CachedReply, cache_key, normalize_question
from app.services.answer_quality import answer_problems
from app.services.knowledge_service import load_knowledge_service
from app.services.prewarm import SUGGESTIONS, prewarm, suggestion_requests
from app.voice.fake import FakeTTS
from tests.conftest import make_settings

FRONTEND_I18N = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "i18n"
ANSWER = 'ACTIONS: [{"type": "show_projects"}]\nHe built three projects. Ask me about any of them.'


class CountingProvider:
    """Streams a fixed answer; can fail the first calls with given errors."""

    name = "counting"
    model = "counting-model"

    def __init__(
        self,
        answer: str = ANSWER,
        failures: list[Exception] | None = None,
        answered_by: str | None = None,  # e.g. the fallback model
    ) -> None:
        self.answer = answer
        self.failures = list(failures or [])
        self.answered_by = answered_by or self.model
        self.calls = 0

    async def stream(self, messages, *, max_tokens, temperature, reasoning_effort=None):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        for part in re.findall(r"\S+\s*", self.answer):
            yield LLMChunk(text=part)
        yield LLMChunk(usage=Usage(1500, 40), model=self.answered_by)

    async def aclose(self) -> None:
        pass


def events(text: str) -> list[tuple[str, dict]]:
    parsed = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        parsed.append((lines["event"], json.loads(lines["data"])))
    return parsed


def answer_of(parsed: list[tuple[str, dict]]) -> str:
    return "".join(data["text"] for name, data in parsed if name == "token")


# --- cache key --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("What's his strongest project?", "whats his strongest project"),
        ("How can I contact him?", "  HOW can i contact him ? "),
        ("حدّثني عن تدريبه في بنك فلسطين", "حدثني عن تدريبه في بنك فلسطين؟"),
        ("ما أقوى مشاريعه؟", "ما اقوى مشاريعه"),
        ("ماذا يعرف عن RAG و MCP؟", "ماذا يعرف عن rag و mcp"),
    ],
)
def test_cache_key_ignores_case_punctuation_and_arabic_marks(a: str, b: str) -> None:
    assert normalize_question(a) == normalize_question(b)
    assert cache_key(a, "en", "kb1", "v6") == cache_key(b, "en", "kb1", "v6")


def test_cache_key_changes_with_question_language_knowledge_and_prompt() -> None:
    base = cache_key("How can I contact him?", "en", "kb1", "v6")
    assert cache_key("How can I hire him?", "en", "kb1", "v6") != base
    assert cache_key("How can I contact him?", "ar", "kb1", "v6") != base
    assert cache_key("How can I contact him?", "en", "kb2", "v6") != base
    assert cache_key("How can I contact him?", "en", "kb1", "v7") != base


def reply(text: str = "He built three projects.", language: str = "en") -> CachedReply:
    return CachedReply(text=text, actions=[], sources=[], language=language, model="m")


@pytest.mark.anyio
async def test_cache_is_lru_bounded() -> None:
    cache = AnswerCache(kb_hash="kb", prompt_version="v6", max_entries=2)
    for key in ("a", "b", "c"):
        await cache.put(key, reply())
    assert await cache.get("a") is None and await cache.get("c") is not None and len(cache) == 2


@pytest.mark.anyio
async def test_cache_persists_per_namespace_and_prunes_only_its_stale_folders(tmp_path: Path):
    (tmp_path / "unrelated").mkdir()
    old = AnswerCache(kb_hash="kb-old", prompt_version="v5", directory=tmp_path)
    await old.put("k1", reply())
    cache = AnswerCache(kb_hash="kb", prompt_version="v6", directory=tmp_path)
    await cache.put("k2", reply("Saved."))
    await cache.put_audio("a1", b"mp3")

    reloaded = AnswerCache(kb_hash="kb", prompt_version="v6", directory=tmp_path)
    assert await reloaded.get("k2") == await cache.get("k2")
    assert await reloaded.get("k1") is None  # another knowledge/prompt version
    assert await reloaded.get_audio("a1") == b"mp3"
    assert (tmp_path / "unrelated").is_dir()  # never touches folders it did not create
    assert len([p for p in tmp_path.iterdir() if p.name != "unrelated"]) == 1  # noqa: ASYNC240


@pytest.mark.anyio
async def test_only_sentences_of_cached_answers_are_speech_cacheable() -> None:
    cache = AnswerCache(kb_hash="kb", prompt_version="v6")
    await cache.put("k", reply("استخدم React و FastAPI في المشروع. وهو مكتمل.", "ar"))
    # The frontend may insert a space between Arabic and Latin letters before speaking.
    assert await cache.speech_cacheable("استخدم React و FastAPI في المشروع.", "ar")
    assert await cache.speech_cacheable("وهو مكتمل.", "ar")
    assert not await cache.speech_cacheable("وهو مكتمل.", "en")
    assert not await cache.speech_cacheable("Something else entirely.", "ar")


# --- chat API ---------------------------------------------------------------------------------


def test_first_turn_answer_is_cached_and_replayed_as_a_normal_stream(make_client, fixture_kb):
    provider = CountingProvider()
    client = make_client(fixture_kb, provider=provider, answer_cache_enabled=True)
    first = events(client.post("/api/v1/chat", json={"message": "What has he built?"}).text)
    again = events(client.post("/api/v1/chat", json={"message": "what has he BUILT"}).text)

    assert provider.calls == 1
    assert [n for n, _ in again][:2] == ["start", "action"] and again[-1][0] == "done"
    assert (
        answer_of(again) == answer_of(first) == "He built three projects. Ask me about any of them."
    )
    assert again[1][1] == first[1][1] == {"actions": [{"type": "show_projects"}]}
    assert again[-1][1]["sources"] == first[-1][1]["sources"]
    assert again[-1][1]["cached"] is True and "cached" not in first[-1][1]
    assert sum(1 for n, _ in again if n == "token") > 1  # still types in, piece by piece


def test_follow_ups_and_failed_answers_are_never_cached(make_client, fixture_kb):
    provider = CountingProvider(failures=[LLMRateLimitError("429", 5)])
    client = make_client(fixture_kb, provider=provider, answer_cache_enabled=True)
    busy = events(client.post("/api/v1/chat", json={"message": "What has he built?"}).text)
    assert busy[-1] == ("error", busy[-1][1]) and busy[-1][1]["retry_after"] == 5
    history = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"}]
    for _ in range(2):
        client.post("/api/v1/chat", json={"message": "What has he built?", "history": history})
    assert provider.calls == 3  # busy + two follow-ups: nothing came from the cache


def test_cached_answers_cost_no_tts_characters_the_second_time(make_client, fixture_kb):
    tts = FakeTTS()
    client = make_client(
        fixture_kb, provider=CountingProvider(), tts=tts, answer_cache_enabled=True
    )
    client.post("/api/v1/chat", json={"message": "What has he built?"})
    budget = client.app.state.tts_budget
    before = budget.remaining
    sentence = {"text": "He built three projects.", "language": "en"}
    first = client.post("/api/v1/voice/speak", json=sentence)
    after_first = budget.remaining
    second = client.post("/api/v1/voice/speak", json=sentence)
    assert first.status_code == second.status_code == 200
    assert second.content == first.content
    assert len(tts.calls) == 1  # the second one came from the audio cache
    assert before > after_first == budget.remaining
    # Text that is not part of a cached answer is never stored.
    client.post("/api/v1/voice/speak", json={"text": "A different sentence.", "language": "en"})
    client.post("/api/v1/voice/speak", json={"text": "A different sentence.", "language": "en"})
    assert len(tts.calls) == 3


@pytest.mark.parametrize(
    ("provider", "why"),
    [
        (CountingProvider(answered_by="fallback-model"), "fallback model"),
        (CountingProvider(answer="ACTIONS: []\nHis work is truly impressive."), "praise"),
        (CountingProvider(answer="ACTIONS: []\nAbdullah's projects are listed here."), "name"),
    ],
    ids=["fallback-model", "praise", "misspelt-name"],
)
def test_answers_from_the_fallback_or_breaking_a_rule_are_not_cached(
    make_client, fixture_kb, provider, why
):
    client = make_client(fixture_kb, provider=provider, answer_cache_enabled=True)
    for _ in range(2):
        client.post("/api/v1/chat", json={"message": "What has he built?"})
    assert provider.calls == 2, why
    assert len(client.app.state.answer_cache) == 0


def test_rule_checks_allow_his_email_and_github_username() -> None:
    assert (
        answer_problems("Email him at abdullahthweib111@gmail.com or see AbdullahThweib2004.") == []
    )
    assert answer_problems("Abdullah built it.") == ["misspelt name 'Abdullah'"]


# --- pre-warm ---------------------------------------------------------------------------------


def test_suggestions_match_the_frontend_chips() -> None:
    for language in ("en", "ar"):
        source = (FRONTEND_I18N / f"{language}.ts").read_text(encoding="utf-8")
        block = re.search(r"suggestions: \[(.*?)\]", source, re.S)
        assert block, language
        assert re.findall(r'"([^"]+)"', block.group(1)) == SUGGESTIONS[language]


@pytest.fixture
def pipeline(fixture_kb):
    settings = make_settings(fixture_kb, answer_cache_stream_delay_ms=0)
    knowledge = load_knowledge_service(fixture_kb)
    return {
        "retriever": build_retriever(knowledge.documents, settings),
        "identity": "",
        "settings": settings,
        "projects": [(p.id, p.title) for p in knowledge.list_projects()],
        "cache": AnswerCache(kb_hash="kb", prompt_version="v6"),
    }


@pytest.mark.anyio
async def test_prewarm_answers_every_chip_once_sequentially_and_waits_on_limits(pipeline):
    provider = CountingProvider(failures=[LLMRateLimitError("429", 3.0)])
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    report = await prewarm(provider=provider, sleep=sleep, **pipeline)
    assert len(suggestion_requests()) == 8
    assert (report.cached, report.already, report.failed) == (8, 0, 0)
    assert provider.calls == 9  # one retry after the 429
    assert 3.0 in slept  # waited Retry-After before retrying
    assert slept.count(2.0) == 7  # a pause between questions

    # Every chip is now answered from the cache, in both languages, without the provider.
    for request in suggestion_requests():
        language = "ar" if request.ui_language == "ar" else "en"
        assert await pipeline["cache"].get(pipeline["cache"].key_for(request.message, language))
    again = await prewarm(provider=provider, sleep=sleep, **pipeline)
    assert (again.cached, again.already) == (0, 8) and provider.calls == 9


@pytest.mark.anyio
async def test_prewarm_gives_up_on_a_question_after_repeated_limits(pipeline):
    provider = CountingProvider(failures=[LLMRateLimitError("429", 500)] * 4)

    async def sleep(seconds: float) -> None:
        assert seconds <= 120  # waits are capped

    report = await prewarm(
        provider=provider,
        sleep=sleep,
        requests=[ChatRequest(message="How can I contact him?")],
        **pipeline,
    )
    assert (report.cached, report.failed) == (0, 1)


def test_prewarm_runs_in_the_background_at_startup(make_client, fixture_kb):
    provider = CountingProvider()
    client = make_client(
        fixture_kb,
        provider=provider,
        answer_cache_enabled=True,
        answer_cache_prewarm=True,
        answer_cache_prewarm_delay_seconds=0,
        answer_cache_stream_delay_ms=0,
    )
    deadline = time.monotonic() + 5
    while provider.calls == 0 and time.monotonic() < deadline:
        time.sleep(0.05)  # the TestClient runs the app's event loop in another thread
    assert provider.calls >= 1
    assert len(client.app.state.answer_cache) >= 1


@pytest.mark.anyio
async def test_prewarm_waits_its_start_delay_first(pipeline):
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    await prewarm(
        provider=CountingProvider(),
        sleep=sleep,
        delay_seconds=30,
        requests=[ChatRequest(message="How can I contact him?")],
        **pipeline,
    )
    assert slept[0] == 30


# --- dev limits and logs ------------------------------------------------------------------------


@pytest.mark.parametrize(("app_env", "per_minute"), [("development", 40), ("production", 8)])
def test_per_ip_limits_are_five_times_higher_in_development(fixture_kb, app_env, per_minute):
    settings = make_settings(fixture_kb, app_env=app_env, chat_rate_per_minute=8)
    app = create_app(settings)
    limiter = app.state.rate_limiter
    allowed = sum(limiter.check_now("1.2.3.4").allowed for _ in range(per_minute + 1))
    assert allowed == per_minute
    assert app.state.voice_rate_limiter._per_minute == settings.voice_rate_per_minute * (
        5 if app_env == "development" else 1
    )
    assert limiter._global_per_day == settings.chat_max_requests_per_day  # global cap unchanged


def test_our_own_429s_are_logged_with_source_and_limit(make_client, fixture_kb, caplog):
    client = make_client(fixture_kb, chat_rate_per_minute=1)
    with caplog.at_level(logging.WARNING):
        client.post("/api/v1/chat", json={"message": "secret question text"})
        limited = client.post("/api/v1/chat", json={"message": "secret question text"})
    assert limited.status_code == 429
    assert "rate_limit source=app limit=per_ip_minute route=chat retry_after=" in caplog.text
    assert "secret question text" not in caplog.text
