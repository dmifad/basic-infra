"""Gateway configuration loaded from environment variables.

All env vars documented in .env.example at repo root.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
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


# Module-level singleton (created on import — keep import side-effect-free)
# Use `from .config import get_settings; settings = get_settings()` in code paths.
def get_settings() -> Settings:
    """Returns cached settings instance.

    TODO(week4-phase-3): add @lru_cache decoration.
    """
    return Settings()
