from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError

from limiter.main import create_app
from limiter.storage import TokenBucketStore


class BrokenStore(TokenBucketStore):
    async def check(self, *args, **kwargs):  # type: ignore[override]
        raise ConnectionError("redis down")

    async def ping(self) -> bool:
        return False


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    real: TokenBucketStore = app.state.store
    app.state.store = BrokenStore("redis://localhost:6379")
    with TestClient(app) as c:
        yield c
    asyncio.run(real.aclose())


def test_check_fails_open_when_redis_down(client: TestClient) -> None:
    r = client.post("/v1/check", json={"rule_key": "write_free", "user_id": "x"})
    assert r.status_code == 200
    assert r.json()["allowed"] is True
    assert r.headers["X-RateLimit-Mode"] == "degraded"


def test_health_reports_degraded(client: TestClient) -> None:
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["mode"] == "degraded"
