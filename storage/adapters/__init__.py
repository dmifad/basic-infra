"""Адаптеры хранилища блобов."""

from storage.adapters.filesystem import FilesystemAdapter
from storage.adapters.minio import MinioAdapter
from storage.adapters.s3 import S3Adapter

__all__ = ["FilesystemAdapter", "MinioAdapter", "S3Adapter"]
