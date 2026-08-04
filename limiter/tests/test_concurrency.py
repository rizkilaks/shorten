from __future__ import annotations

import asyncio

import pytest

from limiter.storage import TokenBucketStore


@pytest.fixture
async def store() -> TokenBucketStore:
    s = TokenBucketStore("redis://localhost:6379")
    await s.flush()
    yield s
    await s.aclose()


async def test_100_parallel_requests_allow_exactly_capacity(store: TokenBucketStore) -> None:
    results = await asyncio.gather(
        *[store.check("t:burst", capacity=5, rate=100.0, ttl=60, now_ms=0) for _ in range(100)]
    )
    allowed = sum(1 for r in results if r.allowed)
    assert allowed == 5
