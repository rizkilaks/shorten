"""HTTP client for the limiter service."""

from __future__ import annotations

import httpx


class LimiterClient:
    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=1.0)

    async def check(
        self, *, rule_key: str, user_id: str | None
    ) -> tuple[int, dict[str, object]]:
        resp = await self._client.post(
            "/v1/check", json={"rule_key": rule_key, "user_id": user_id}
        )
        return resp.status_code, resp.json()

    async def aclose(self) -> None:
        await self._client.aclose()
