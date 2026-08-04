"""Rate limit rules. One rule per (route, identity class) — tiered config."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Rule(BaseModel):
    capacity: int = Field(gt=0)
    refill_rate: float = Field(gt=0)
    ttl_seconds: int = Field(default=120, gt=0)


RULES: dict[str, Rule] = {
    "write_free": Rule(capacity=10, refill_rate=20 / 60),
    "read_free": Rule(capacity=100, refill_rate=300 / 60),
    "ip_write": Rule(capacity=30, refill_rate=60 / 60),
}
