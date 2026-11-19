import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.prompt import PROMPT_VERSION
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.redis import UpstashRedis
from app.core.security import SecurityHeadersMiddleware
from app.core.version import VERSION
from app.llm.base import LLMConfigError, LLMProvider
from app.llm.factory import build_provider
from app.rag.chunking import chunk_documents
from app.rag.identity import build_identity_context
from app.rag.index import content_hash
from app.rag.service import build_retriever
from app.services.answer_cache import AnswerCache, RedisAnswerCache
from app.services.knowledge_service import load_knowledge_service
from app.services.prewarm import prewarm
from app.services.rate_limit import InMemoryRateLimiter, RateLimiter, RedisRateLimiter
from app.services.voice_service import CharBudget, RedisCharBudget, build_vocabulary
from app.voice.base import STTProvider, TTSProvider, VoiceConfigError
from app.voice.factory import build_stt, build_tts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# APP_ENV=development: per-IP limits are this many times higher (local testing, evals).
DEV_LIMIT_FACTOR = 5


def build_redis(settings: Settings) -> UpstashRedis | None:
    if settings.redis_rest_url and settings.redis_rest_token:
        return UpstashRedis(settings.redis_rest_url, settings.redis_rest_token.get_secret_value())
    if settings.vercel:
        logger.warning("No Redis configured on Vercel: limits and caches are per instance")
    return None


def build_answer_cache(settings: Settings, knowledge, redis: UpstashRedis | None) -> AnswerCache:
    kb_hash = content_hash(chunk_documents(knowledge.documents), "answers")
    if redis is not None:
        return RedisAnswerCache(
            redis,
            kb_hash=kb_hash,
            prompt_version=PROMPT_VERSION,
            max_entries=settings.answer_cache_max_entries,
        )
    return AnswerCache(
        kb_hash=kb_hash,
        prompt_version=PROMPT_VERSION,
        directory=settings.answer_cache_dir,
        max_entries=settings.answer_cache_max_entries,
    )


