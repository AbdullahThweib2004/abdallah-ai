"""Serverless building blocks: index artifact, shared state in (fake) Upstash Redis, proxy IPs.

The fake speaks Upstash's REST protocol (`POST /`, `POST /pipeline`) through httpx's
MockTransport and runs our Lua scripts as Python equivalents. Two clients on one fake = two
serverless instances sharing state.
"""

import base64
import json
from pathlib import Path

import httpx
import pytest

from app.core.redis import UpstashRedis
from app.rag.chunking import chunk_documents
from app.rag.embeddings import FakeEmbedder
from app.rag.index import KnowledgeIndex
from app.services import rate_limit, voice_service
from app.services.answer_cache import CachedReply, RedisAnswerCache
from app.services.rate_limit import RedisRateLimiter
from app.services.voice_service import RedisCharBudget
from tests.conftest import make_settings


class FakeUpstash:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}
        self.fail = False
        self.commands: list[list[str]] = []

    def run(self, cmd: list[str]) -> object:
        self.commands.append(cmd)
        name, args = cmd[0].upper(), cmd[1:]
        data = self.data
        if name == "GET":
            value = data.get(args[0])
            return None if value is None else str(value)
        if name == "SET":
            data[args[0]] = args[1]
            return "OK"
        if name in {"EXPIRE", "PEXPIRE"}:
            return 1
        if name == "HSET":
            data.setdefault(args[0], {})[args[1]] = args[2]  # type: ignore[index]
            return 1
        if name == "HGETALL":
            flat: list[str] = []
            for key, value in dict(data.get(args[0], {})).items():  # type: ignore[arg-type]
                flat += [key, value]
            return flat
        if name == "EVAL":
            script, nkeys = args[0], int(args[1])
            keys, argv = args[2 : 2 + nkeys], args[2 + nkeys :]
            return self.script(script, keys, argv)
        raise AssertionError(f"unexpected command {name}")

    def script(self, script: str, keys: list[str], argv: list[str]) -> object:
        data = self.data
        if script == rate_limit._CHECK_SCRIPT:
            now, per_minute, per_day, global_day, until = (float(a) for a in argv[:5])
            if int(data.get(keys[0], 0)) >= global_day:  # type: ignore[arg-type]
                return [0, "daily_cap", int(until)]
            if int(data.get(keys[1], 0)) >= per_day:  # type: ignore[arg-type]
                return [0, "daily_limit", int(until)]
            recent = [t for t in data.get(keys[2], []) if t > now - 60000]  # type: ignore[union-attr]
            if len(recent) >= per_minute:
                return [0, "rate_limited", int((60000 - (now - min(recent))) / 1000) + 1]
            data[keys[2]] = [*recent, now]
            for key in keys[:2]:
                data[key] = int(data.get(key, 0)) + 1  # type: ignore[arg-type]
            return [1, "", 0]
        if script == voice_service._CONSUME_SCRIPT:
            used = int(data.get(keys[0], 0))  # type: ignore[arg-type]
            if used + int(argv[0]) > int(argv[1]):
                return 0
            data[keys[0]] = used + int(argv[0])
            return 1
        if script == voice_service._REFUND_SCRIPT:
            data[keys[0]] = max(0, int(data.get(keys[0], 0)) - int(argv[0]))  # type: ignore[arg-type]
            return data[keys[0]]
        raise AssertionError("unknown script")

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer token"
        if self.fail:
            return httpx.Response(503)
        body = json.loads(request.content)
        if request.url.path == "/pipeline":
            return httpx.Response(200, json=[{"result": self.run(cmd)} for cmd in body])
        return httpx.Response(200, json={"result": self.run(body)})

    def client(self) -> UpstashRedis:
        return UpstashRedis("https://fake.upstash.io", "token", transport=httpx.MockTransport(self))


# --- index artifact --------------------------------------------------------------------------


class CountingEmbedder(FakeEmbedder):
    def __init__(self) -> None:
        self.passages = 0

    def embed_passages(self, texts):
        self.passages += len(texts)
        return super().embed_passages(texts)


