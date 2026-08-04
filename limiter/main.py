"""Rate limiter HTTP service.

POST /v1/check  -> 200 {allowed, limit, remaining, reset_at} | 429 {error, retry_after_s, ...}
GET  /v1/health -> {status, mode}

Fail-open: if Redis errors, answer `allowed: true` with `X-RateLimit-Mode: degraded`.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from redis.exceptions import RedisError

from limiter.config import Settings
from limiter.rules import RULES
from limiter.storage import CheckResult, TokenBucketStore

logger = logging.getLogger("limiter")


class CheckRequest(BaseModel):
    user_id: str | None = None
    rule_key: str
    cost: int = Field(default=1, ge=1, le=100)


def _identity(req: CheckRequest, request: Request) -> str:
    if req.user_id:
        cleaned = "".join(ch for ch in req.user_id if ch.isalnum() or ch in "_-")
        if cleaned:
            return f"u:{cleaned[:64]}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title="rate limiter")
    app.state.store = TokenBucketStore(settings.redis_url)

    @app.get("/v1/health")
    async def health(request: Request) -> dict[str, str]:
        store: TokenBucketStore = request.app.state.store
        redis_up = await store.ping()
        return {"status": "ok", "mode": "normal" if redis_up else "degraded"}

    @app.post("/v1/check")
    async def check(req: CheckRequest, request: Request) -> JSONResponse:
        store: TokenBucketStore = request.app.state.store
        rule = RULES.get(req.rule_key)
        if rule is None:
            raise HTTPException(status_code=400, detail=f"unknown rule_key: {req.rule_key}")
        if req.cost > rule.capacity:
            raise HTTPException(
                status_code=422,
                detail=f"cost {req.cost} exceeds rule capacity {rule.capacity}",
            )

        key = f"rl:{req.rule_key}:{_identity(req, request)}"
        try:
            result: CheckResult | None = await store.check(
                key, rule.capacity, rule.refill_rate, rule.ttl_seconds, cost=req.cost
            )
            mode = "normal"
        except RedisError as exc:  # fail-open by design: degraded protection > dead service
            logger.warning("degraded mode (Redis error): %s", exc)
            result = None
            mode = "degraded"

        if mode == "degraded":
            now_s = int(time.time())
            headers = {
                "X-RateLimit-Limit": str(rule.capacity),
                "X-RateLimit-Remaining": str(rule.capacity),
                "X-RateLimit-Reset": str(now_s),
                "X-RateLimit-Mode": "degraded",
            }
            return JSONResponse(
                status_code=200,
                content={
                    "allowed": True,
                    "limit": rule.capacity,
                    "remaining": rule.capacity,
                    "reset_at": now_s,
                },
                headers=headers,
            )

        assert result is not None
        now_s = int(time.time())
        reset_at = now_s + int(result.time_to_full if result.allowed else result.time_to_next)
        headers = {
            "X-RateLimit-Limit": str(rule.capacity),
            "X-RateLimit-Remaining": str(result.remaining if result.allowed else 0),
            "X-RateLimit-Reset": str(reset_at),
        }
        if not result.allowed:
            retry_after_s = max(1, int(result.time_to_next))
            headers["Retry-After"] = str(retry_after_s)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limited",
                    "limit": rule.capacity,
                    "remaining": 0,
                    "reset_at": reset_at,
                    "retry_after_s": retry_after_s,
                },
                headers=headers,
            )
        return JSONResponse(
            status_code=200,
            content={
                "allowed": True,
                "limit": rule.capacity,
                "remaining": result.remaining,
                "reset_at": reset_at,
            },
            headers=headers,
        )

    return app
