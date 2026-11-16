from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient


def test_health_returns_ok_with_knowledge_base_status(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    # 11 approved fixture documents; the draft project is not counted.
    assert response.json() == {
        "status": "ok",
        "version": "0.1.0",
        "knowledge_base": "ok",
        "approved_documents": 11,
    }


def test_health_stays_ok_when_knowledge_base_fails(
    make_client: Callable[[Path], TestClient], tmp_path: Path
) -> None:
    client = make_client(tmp_path / "missing")

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["knowledge_base"] == "error"
    assert response.json()["approved_documents"] == 0


def test_health_allows_configured_cors_origin(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_health_rejects_unknown_cors_origin(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers
