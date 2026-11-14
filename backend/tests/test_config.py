import pytest

from app.core.config import Settings


def test_cors_origins_parsed_from_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, https://example.com")

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["http://localhost:3000", "https://example.com"]
