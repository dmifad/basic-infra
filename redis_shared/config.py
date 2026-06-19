"""Control-plane (admin) settings. Env prefix REDIS_ADMIN_.

Separate from the data-plane BASIC_INFRA_REDIS_* so tenant apps never carry
admin credentials. ENV split preserved (REDIS_ADMIN_ENV).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REDIS_ADMIN_",
        # Load admin creds from the repo .env so the control-plane CLI works
        # however it is invoked (make targets, direct `python -m redis_shared.cli`).
        # Real environment variables still take precedence over the file.
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="127.0.0.1")
    port: int = Field(default=6380)
    username: str = Field(default="default")
    password: Optional[str] = Field(default=None)
    ssl: bool = Field(default=False)
    env: str = Field(default="local")
    # If the server uses an aclfile, persist ACL changes after each mutation.
    acl_save: bool = Field(default=True)


@lru_cache(maxsize=1)
def get_admin_settings() -> AdminSettings:
    return AdminSettings()
