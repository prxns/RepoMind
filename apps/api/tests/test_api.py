from fastapi.testclient import TestClient

from repomind.api import app


def test_liveness_does_not_require_database():
    response = TestClient(app).get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_invalid_repository_url_fails_before_github_access():
    response = TestClient(app).post("/api/v1/repositories/ingest", json={"url": "https://evil.example/a/b"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_INPUT"
