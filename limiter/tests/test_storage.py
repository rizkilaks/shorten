from __future__ import annotations

import pytest

from limiter.storage import TokenBucketStore


@pytest.fixture
async def store() -> TokenBucketStore:
    s = TokenBucketStore("redis://localhost:6379")
    await s.flush()
    yield s
    await s.aclose()


async def test_first_request_is_allowed_and_costs_one(store: TokenBucketStore) -> None:
    r = await store.check("t:first", capacity=10, rate=1.0, ttl=60, now_ms=0)
    assert r.allowed is True
    assert r.remaining == 9


async def test_refill_over_time(store: TokenBucketStore) -> None:
    await store.check("t:refill", capacity=10, rate=1.0, ttl=60, now_ms=0)
    r = await store.check("t:refill", capacity=10, rate=1.0, ttl=60, now_ms=3000)
    assert r.allowed is True
    assert r.remaining == 9


async def test_tokens_capped_at_capacity(store: TokenBucketStore) -> None:
    await store.check("t:cap", capacity=10, rate=1.0, ttl=60, now_ms=0)
    r = await store.check("t:cap", capacity=10, rate=1.0, ttl=60, now_ms=1_000_000)
    assert r.remaining == 9


async def test_exhaustion_denies_and_reports_time_to_next(store: TokenBucketStore) -> None:
    for _ in range(10):
        assert (await store.check("t:exh", capacity=10, rate=1.0, ttl=60, now_ms=0)).allowed
    denied = await store.check("t:exh", capacity=10, rate=1.0, ttl=60, now_ms=0)
    assert denied.allowed is False
    assert denied.remaining == 0
    assert denied.time_to_next == pytest.approx(1.0)


async def test_cost_above_one(store: TokenBucketStore) -> None:
    r = await store.check("t:cost", capacity=5, rate=1.0, ttl=60, now_ms=0, cost=3)
    assert r.allowed is True
    assert r.remaining == 2


async def test_key_expires_and_restarts_full(store: TokenBucketStore) -> None:
    await store.check("t:ttl", capacity=2, rate=1.0, ttl=60, now_ms=0)
    await store._client.expire("t:ttl", 0)
    r = await store.check("t:ttl", capacity=2, rate=1.0, ttl=60, now_ms=10_000)
    assert r.allowed is True
    assert r.remaining == 1


async def test_ttl_is_set(store: TokenBucketStore) -> None:
    await store.check("t:ttl2", capacity=10, rate=1.0, ttl=60, now_ms=0)
    ttl = await store._client.ttl("t:ttl2")
    assert 0 < ttl <= 60
