"""Demo settings, configurable via DEMO_* env vars."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    limiter_url: str = "http://localhost:8000"
    base_url: str = "http://localhost:8080"
    db_path: str = "data/links.db"

    model_config = {"env_prefix": "DEMO_"}
