from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_health_allows_configured_cors_origin(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_health_rejects_unknown_cors_origin(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers
