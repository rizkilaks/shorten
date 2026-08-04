from __future__ import annotations

import pytest

from demo.store import SQLiteStore


@pytest.fixture
async def store(tmp_path) -> SQLiteStore:
    s = SQLiteStore(str(tmp_path / "links.db"))
    await s.init()
    yield s


async def test_put_and_get(store: SQLiteStore) -> None:
    assert await store.put("abc123", "https://x.dev", None, 1)
    link = await store.get("abc123")
    assert link is not None
    assert link.url == "https://x.dev"
    assert link.hits == 0


async def test_duplicate_put_rejected(store: SQLiteStore) -> None:
    assert await store.put("abc123", "https://x.dev", None, 1)
    assert not await store.put("abc123", "https://y.dev", None, 1)


async def test_missing_code_returns_none(store: SQLiteStore) -> None:
    assert await store.get("nope") is None


async def test_record_hit_increments(store: SQLiteStore) -> None:
    await store.put("abc123", "https://x.dev", None, 1)
    await store.record_hit("abc123", 100)
    await store.record_hit("abc123", 200)
    link = await store.get("abc123")
    assert link is not None
    assert link.hits == 2
    assert link.last_used == 200


async def test_recent_returns_newest_first(store: SQLiteStore) -> None:
    for i in range(3):
        await store.put(f"code{i}", f"https://x.dev/{i}", None, i)
    links = await store.recent(2)
    assert [link.code for link in links] == ["code2", "code1"]
