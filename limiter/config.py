"""Limiter settings, configurable via LIMITER_* env vars."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379"

    model_config = {"env_prefix": "LIMITER_"}
