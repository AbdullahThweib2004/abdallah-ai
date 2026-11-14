import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    settings = Settings(app_env="test", cors_origins=["http://localhost:3000"])
    return TestClient(create_app(settings))
