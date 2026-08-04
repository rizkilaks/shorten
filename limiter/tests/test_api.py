from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from limiter.main import create_app
from limiter.rules import RULES


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as c:
        c.portal.call(app.state.store.flush)
        yield c
        c.portal.call(app.state.store.aclose)


def test_every_rule_has_positive_bounds() -> None:
    assert RULES["write_free"].capacity == 10
    assert RULES["write_free"].refill_rate == pytest.approx(20 / 60)
    assert RULES["read_free"].capacity == 100
    assert RULES["read_free"].refill_rate == pytest.approx(300 / 60)
    assert RULES["ip_write"].capacity == 30
    assert RULES["ip_write"].refill_rate == pytest.approx(60 / 60)
    for rule in RULES.values():
        assert rule.ttl_seconds > 0


def test_health_ok(client: TestClient) -> None:
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "mode": "normal"}


def test_check_allowed(client: TestClient) -> None:
    r = client.post("/v1/check", json={"rule_key": "write_free", "user_id": "alice"})
    assert r.status_code == 200
    assert r.json()["allowed"] is True
    assert r.json()["remaining"] == 9
    assert r.headers["X-RateLimit-Limit"] == "10"
    assert r.headers["X-RateLimit-Remaining"] == "9"
    assert "X-RateLimit-Reset" in r.headers


def test_check_429_when_exhausted(client: TestClient) -> None:
    for _ in range(10):
        resp = client.post("/v1/check", json={"rule_key": "write_free", "user_id": "bob"})
        assert resp.status_code == 200
    r = client.post("/v1/check", json={"rule_key": "write_free", "user_id": "bob"})
    assert r.status_code == 429
    assert r.json()["error"] == "rate_limited"
    assert r.json()["remaining"] == 0
    assert int(r.headers["Retry-After"]) >= 1
    assert r.headers["X-RateLimit-Remaining"] == "0"


def test_check_unknown_rule(client: TestClient) -> None:
    r = client.post("/v1/check", json={"rule_key": "nope", "user_id": "x"})
    assert r.status_code == 400


def test_check_zero_cost_rejected(client: TestClient) -> None:
    r = client.post("/v1/check", json={"rule_key": "write_free", "user_id": "x", "cost": 0})
    assert r.status_code == 422


def test_check_cost_over_capacity_rejected(client: TestClient) -> None:
    r = client.post("/v1/check", json={"rule_key": "write_free", "user_id": "x", "cost": 20})
    assert r.status_code == 422


def test_ip_fallback_when_no_user_id(client: TestClient) -> None:
    r = client.post("/v1/check", json={"rule_key": "ip_write"})
    assert r.status_code == 200
    assert r.json()["allowed"] is True


def test_user_id_is_sanitized(client: TestClient) -> None:
    r = client.post("/v1/check", json={"rule_key": "write_free", "user_id": "alice <script>"})
    assert r.status_code == 200
    assert r.json()["remaining"] == 9
