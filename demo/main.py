"""TinyURL-style shortener. The limiter is a built-in feature: every /shorten asks it first."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

from demo.config import Settings
from demo.limiter_client import LimiterClient
from demo.shortcode import generate_code
from demo.store import SQLiteStore

logger = logging.getLogger("shortener")

MAX_COLLISION_ATTEMPTS = 5
STATIC_DIR = Path(__file__).parent / "static"


class ShortenRequest(BaseModel):
    url: HttpUrl
    user_id: str | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    store = SQLiteStore(settings.db_path)
    limiter = LimiterClient(settings.limiter_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await store.init()
        yield
        await limiter.aclose()

    app = FastAPI(title="shortener", lifespan=lifespan)
    app.state.store = store
    app.state.limiter = limiter
    app.state.settings = settings

    @app.get("/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/shorten", response_model=None)
    async def shorten(req: ShortenRequest, request: Request) -> JSONResponse | dict[str, object]:
        rl: LimiterClient = request.app.state.limiter
        mem: SQLiteStore = request.app.state.store
        cfg: Settings = request.app.state.settings

        try:
            status, body = await rl.check(
                rule_key="write_free" if req.user_id else "ip_write",
                user_id=req.user_id,
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("limiter unavailable, failing open: %s", exc)
            status, body = 200, {"allowed": True}

        if status == 429:
            retry_after_raw = body.get("retry_after_s")
            retry_after_s = max(
                1, int(float(retry_after_raw)) if isinstance(retry_after_raw, (int, str)) else 1
            )
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limited", "retry_after_s": retry_after_s},
                headers={"Retry-After": str(retry_after_s)},
            )
        if status >= 500:
            raise HTTPException(status_code=502, detail="limiter unavailable")

        created_at = int(time.time())
        for _ in range(MAX_COLLISION_ATTEMPTS):
            code = generate_code()
            if await mem.put(code, str(req.url), req.user_id, created_at):
                return {
                    "short_code": code,
                    "short_url": f"{cfg.base_url}/{code}",
                    "created_at": created_at,
                    "hits": 0,
                }
        raise HTTPException(status_code=500, detail="could not allocate a short code")

    @app.get("/recent")
    async def recent(request: Request) -> dict[str, list[dict[str, object]]]:
        mem: SQLiteStore = request.app.state.store
        cfg: Settings = request.app.state.settings
        links = await mem.recent(20)
        return {
            "links": [
                {
                    "code": link.code,
                    "short_url": f"{cfg.base_url}/{link.code}",
                    "url": link.url,
                    "hits": link.hits,
                    "created_at": link.created_at,
                }
                for link in links
            ]
        }

    @app.get("/{code}")
    async def redirect_to(code: str, request: Request) -> RedirectResponse:
        mem: SQLiteStore = request.app.state.store
        link = await mem.get(code)
        if link is None:
            raise HTTPException(status_code=404, detail="not found")
        await mem.record_hit(code, int(time.time()))
        return RedirectResponse(link.url, status_code=301)

    app.mount(
        "/", StaticFiles(directory=STATIC_DIR, html=True, check_dir=False), name="static"
    )
    return app
