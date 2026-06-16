"""Конфигурация SDK клиента хранилища.

Все настройки читаются из переменных окружения с префиксом
``BASIC_INFRA_STORAGE_``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

StorageBackend = Literal["minio", "s3", "filesystem"]


class StorageSettings(BaseSettings):
    """Настройки хранилища блобов.

    :ivar backend: тип backend'а. ``minio`` и ``s3`` ходят по S3 API,
        ``filesystem`` пишет на локальный диск (для dev/тестов и
        миграционного adoption).
    :ivar bucket: имя bucket'а для ``minio``/``s3``.
    :ivar endpoint_url: URL S3-совместимого endpoint'а для ``minio``.
        Игнорируется для ``s3`` (AWS default endpoints).
    :ivar region: AWS-регион для ``s3``. Для ``minio`` — формальное
        значение, используется только для подписи запросов.
    :ivar access_key/secret_key: credentials. Для ``s3`` опциональны
        (fallback на стандартную цепочку botocore). Для ``minio``
        обязательны.
    :ivar filesystem_root: корневая директория для ``filesystem``.
    :ivar use_ssl: TLS для S3-совместимого endpoint'а. По умолчанию
        ``True`` для ``s3``, ``False`` для ``minio`` внутри compose.
    """

    model_config = SettingsConfigDict(
        env_prefix="BASIC_INFRA_STORAGE_",
        case_sensitive=False,
        extra="ignore",
    )

    backend: StorageBackend = Field(default="filesystem")

    # S3-compatible settings
    bucket: str | None = None
    endpoint_url: str | None = None
    region: str = "us-east-1"
    access_key: str | None = None
    secret_key: str | None = None
    use_ssl: bool | None = None

    # Filesystem settings
    filesystem_root: str | None = None

    @model_validator(mode="after")
    def _validate_backend_settings(self) -> "StorageSettings":
        if self.backend == "filesystem":
            if not self.filesystem_root:
                raise ValueError(
                    "filesystem backend requires BASIC_INFRA_STORAGE_FILESYSTEM_ROOT"
                )
        elif self.backend == "minio":
            missing = [
                name
                for name, value in (
                    ("BUCKET", self.bucket),
                    ("ENDPOINT_URL", self.endpoint_url),
                    ("ACCESS_KEY", self.access_key),
                    ("SECRET_KEY", self.secret_key),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"minio backend requires: "
                    f"{', '.join('BASIC_INFRA_STORAGE_' + m for m in missing)}"
                )
        elif self.backend == "s3":
            if not self.bucket:
                raise ValueError(
                    "s3 backend requires BASIC_INFRA_STORAGE_BUCKET"
                )
            # access_key/secret_key опциональны — botocore разрешает credentials.

        # Дефолты use_ssl по backend.
        if self.use_ssl is None:
            object.__setattr__(
                self, "use_ssl", self.backend == "s3"
            )

        return self
