"""Application settings loaded from environment variables / `.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Look for `.env` in backend/ first, then the repo root.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_FILES = (_BACKEND_DIR.parent / ".env", _BACKEND_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, extra="ignore")

    app_env: Literal["development", "staging", "production", "test"] = "development"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    knowledge_base_dir: Path = Path("../knowledge_base")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        # Accept a comma-separated string, e.g. "http://localhost:3000,https://example.com".
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("knowledge_base_dir", mode="after")
    @classmethod
    def _resolve_knowledge_base_dir(cls, value: Path) -> Path:
        # Relative paths are resolved against backend/, independent of the working directory.
        return value if value.is_absolute() else (_BACKEND_DIR / value).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