def test_index_artifact_is_built_once_and_loaded_without_embedding(fixture_kb, tmp_path):
    from app.knowledge.loader import load_knowledge_base

    chunks = chunk_documents(load_knowledge_base(fixture_kb))
    builder = CountingEmbedder()
    built = KnowledgeIndex(tmp_path / "idx", builder)
    assert built.ensure(chunks) is True and builder.passages == len(chunks)
    meta = json.loads((tmp_path / "idx" / "index.json").read_text())
    assert meta["ids"] == [c.id for c in chunks] and len(meta["bm25_tokens"]) == len(chunks)

    runtime = CountingEmbedder()  # a cold start: loads the artifact, embeds no chunk
    loaded = KnowledgeIndex(tmp_path / "idx", runtime)
    assert loaded.ensure(chunks) is False and runtime.passages == 0
    query = FakeEmbedder().embed_query(chunks[0].text)
    assert loaded.search(query, 3)[0][0] == chunks[0].id
    assert loaded.bm25_tokens == meta["bm25_tokens"]


def test_stale_index_on_a_read_only_filesystem_is_rebuilt_in_memory(fixture_kb, tmp_path):
    from app.knowledge.loader import load_knowledge_base

    chunks = chunk_documents(load_knowledge_base(fixture_kb))
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    index = KnowledgeIndex(blocker / "idx", FakeEmbedder())  # cannot be created
    assert index.ensure(chunks) is True
    assert index.search(FakeEmbedder().embed_query(chunks[1].text), 1)[0][0] == chunks[1].id


# --- shared rate limits, budget, answer cache --------------------------------------------------


@pytest.mark.anyio
async def test_rate_limits_are_shared_between_instances_and_never_store_raw_ips():
    fake = FakeUpstash()
    options = {"name": "chat", "scope": "production", "per_minute": 2, "per_day": 3,
               "global_per_day": 100}  # fmt: skip
    first, second = (RedisRateLimiter(fake.client(), **options) for _ in range(2))
    assert (await first.check("203.0.113.9")).allowed
    assert (await second.check("203.0.113.9")).allowed
    limited = await first.check("203.0.113.9")  # third request this minute, other instance
    assert not limited.allowed and limited.reason == "rate_limited" and limited.retry_after
    assert (await second.check("198.51.100.1")).allowed  # another visitor
    assert not any("203.0.113.9" in key for key in fake.data)
    assert all(key.startswith("aa:production:rl:chat:") for key in fake.data)


@pytest.mark.anyio
async def test_global_daily_cap_is_shared():
    fake = FakeUpstash()
    options = {"name": "chat", "scope": "production", "per_minute": 10, "per_day": 10,
               "global_per_day": 2}  # fmt: skip
    a, b = (RedisRateLimiter(fake.client(), **options) for _ in range(2))
    assert (await a.check("1.1.1.1")).allowed and (await b.check("2.2.2.2")).allowed
    capped = await a.check("3.3.3.3")
    assert not capped.allowed and capped.reason == "daily_cap"


@pytest.mark.anyio
async def test_preview_and_production_counters_are_separate():
    fake = FakeUpstash()
    options = {"name": "chat", "per_minute": 1, "per_day": 10, "global_per_day": 10}
    prod = RedisRateLimiter(fake.client(), scope="production", **options)
    preview = RedisRateLimiter(fake.client(), scope="preview", **options)
    assert (await preview.check("1.1.1.1")).allowed
    assert (await prod.check("1.1.1.1")).allowed  # the preview's request did not count


@pytest.mark.anyio
async def test_redis_outage_falls_back_to_in_memory_limits(caplog):
    fake = FakeUpstash()
    fake.fail = True
    limiter = RedisRateLimiter(
        fake.client(), name="chat", scope="p", per_minute=1, per_day=5, global_per_day=5
    )
    assert (await limiter.check("1.1.1.1")).allowed
    assert not (await limiter.check("1.1.1.1")).allowed  # still limited, per instance
    assert "in-memory fallback" in caplog.text


