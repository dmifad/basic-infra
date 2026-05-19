"""Gateway configuration loaded from environment variables.

All env vars documented in .env.example at repo root.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Gateway service
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8003
    gateway_log_level: str = "INFO"
    gateway_log_format: str = "json"  # "json" or "console"

    # Tenant store
    tenant_db_path: Path = Path("/data/tenants/tenants.db")

    # Rate limiting
    redis_url: str = "redis://redis:6379/0"
    rate_limit_fail_open: bool = True

    # Backend registry
    backends_config: Path = Path("/app/backends.yaml")
    backend_health_interval_seconds: int = 30
    backend_unhealthy_threshold: int = 3
    backend_request_timeout_seconds: int = 900


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached :class:`Settings` instance.

    Cached so env parsing happens once. Tests that need a different config
    construct :class:`Settings` directly and pass it to ``create_app``.
    """
    return Settings()
