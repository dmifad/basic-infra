"""Конфигурация postgres SDK (data plane для client projects).

Все настройки — env vars с префиксом ``BASIC_INFRA_POSTGRES_``.

Соответствует контракту переменных окружения platform-слоя. Поле ``env``
читается из ``BASIC_INFRA_POSTGRES_ENV`` (SDK-namespaced), параллельно
глобальной платформенной ``ENV`` — split осознанный, по образцу
observability SDK (ADR-0011 §Config, ADR-0013 §Config).
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["local", "managed"]
Environment = Literal["dev", "staging", "prod"]


class PostgresSettings(BaseSettings):
    """Настройки подключения client project к своей tenant-БД.

    Client project знает только свою БД — admin-креды (provisioning) сюда
    не входят, это control plane (см. ``postgres.LocalAdapter``).

    :ivar tenant: client project. Имя БД выводится из него детерминированно,
        если ``database`` не задан явно.
    :ivar provider: ``local`` | ``managed``. Переключение local↔cloud — только
        через env, без изменения кода (provider portability, ADR-0013).
    :ivar database: имя БД. По умолчанию выводится из ``tenant``.
    :ivar sslmode: TLS-режим; для ``managed`` практически всегда ``require``.
    """

    model_config = SettingsConfigDict(
        env_prefix="BASIC_INFRA_POSTGRES_",
        case_sensitive=False,
        extra="ignore",
    )

    tenant: str = Field(..., min_length=1)
    env: Environment = Field(default="dev")
    provider: Provider = Field(default="local")

    host: str = Field(default="localhost")
    port: int = Field(default=5434, ge=1, le=65535)
    user: str = Field(...)
    password: str = Field(...)
    database: str | None = Field(default=None)
    sslmode: str | None = Field(default=None)

    # Пул SQLAlchemy.
    pool_size: int = Field(default=5, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=100)
    pool_timeout: float = Field(default=30.0, gt=0)
    pool_recycle: int = Field(default=1800, ge=-1)
    echo: bool = Field(default=False)

    @model_validator(mode="after")
    def _resolve_database(self) -> PostgresSettings:
        if self.database is None:
            # Локальный импорт: SDK не тянет control-plane пакет в граф зависимостей
            # на уровне модуля; здесь — лишь чистая функция вывода имени.
            self.database = self.tenant.lower().replace("-", "_")
        return self

    @model_validator(mode="after")
    def _managed_requires_ssl(self) -> PostgresSettings:
        if self.provider == "managed" and self.sslmode is None:
            self.sslmode = "require"
        return self
