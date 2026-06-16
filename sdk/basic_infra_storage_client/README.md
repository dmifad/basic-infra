# basic-infra-storage-client

SDK для хранилища блобов basic-infra. Дистрибутирует `BlobStorePort` и три
адаптера (MinIO, AWS S3, локальная ФС) клиентским репозиториям экосистемы.

См. [ADR-0010](../../docs/adr/0010-storage-abstraction.md) для архитектурного
контекста.

## Установка

Поскольку basic-infra public, можно ставить напрямую из GitHub:

```bash
pip install "basic-infra-storage-client @ git+https://github.com/<org>/basic-infra.git#subdirectory=sdk/basic_infra_storage_client"
```

В клиентских репозиториях рекомендуется фиксировать commit hash, как это
сделано для `vams_llm_client`.

## Конфигурация

Через переменные окружения:

```bash
# Production — AWS S3
BASIC_INFRA_STORAGE_BACKEND=s3
BASIC_INFRA_STORAGE_BUCKET=basic-infra-prod
BASIC_INFRA_STORAGE_REGION=eu-central-1
# Credentials — через IAM role, env vars или ~/.aws/credentials

# Локальная разработка — MinIO в compose
BASIC_INFRA_STORAGE_BACKEND=minio
BASIC_INFRA_STORAGE_BUCKET=basic-infra-dev
BASIC_INFRA_STORAGE_ENDPOINT_URL=http://minio:9000
BASIC_INFRA_STORAGE_ACCESS_KEY=minioadmin
BASIC_INFRA_STORAGE_SECRET_KEY=minioadmin

# Миграционный режим — поверх существующей раскладки на диске
BASIC_INFRA_STORAGE_BACKEND=filesystem
BASIC_INFRA_STORAGE_FILESYSTEM_ROOT=/var/telcoss/pdf-intake
```

## Базовое использование

### Async

```python
from basic_infra_storage_client import AsyncBlobStoreClient

async def upload_pdf(pdf_bytes: bytes) -> str:
    client = AsyncBlobStoreClient(tenant_id="telcoss")
    ref = await client.put(
        key="pdf-intake/inbox/2026-05-23-doc.pdf",
        data=pdf_bytes,
        content_type="application/pdf",
        metadata={"source": "operator-portal"},
    )
    return ref.etag
```

### Streaming

```python
async def download_pdf_to_disk(key: str, dest: str) -> None:
    client = AsyncBlobStoreClient(tenant_id="telcoss")
    blob = await client.get(key=key)
    async with aiofiles.open(dest, "wb") as f:
        async for chunk in blob.stream():
            await f.write(chunk)
```

### Presigned URL

```python
async def share_dossier(key: str) -> str:
    """Дать внешнему подписанту 24-часовую ссылку на дossier."""
    client = AsyncBlobStoreClient(tenant_id="telcoss")
    return await client.presigned_url(
        key=key,
        op="GET",
        ttl_seconds=86400,
    )
```

### Sync (для скриптов и CLI)

```python
from basic_infra_storage_client import BlobStoreClient

client = BlobStoreClient(tenant_id="telcoss")
pdf = client.get(key="pdf-intake/inbox/doc.pdf")
```

## Изоляция тенантов

`tenant_id` — обязательный аргумент конструктора. После создания клиента
все его методы работают только в пределах этого тенанта. Cross-tenant
операции невозможны: для другого тенанта создайте отдельный клиент.

Адаптер сам конструирует итоговый объектный ключ из `tenant_id` и `key`.
Прикладной код физически не может пересечь границу — попытки
вложить `..` или абсолютный путь в `key` поднимают `TenantIsolationError`.
