"""Application settings loaded from environment variables / `.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Look for `.env` in backend/ first, then the repo root.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_FILES = (_BACKEND_DIR.parent / ".env", _BACKEND_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, extra="ignore")

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
    # TEMPORARY until step 5 (RAG): `compact` sends a shorter KNOWLEDGE section so a request
    # fits small tokens-per-minute limits (Groq free tier: 8K TPM).
    llm_knowledge_mode: Literal["full", "compact"] = "full"
    # Sent only when set (gpt-oss / o-series); leave empty for models without reasoning.
    llm_reasoning_effort: Literal["low", "medium", "high"] | None = "low"
    llm_max_output_tokens: int = Field(default=500, ge=1, le=8000)
    llm_temperature: float = Field(default=0.3, ge=0, le=2)
    llm_timeout_seconds: float = Field(default=30, gt=0)
    # USD per million tokens, only used for cost estimates in logs and evals.
    llm_input_cost_per_mtok: float = Field(default=0, ge=0)
    llm_output_cost_per_mtok: float = Field(default=0, ge=0)

    # --- Chat abuse and cost protection ---
    chat_rate_per_minute: int = Field(default=8, ge=1)
    chat_rate_per_day: int = Field(default=60, ge=1)
    chat_max_requests_per_day: int = Field(default=500, ge=1)

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
        mode="before",
    )
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        # `LLM_REASONING_EFFORT=` (empty) in .env means "do not send the parameter".
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("knowledge_base_dir", mode="after")
    @classmethod
    def _resolve_knowledge_base_dir(cls, value: Path) -> Path:
        # Relative paths are resolved against backend/, independent of the working directory.
        return value if value.is_absolute() else (_BACKEND_DIR / value).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
