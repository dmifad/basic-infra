"""Адаптер для MinIO.

MinIO говорит по S3 API. Отличие от AWS S3:

- Кастомный endpoint URL (обычно `http://minio:9000` внутри compose).
- Path-style URLs вместо virtual-hosted (MinIO так удобнее).
- HTTP по умолчанию (внутри compose), TLS опционально.
- Access/secret keys в plain (не IAM-role).
"""

from __future__ import annotations

from storage.adapters._s3_compatible import _S3CompatibleAdapter


class MinioAdapter(_S3CompatibleAdapter):
    """S3-совместимый адаптер для MinIO.

    :param endpoint_url: URL MinIO сервера, например ``http://minio:9000``.
    :param bucket: имя bucket'а. Должен существовать (см. minio-init в
        ``storage/compose/minio.yml``).
    :param access_key: MinIO access key.
    :param secret_key: MinIO secret key.
    :param use_ssl: использовать ли TLS. По умолчанию ``False`` — внутри
        compose-сети TLS не нужен.
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        use_ssl: bool = False,
        region_name: str = "us-east-1",
    ) -> None:
        super().__init__(
            bucket=bucket,
            endpoint_url=endpoint_url,
            region_name=region_name,
            access_key=access_key,
            secret_key=secret_key,
            use_ssl=use_ssl,
        )
