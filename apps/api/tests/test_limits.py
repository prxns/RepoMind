from fastapi.testclient import TestClient
from threading import BoundedSemaphore
import uuid

from repomind.api import app
from repomind.limits import PostRateLimiter


def test_post_limit_is_shared_across_paths_and_host_headers(monkeypatch):
    monkeypatch.setattr("repomind.api.rate_limiter", PostRateLimiter(2, 10))
    client = TestClient(app)
    url = "/api/v1/repositories/ingest"
    assert client.post(url, json={}, headers={"Host": "audit.local"}).status_code == 422
    assert client.post(url, json={}, headers={"Host": "audit.local/other?"}).status_code == 422
    limited = client.post(url, json={}, headers={"Host": "audit.local/another?"})
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert limited.headers["X-Request-ID"]


def test_post_limit_bounds_clients_and_expires_idle_windows():
    limiter = PostRateLimiter(per_client=2, global_limit=3, max_clients=2)
    assert limiter.allow("first", now=0)
    assert limiter.allow("second", now=0)
    assert not limiter.allow("third", now=0)
    assert limiter.allow("first", now=1)
    assert not limiter.allow("first", now=1)
    assert not limiter.allow("second", now=1)
    assert limiter.allow("third", now=61)
    assert list(limiter.clients) == ["third"]


def test_query_capacity_rejects_new_work_before_database_access(monkeypatch):
    slots = BoundedSemaphore(1)
    assert slots.acquire(blocking=False)
    monkeypatch.setattr("repomind.api.query_slots", slots)
    response = TestClient(app).post(f"/api/v1/repositories/{uuid.uuid4()}/query",
                                    json={"question": "Where is the API?"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "QUERY_CAPACITY"
