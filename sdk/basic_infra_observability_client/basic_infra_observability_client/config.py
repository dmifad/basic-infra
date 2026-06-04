"""Конфигурация SDK observability клиента.

Все настройки — env vars с префиксом ``BASIC_INFRA_OBSERVABILITY_``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LogFormat = Literal["json", "console"]
Environment = Literal["dev", "staging", "prod"]


class ObservabilitySettings(BaseSettings):
    """Настройки observability клиента.

    :ivar service_name: имя сервиса (обязательно). Попадает в лейбл
        ``service`` всех метрик и логов.
    :ivar env: окружение. Лейбл ``env``.
    :ivar tenant: клиентский тенант (опционально для платформенных
        компонентов). Лейбл ``tenant``.
    :ivar metrics_port: порт для ``/metrics`` endpoint. По умолчанию 9090.
    :ivar log_level: уровень логирования (DEBUG/INFO/WARNING/ERROR/CRITICAL).
    :ivar log_format: ``json`` для прода, ``console`` для локального dev.
    """

    model_config = SettingsConfigDict(
        env_prefix="BASIC_INFRA_OBSERVABILITY_",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = Field(..., min_length=1)
    env: Environment = Field(default="dev")
    tenant: str | None = Field(default=None)

    metrics_port: int = Field(default=9090, ge=1, le=65535)
    metrics_enabled: bool = Field(default=True)

    log_level: str = Field(default="INFO")
    log_format: LogFormat = Field(default="json")
