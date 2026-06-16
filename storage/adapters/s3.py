"""Адаптер для AWS S3.

Использует стандартную AWS-аутентификацию через цепочку источников
учётных данных botocore (IAM role → env vars → ~/.aws/credentials → ...).

Если переданы ``access_key`` и ``secret_key`` — они используются явно;
если нет — botocore сам разрешает credentials из окружения. В production
рекомендуется IAM-role attached to the workload (EC2 instance profile,
ECS task role, EKS service account), credentials в env vars — только
для CI и dev-окружений.
"""

from __future__ import annotations

from storage.adapters._s3_compatible import _S3CompatibleAdapter


class S3Adapter(_S3CompatibleAdapter):
    """Адаптер для AWS S3.

    :param bucket: имя S3 bucket'а.
    :param region_name: AWS-регион bucket'а.
    :param access_key: явный AWS access key. Если не указан — botocore
        возьмёт из стандартной цепочки источников.
    :param secret_key: явный AWS secret key.
    """

    def __init__(
        self,
        *,
        bucket: str,
        region_name: str,
        access_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        super().__init__(
            bucket=bucket,
            endpoint_url=None,  # AWS default endpoints
            region_name=region_name,
            access_key=access_key,
            secret_key=secret_key,
            use_ssl=True,
        )
