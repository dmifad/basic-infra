"""basic_infra_storage_client — SDK для хранилища блобов basic-infra.

Публичный API:

- ``AsyncBlobStoreClient`` — асинхронный tenant-scoped клиент.
- ``BlobStoreClient`` — синхронная обёртка.
- ``StorageSettings`` — конфигурация из переменных окружения.
- ``BlobRef``, ``BlobMetadata``, ``BlobData`` — value objects.
- Исключения порта.
"""

from storage.ports.blob_store import (
    BlobData,
    BlobMetadata,
    BlobRef,
    PresignedOp,
)
from storage.ports.exceptions import (
    BlobAlreadyExists,
    BlobNotFound,
    BlobStoreConfigError,
    BlobStoreError,
    BlobStoreUnavailable,
    TenantIsolationError,
)

from basic_infra_storage_client.async_client import AsyncBlobStoreClient
from basic_infra_storage_client.client import BlobStoreClient
from basic_infra_storage_client.config import StorageSettings

__all__ = [
    "AsyncBlobStoreClient",
    "BlobStoreClient",
    "StorageSettings",
    "BlobData",
    "BlobMetadata",
    "BlobRef",
    "PresignedOp",
    "BlobStoreError",
    "BlobNotFound",
    "BlobAlreadyExists",
    "BlobStoreUnavailable",
    "BlobStoreConfigError",
    "TenantIsolationError",
]

__version__ = "0.1.0"
