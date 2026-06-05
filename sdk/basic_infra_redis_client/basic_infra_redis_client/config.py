"""Redis client settings (data plane). Env prefix BASIC_INFRA_REDIS_.

ENV split discipline (ADR-0011/0013/0014): `env` is read from
BASIC_INFRA_REDIS_ENV and is deliberately NOT unified with the application ENV
via AliasChoices.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .namespace import RedisNamespace, derive_namespace


class RedisSettings(BaseSettings):
    """Connection + tenancy settings for the shared Redis layer."""

    model_config = SettingsConfigDict(
        env_prefix="BASIC_INFRA_REDIS_",
        extra="ignore",
    )

    host: str = Field(default="redis-shared")
    port: int = Field(default=6379)
    # Per-tenant ACL user + password (provisioned by the control plane).
    username: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None)
    # Isolation is by ACL key-pattern on db 0, not by db number.
    db: int = Field(default=0)
    # The tenant string; the namespace is derived from it.
    tenant: str = Field(default="default")
    ssl: bool = Field(default=False)
    # Explicit deployment-env field; NOT aliased to the app ENV by design.
    env: str = Field(default="local")
    max_connections: int = Field(default=20, ge=1)

    @property
    def namespace(self) -> str:
        return derive_namespace(self.tenant)

    def namespacer(self) -> RedisNamespace:
        return RedisNamespace(self.namespace)

    def dsn(self) -> str:
        scheme = "rediss" if self.ssl else "redis"
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        elif self.password:
            auth = f":{self.password}@"
        return f"{scheme}://{auth}{self.host}:{self.port}/{self.db}"


@lru_cache(maxsize=1)
def get_settings() -> RedisSettings:
    return RedisSettings()