def create_app(
    settings: Settings | None = None,
    *,
    llm_provider: LLMProvider | None = None,
    rate_limiter: RateLimiter | None = None,
    stt_provider: STTProvider | None = None,
    tts_provider: TTSProvider | None = None,
) -> FastAPI:
    """App factory. Tests may inject providers (LLM, STT, TTS) and a rate limiter."""
    settings = settings or get_settings()
    # Shared state for serverless instances (rate limits, budgets, answer cache).
    redis = build_redis(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        started = time.perf_counter()
        # Loaded once; None means the content endpoints answer 503 while the API stays up.
        knowledge = load_knowledge_service(settings.knowledge_base_dir)
        knowledge_s = time.perf_counter() - started
        app.state.knowledge = knowledge
        # The vector index is rebuilt only when the approved knowledge (or model) changed.
        app.state.retriever = build_retriever(knowledge.documents, settings) if knowledge else None
        retriever_s = time.perf_counter() - started - knowledge_s
        # Without the project list since prompt v6: the action catalog already names every
        # approved project (and says it is the complete list).
        app.state.identity = (
            build_identity_context(knowledge.profile, knowledge.contact()) if knowledge else ""
        )
        # (id, title) of approved projects: the prompt's action catalog and the allowlist.
        app.state.projects = (
            [(project.id, project.title) for project in knowledge.list_projects()]
            if knowledge
            else []
        )

        owned_provider = None
        if llm_provider is None:
            try:
                owned_provider = build_provider(settings)
            except LLMConfigError as exc:
                logger.error("LLM disabled: %s", exc)
        app.state.llm = llm_provider or owned_provider
        if app.state.llm:
            logger.info("LLM provider=%s model=%s", app.state.llm.name, app.state.llm.model)

        # Voice: a misconfigured provider disables voice input (text keeps working) or falls
        # back to the browser's own voice for output.
        owned_voice: list[STTProvider | TTSProvider] = []
        app.state.stt = stt_provider
        if stt_provider is None:
            try:
                app.state.stt = build_stt(settings)
                owned_voice.append(app.state.stt)
            except VoiceConfigError as exc:
                logger.error("Voice input disabled: %s", exc)
        app.state.tts = tts_provider
        if tts_provider is None:
            try:
                app.state.tts = build_tts(settings)
                if app.state.tts:
                    owned_voice.append(app.state.tts)
            except VoiceConfigError as exc:
                logger.error("Server voice disabled, using the browser voice: %s", exc)
        app.state.stt_vocabulary = (
            build_vocabulary(knowledge.profile, knowledge.list_projects()) if knowledge else ""
        )
        for name, provider in (("STT", app.state.stt), ("TTS", app.state.tts)):
            if provider:
                logger.info("%s provider=%s model=%s", name, provider.name, provider.model)

        # Answer cache: keyed by the approved knowledge (hash) and the prompt version. Shared
        # through Redis when configured (serverless), else in memory (+ disk when configured).
        app.state.answer_cache = None
        if settings.answer_cache_enabled and knowledge:
            app.state.answer_cache = build_answer_cache(settings, knowledge, redis)
        prewarm_task: asyncio.Task | None = None
        if (
            settings.answer_cache_prewarm
            and not settings.vercel  # serverless: the build pre-warms (app.services.prewarm)
            and app.state.answer_cache is not None
            and app.state.llm is not None
            and app.state.retriever is not None
        ):
            prewarm_task = asyncio.create_task(
                prewarm(
                    provider=app.state.llm,
                    retriever=app.state.retriever,
                    identity=app.state.identity,
                    settings=settings,
                    projects=app.state.projects,
                    cache=app.state.answer_cache,
                    delay_seconds=settings.answer_cache_prewarm_delay_seconds,
                )
            )
        logger.info(
            "Startup %.2fs (knowledge %.2fs, index %.2fs; embedder loads in the background)",
            time.perf_counter() - started,
            knowledge_s,
            retriever_s,
        )
        yield
        if prewarm_task and not prewarm_task.done():
            prewarm_task.cancel()
            with suppress(asyncio.CancelledError):
                await prewarm_task
        if owned_provider:
            await owned_provider.aclose()
        for provider in owned_voice:
            await provider.aclose()
        if redis is not None:
            await redis.aclose()

    # Interactive API docs only outside production (no need to publish the schema).
    public_docs = settings.app_env != "production"
    app = FastAPI(
        title="Abdallah AI API",
        version=VERSION,
        lifespan=lifespan,
        docs_url="/docs" if public_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if public_docs else None,
    )
    app.state.settings = settings
    app.state.knowledge = None
    app.state.retriever = None
    app.state.identity = ""
    app.state.projects = []
    app.state.llm = None
    app.state.stt = None
    app.state.tts = None
    app.state.stt_vocabulary = ""
    app.state.answer_cache = None
    # Per-IP limits only (the global daily caps stay): 5x higher in development.
    factor = DEV_LIMIT_FACTOR if settings.app_env == "development" else 1

    def limiter(name: str, per_minute: int, per_day: int, global_per_day: int) -> RateLimiter:
        if redis is not None:
            return RedisRateLimiter(
                redis, name=name, scope=settings.state_scope, per_minute=per_minute,
                per_day=per_day, global_per_day=global_per_day,
            )  # fmt: skip
        return InMemoryRateLimiter(
            per_minute=per_minute, per_day=per_day, global_per_day=global_per_day
        )

    app.state.rate_limiter = rate_limiter or limiter(
        "chat",
        settings.chat_rate_per_minute * factor,
        settings.chat_rate_per_day * factor,
        settings.chat_max_requests_per_day,
    )
    # Every voice question also becomes a chat turn, so it shares the chat's daily limits.
    app.state.voice_rate_limiter = limiter(
        "voice",
        settings.voice_rate_per_minute * factor,
        settings.chat_rate_per_day * factor,
        settings.chat_max_requests_per_day,
    )
    # One call per spoken sentence; the character budget is the real cost guard.
    app.state.tts_rate_limiter = limiter(
        "tts",
        settings.tts_rate_per_minute * factor,
        settings.chat_rate_per_day * 10 * factor,
        settings.chat_max_requests_per_day * 10,
    )
    app.state.tts_budget = (
        RedisCharBudget(redis, settings.tts_max_chars_per_day, scope=settings.state_scope)
        if redis is not None
        else CharBudget(settings.tts_max_chars_per_day)
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(api_router)
    return app


app = create_app()
