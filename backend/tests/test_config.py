from pathlib import Path

import pytest

from app.core.config import Settings


def test_cors_origins_parsed_from_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, https://example.com")

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["http://localhost:3000", "https://example.com"]


def test_knowledge_base_dir_defaults_to_repo_knowledge_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KNOWLEDGE_BASE_DIR", raising=False)

    settings = Settings(_env_file=None)

    assert settings.knowledge_base_dir == Path(__file__).resolve().parents[2] / "knowledge_base"
