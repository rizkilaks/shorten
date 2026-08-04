"""Redis-backed token bucket with a Lua-atomic read-modify-write."""

from __future__ import annotations

import time
from typing import NamedTuple

import redis.asyncio as redis
from redis.exceptions import RedisError

TOKEN_BUCKET_LUA = """
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local current = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(current[1])
local ts = tonumber(current[2])

if not tokens then
  tokens = capacity
  ts = now
end

local dt = (now - ts) / 1000
if dt > 0 then
  tokens = math.min(capacity, tokens + dt * rate)
  ts = now
end

local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end

redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', ts)
redis.call('EXPIRE', KEYS[1], ttl)

local remaining = math.floor(tokens)
local time_to_next = 0
if allowed == 0 then
  time_to_next = (cost - tokens) / rate
end
local time_to_full = (capacity - tokens) / rate
return {allowed, remaining, time_to_next, time_to_full}
"""


class CheckResult(NamedTuple):
    allowed: bool
    remaining: int
    time_to_next: float
    time_to_full: float


class TokenBucketStore:
    def __init__(self, url: str) -> None:
        self._client = redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)

    async def check(
        self,
        key: str,
        capacity: float,
        rate: float,
        ttl: int,
        *,
        cost: int = 1,
        now_ms: int | None = None,
    ) -> CheckResult:
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        res = await self._client.eval(
            TOKEN_BUCKET_LUA,
            1,
            key,
            capacity,
            rate,
            now_ms,
            cost,
            ttl,
        )
        return CheckResult(
            allowed=bool(int(res[0])),
            remaining=int(res[1]),
            time_to_next=float(res[2]),
            time_to_full=float(res[3]),
        )

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except RedisError:
            return False

    async def flush(self) -> None:
        await self._client.flushall()

    async def aclose(self) -> None:
        await self._client.aclose()
