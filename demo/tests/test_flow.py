from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from demo.config import Settings
from demo.main import create_app


class StubLimiter:
    def __init__(self, status: int = 200, body: dict | None = None) -> None:
        self._status = status
        self._body = body or {"allowed": True, "limit": 10, "remaining": 9, "reset_at": 0}

    async def check(self, *, rule_key: str, user_id: str | None) -> tuple[int, dict]:
        return self._status, self._body

    async def aclose(self) -> None:
        pass


@pytest.fixture
def client(tmp_path) -> TestClient:
    app = create_app(Settings(db_path=str(tmp_path / "links.db")))
    app.state.limiter = StubLimiter()  # type: ignore[assignment]
    with TestClient(app) as c:
        yield c


def test_shorten_returns_short_url(client: TestClient) -> None:
    r = client.post("/shorten", json={"url": "https://example.com/page", "user_id": "demo"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["short_code"]) == 6
    assert body["short_url"] == f"http://localhost:8080/{body['short_code']}"
    assert body["hits"] == 0


def test_redirect_records_a_hit(client: TestClient) -> None:
    created = client.post(
        "/shorten", json={"url": "https://example.com/page", "user_id": "demo"}
    ).json()
    code = created["short_code"]
    assert client.get(f"/{code}", follow_redirects=False).status_code == 301
    assert client.get(f"/{code}", follow_redirects=False).status_code == 301
    recent = client.get("/recent").json()["links"]
    assert recent[0]["code"] == code
    assert recent[0]["hits"] == 2


def test_unknown_code_404(client: TestClient) -> None:
    assert client.get("/zzzzzz", follow_redirects=False).status_code == 404


def test_shorten_throttled_passthrough(client: TestClient) -> None:
    client.app.state.limiter = StubLimiter(429, {"retry_after_s": 3})  # type: ignore[assignment]
    r = client.post("/shorten", json={"url": "https://example.com/page", "user_id": "demo"})
    assert r.status_code == 429
    assert r.headers["Retry-After"] == "3"
    assert r.json()["error"] == "rate_limited"


def test_recent_empty(client: TestClient) -> None:
    assert client.get("/recent").json() == {"links": []}


def test_static_index_served(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Spam" in r.text