@pytest.mark.anyio
async def test_tts_budget_is_shared_between_instances():
    fake = FakeUpstash()
    a, b = (RedisCharBudget(fake.client(), 100, scope="production") for _ in range(2))
    assert await a.try_consume(70)
    assert not await b.try_consume(40)  # 70 already used by the other instance
    await b.refund(30)
    assert await a.try_consume(60)
    await a.exhaust()
    assert not await b.try_consume(1)


@pytest.mark.anyio
async def test_answer_cache_and_audio_are_shared_between_instances():
    fake = FakeUpstash()
    a, b = (RedisAnswerCache(fake.client(), kb_hash="kb", prompt_version="v7") for _ in range(2))
    key = a.key_for("How can I contact him?", "en")
    reply = CachedReply("Email or LinkedIn. Ask away.", [{"type": "show_contact"}], [], "en", "m")
    await a.put(key, reply)
    assert await b.get(key) == reply
    assert await b.speech_cacheable("Email or LinkedIn.", "en")  # loaded from Redis
    await a.put_audio("audio1", b"\x00mp3")
    assert await b.get_audio("audio1") == b"\x00mp3"
    stored = fake.data[f"aa:cache:{a.namespace}:audio:audio1"]
    assert base64.b64decode(stored) == b"\x00mp3"  # type: ignore[arg-type]
    assert "How can I contact him" not in json.dumps(fake.data, default=str)  # hashes only


@pytest.mark.anyio
async def test_answer_cache_redis_outage_is_a_miss():
    fake = FakeUpstash()
    cache = RedisAnswerCache(fake.client(), kb_hash="kb", prompt_version="v7")
    fake.fail = True
    assert await cache.get("missing") is None
    await cache.put("k", CachedReply("Hi.", [], [], "en", "m"))  # logged, not raised
    assert await cache.get("k") is not None  # the in-process copy still serves


# --- app wiring --------------------------------------------------------------------------------


def test_client_ip_comes_from_the_proxy_header_only_behind_a_trusted_proxy(fixture_kb):
    from fastapi.testclient import TestClient

    from app.main import create_app

    seen: list[str] = []

    class Recorder:
        async def check(self, key: str):
            seen.append(key)
            return rate_limit.RateDecision(False, "rate_limited", 5)

    for behind, expected in ((True, "203.0.113.7"), (False, "testclient")):
        settings = make_settings(fixture_kb, trust_proxy_headers=behind)
        with TestClient(create_app(settings, rate_limiter=Recorder())) as client:
            client.post(
                "/api/v1/chat",
                json={"message": "hi"},
                headers={"x-real-ip": "203.0.113.7", "x-forwarded-for": "203.0.113.7, 10.0.0.1"},
            )
        assert seen[-1] == expected


def test_api_docs_are_hidden_in_production(fixture_kb: Path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(make_settings(fixture_kb, app_env="production"))) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
    with TestClient(create_app(make_settings(fixture_kb))) as client:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "default-src 'none'" in response.headers["content-security-policy"]


def test_a_model_that_fails_to_load_lazily_falls_back_to_bm25(fixture_kb, caplog, tmp_path):
    from app.knowledge.loader import load_knowledge_base
    from app.rag.embeddings import LazyEmbedder
    from app.rag.query_expansion import glossary_terms
    from app.rag.retriever import Retriever

    def broken():
        raise RuntimeError("model file missing")

    documents = load_knowledge_base(fixture_kb)
    chunks = chunk_documents(documents)
    index = KnowledgeIndex(tmp_path / "index", FakeEmbedder())
    index.ensure(chunks)
    lazy = LazyEmbedder("broken-model", broken)
    retriever = Retriever(chunks, index=index, embedder=lazy, glossary=glossary_terms(documents))
    result = retriever.retrieve("Alpha problem")
    assert result.chunks  # BM25 still finds it
    assert "Vector search failed" in caplog.text
