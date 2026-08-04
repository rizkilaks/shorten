"""Persistent link store: SQLite (WAL) via aiosqlite, raw SQL, no ORM."""

from __future__ import annotations

from dataclasses import dataclass

import aiosqlite

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS links (
  code TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  user_id TEXT,
  created_at INTEGER NOT NULL,
  hits INTEGER NOT NULL DEFAULT 0,
  last_used INTEGER
)
"""


@dataclass
class Link:
    code: str
    url: str
    user_id: str | None
    created_at: int
    hits: int
    last_used: int | None


class SQLiteStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute(CREATE_TABLE_SQL)
            await db.commit()

    async def put(self, code: str, url: str, user_id: str | None, created_at: int) -> bool:
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    "INSERT INTO links (code, url, user_id, created_at) VALUES (?, ?, ?, ?)",
                    (code, url, user_id, created_at),
                )
                await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def get(self, code: str) -> Link | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM links WHERE code = ?", (code,)) as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        return Link(**dict(row))

    async def record_hit(self, code: str, ts: int) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE links SET hits = hits + 1, last_used = ? WHERE code = ?", (ts, code)
            )
            await db.commit()

    async def recent(self, limit: int = 20) -> list[Link]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM links ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as cur:
                rows = await cur.fetchall()
        return [Link(**dict(row)) for row in rows]
