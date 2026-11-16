import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.version import VERSION
from app.llm.base import LLMConfigError, LLMProvider
from app.llm.factory import build_provider
from app.rag.identity import build_identity_context
from app.rag.service import build_retriever
from app.services.knowledge_service import load_knowledge_service
from app.services.rate_limit import InMemoryRateLimiter, RateLimiter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    llm_provider: LLMProvider | None = None,
    rate_limiter: RateLimiter | None = None,
) -> FastAPI:
    """App factory. Tests may inject an LLM provider and a rate limiter."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Loaded once; None means the content endpoints answer 503 while the API stays up.
        knowledge = load_knowledge_service(settings.knowledge_base_dir)
        app.state.knowledge = knowledge
        # The vector index is rebuilt only when the approved knowledge (or model) changed.
        app.state.retriever = build_retriever(knowledge.documents, settings) if knowledge else None
        app.state.identity = (
            build_identity_context(
                knowledge.profile, knowledge.contact(), knowledge.list_projects()
            )
            if knowledge
            else ""
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
        yield
        if owned_provider:
            await owned_provider.aclose()

    app = FastAPI(title="Abdallah AI API", version=VERSION, lifespan=lifespan)
    app.state.settings = settings
    app.state.knowledge = None
    app.state.retriever = None
    app.state.identity = ""
    app.state.llm = None
    app.state.rate_limiter = rate_limiter or InMemoryRateLimiter(
        per_minute=settings.chat_rate_per_minute,
        per_day=settings.chat_rate_per_day,
        global_per_day=settings.chat_max_requests_per_day,
    )
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
