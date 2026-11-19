"""Application settings loaded from environment variables / `.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Look for `.env` in backend/ first, then the repo root.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_FILES = (_BACKEND_DIR.parent / ".env", _BACKEND_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, extra="ignore", populate_by_name=True)

    app_env: Literal["development", "staging", "production", "test"] = "development"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    knowledge_base_dir: Path = Path("../knowledge_base")

    # --- LLM (see app/llm). The default `fake` provider needs no key. ---
    llm_provider: Literal["fake", "openai_compatible", "anthropic"] = "fake"
    # Delay between fake tokens, to demo/test streaming and Stop without a real model.
    llm_fake_delay_ms: int = Field(default=0, ge=0, le=2000)
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_fallback_model: str | None = None
    # Sent only when set (gpt-oss / o-series); leave empty for models without reasoning.
    llm_reasoning_effort: Literal["low", "medium", "high"] | None = "low"
    # Optional override for Arabic replies; falls back to llm_reasoning_effort.
    llm_reasoning_effort_ar: Literal["low", "medium", "high"] | None = None
    llm_max_output_tokens: int = Field(default=500, ge=1, le=8000)
    llm_temperature: float = Field(default=0.3, ge=0, le=2)
    llm_timeout_seconds: float = Field(default=30, gt=0)
    # Limit-aware routing: a model is skipped before sending when its remaining tokens per
    # minute (from the provider's rate-limit headers) do not cover the prompt + this headroom.
    llm_route_headroom_tokens: int = Field(default=300, ge=0)
    # USD per million tokens, only used for cost estimates in logs and evals.
    llm_input_cost_per_mtok: float = Field(default=0, ge=0)
    llm_output_cost_per_mtok: float = Field(default=0, ge=0)

    # --- Retrieval (RAG, see app/rag) ---
    # `onnx`: a small multilingual ONNX model run locally (see app/rag/embeddings.py).
    rag_embedder: Literal["onnx", "fake"] = "onnx"
    rag_embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    rag_models_dir: Path = Path(".models")
    # The precomputed index artifact (vectors + BM25 tokens + hash), built by `app.rag.cli
    # build` (the Vercel build hook) and rebuilt automatically when the knowledge changed.
    rag_index_dir: Path = Path(".index")
    # Budget kept small (cost, latency, and Groq's free tier); evals/run_retrieval reports
    # the recall of what the chat really sends at these settings (1.0 at 6 / 1000; top_k 4
    # loses e.g. Nawa's results for "How well does Nawa perform?").
    rag_top_k: int = Field(default=6, ge=1, le=20)
    rag_max_context_tokens: int = Field(default=1000, ge=100)
    # Minimum cosine similarity for a vector hit to count (BM25 hits are kept regardless).
    # Model-specific: for MiniLM-L12, 0.25 keeps Recall@6 = 1.0 with a margin (0.35 already
    # loses cases; see evals.run_retrieval --min-score). Re-tune when changing models.
    rag_min_score: float = Field(default=0.25, ge=0, le=1)

    # --- Answer cache (first-turn questions; see app/services/answer_cache.py) ---
    answer_cache_enabled: bool = True
    # Persisted across restarts (empty = memory only). Relative to backend/.
    answer_cache_dir: Path | None = Path(".cache/answers")
    answer_cache_max_entries: int = Field(default=500, ge=1)
    # Answer the home page's suggestion chips (EN + AR) in the background at startup.
    answer_cache_prewarm: bool = True
    # Wait before pre-warming, so `uvicorn --reload` restarts cancel it before any provider call.
    answer_cache_prewarm_delay_seconds: float = Field(default=30, ge=0)
    # Pause between replayed pieces of a cached answer, so it still types in.
    answer_cache_stream_delay_ms: int = Field(default=15, ge=0, le=500)

    # --- Shared state (rate limits, daily caps, TTS budget, answer cache) ---
    # Upstash Redis over its REST API. Empty = in-memory (one process: local dev and tests).
    # Accepts the names the Vercel Marketplace integration sets.
    redis_rest_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "REDIS_REST_URL", "UPSTASH_REDIS_REST_URL", "KV_REST_API_URL"
        ),
    )
    redis_rest_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "REDIS_REST_TOKEN", "UPSTASH_REDIS_REST_TOKEN", "KV_REST_API_TOKEN"
        ),
    )
    # Vercel sets VERCEL=1 and VERCEL_ENV (production / preview / development) at runtime.
    vercel: bool = False
    vercel_env: str | None = None
    # Read the client IP from X-Forwarded-For / X-Real-IP (only behind a trusted proxy;
    # always on when running on Vercel, which overwrites these headers).
    trust_proxy_headers: bool = False

    # --- Chat abuse and cost protection ---
    chat_rate_per_minute: int = Field(default=8, ge=1)
    chat_rate_per_day: int = Field(default=60, ge=1)
    chat_max_requests_per_day: int = Field(default=500, ge=1)

    # --- Voice (see app/voice). Defaults need no key: fake STT, the browser's own voice. ---
    # STT reuses LLM_BASE_URL and LLM_API_KEY (Groq's OpenAI-compatible /audio/transcriptions).
    stt_provider: Literal["fake", "groq"] = "fake"
    stt_model: str = "whisper-large-v3"
    stt_timeout_seconds: float = Field(default=20, gt=0)
    # `browser` = speechSynthesis in the visitor's browser (free; no backend audio at all).
    tts_provider: Literal["fake", "browser", "elevenlabs"] = "browser"
    tts_model: str = "eleven_v4_turbo"
    # ElevenLabs stock voice ids (not secrets). Default: "Chris", a male premade voice with
    # Arabic listed among its ElevenLabs-verified languages; one multilingual voice for both.
    tts_voice_en: str = "iP95p4xoKVk53GoZ742B"
    tts_voice_ar: str = "iP95p4xoKVk53GoZ742B"
    tts_timeout_seconds: float = Field(default=15, gt=0)
    elevenlabs_api_key: SecretStr | None = None
    # Per IP. Each spoken sentence is one /voice/speak call, hence the higher TTS limit.
    voice_rate_per_minute: int = Field(default=6, ge=1)
    tts_rate_per_minute: int = Field(default=40, ge=1)
    # Global daily budget of synthesized characters (UTC day), protecting the free tier.
    tts_max_chars_per_day: int = Field(default=20_000, ge=0)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        # Accept a comma-separated string, e.g. "http://localhost:3000,https://example.com".
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator(
        "llm_base_url",
        "llm_api_key",
        "llm_model",
        "llm_fallback_model",
        "llm_reasoning_effort",
        "llm_reasoning_effort_ar",
        "elevenlabs_api_key",
        "answer_cache_dir",
        "redis_rest_url",
        "redis_rest_token",
        "vercel_env",
        mode="before",
    )
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        # `LLM_REASONING_EFFORT=` (empty) in .env means "do not send the parameter".
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator(
        "knowledge_base_dir", "rag_models_dir", "rag_index_dir", "answer_cache_dir", mode="after"
    )
    @classmethod
    def _resolve_knowledge_base_dir(cls, value: Path | None) -> Path | None:
        # Relative paths are resolved against backend/, independent of the working directory.
        if value is None:
            return None
        return value if value.is_absolute() else (_BACKEND_DIR / value).resolve()

    @model_validator(mode="after")
    def _bundled_knowledge_base(self) -> "Settings":
        # Serverless bundles contain only backend/: the build step (app.deploy) copies the
        # knowledge base to backend/knowledge_base. Use it when the repo copy is absent.
        bundled = _BACKEND_DIR / "knowledge_base"
        if not self.knowledge_base_dir.is_dir() and bundled.is_dir():
            self.knowledge_base_dir = bundled
        return self

    @property
    def behind_proxy(self) -> bool:
        return self.trust_proxy_headers or self.vercel

    @property
    def state_scope(self) -> str:
        """Prefix that keeps rate counters of preview deployments apart from production."""
        return self.vercel_env or self.app_env


@lru_cache
def get_settings() -> Settings:
    return Settings()
