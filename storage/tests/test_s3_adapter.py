"""Интеграционные тесты S3-совместимого адаптера через moto.

Покрывают путь MinIO/S3, который unit-тесты (filesystem-only) не трогают.
Регрессия: `get()` → `BlobData.stream()` падал с AttributeError, потому что
`iter_chunks` вызывался на результате `async with body` (aiohttp
ClientResponse), а не на самом aiobotocore StreamingBody.

moto патчит botocore на HTTP-уровне и НЕ перехватывает aiohttp-запросы
aiobotocore, поэтому используется реальный out-of-process moto server, на
endpoint которого направляется адаптер.
"""

from __future__ import annotations

import socket
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import pytest_asyncio
from aiobotocore.session import AioSession
from moto.server import ThreadedMotoServer

from storage.adapters.minio import MinioAdapter
from storage.ports.exceptions import BlobAlreadyExists, BlobNotFound

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_BUCKET = "test-bucket"
_CREDS = {"access_key": "testing", "secret_key": "testing"}


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


@pytest.fixture(scope="module")
def moto_endpoint() -> Iterator[str]:
    port = _free_port()
    server = ThreadedMotoServer(port=port)
    server.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.stop()


@pytest_asyncio.fixture
async def s3_adapter(moto_endpoint: str) -> AsyncIterator[MinioAdapter]:
    # Сброс состояния moto между тестами + чистый bucket.
    httpx.post(f"{moto_endpoint}/moto-api/reset")
    session = AioSession()
    async with session.create_client(
        "s3",
        endpoint_url=moto_endpoint,
        region_name="us-east-1",
        aws_access_key_id=_CREDS["access_key"],
        aws_secret_access_key=_CREDS["secret_key"],
    ) as client:
        await client.create_bucket(Bucket=_BUCKET)
    adapter = MinioAdapter(
        endpoint_url=moto_endpoint,
        bucket=_BUCKET,
        access_key=_CREDS["access_key"],
        secret_key=_CREDS["secret_key"],
    )
    try:
        yield adapter
    finally:
        # Закрываем разделяемый клиент (Week 10 lifecycle fix).
        await adapter.aclose()


async def test_put_then_get_roundtrip_via_stream(s3_adapter: MinioAdapter) -> None:
    """Регрессия: get() + stream() должны вернуть записанные байты."""
    payload = b"s3 adapter regression payload"
    await s3_adapter.put(
        tenant_id="telcoss", key="docs/a.txt", data=payload, content_type="text/plain"
    )

    blob = await s3_adapter.get(tenant_id="telcoss", key="docs/a.txt")

    # .bytes() внутри прогоняет .stream() — именно этот путь был сломан.
    assert await blob.bytes() == payload

    # И явная итерация по чанкам.
    blob2 = await s3_adapter.get(tenant_id="telcoss", key="docs/a.txt")
    collected = b"".join([chunk async for chunk in blob2.stream()])
    assert collected == payload


async def test_streaming_put_accepts_async_iterator(s3_adapter: MinioAdapter) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b"part1"
        yield b"part2"

    ref = await s3_adapter.put(tenant_id="telcoss", key="big.bin", data=chunks())
    assert ref.size == len(b"part1part2")

    blob = await s3_adapter.get(tenant_id="telcoss", key="big.bin")
    assert await blob.bytes() == b"part1part2"


async def test_get_missing_raises_blob_not_found(s3_adapter: MinioAdapter) -> None:
    with pytest.raises(BlobNotFound):
        await s3_adapter.get(tenant_id="telcoss", key="nope.txt")


async def test_head_returns_metadata_and_none(s3_adapter: MinioAdapter) -> None:
    await s3_adapter.put(
        tenant_id="telcoss", key="m.txt", data=b"1234", content_type="text/plain"
    )
    meta = await s3_adapter.head(tenant_id="telcoss", key="m.txt")
    assert meta is not None
    assert meta.size == 4
    assert meta.content_type == "text/plain"

    assert await s3_adapter.head(tenant_id="telcoss", key="absent") is None


async def test_list_returns_only_tenant_keys(s3_adapter: MinioAdapter) -> None:
    await s3_adapter.put(tenant_id="telcoss", key="a.txt", data=b"a")
    await s3_adapter.put(tenant_id="telcoss", key="sub/b.txt", data=b"b")
    await s3_adapter.put(tenant_id="pamyat-naroda", key="c.txt", data=b"c")

    telcoss_keys = sorted([r.key async for r in s3_adapter.list(tenant_id="telcoss")])
    assert telcoss_keys == ["a.txt", "sub/b.txt"]

    prefixed = [r.key async for r in s3_adapter.list(tenant_id="telcoss", prefix="sub/")]
    assert prefixed == ["sub/b.txt"]


async def test_delete_is_idempotent(s3_adapter: MinioAdapter) -> None:
    await s3_adapter.put(tenant_id="telcoss", key="d.txt", data=b"x")
    await s3_adapter.delete(tenant_id="telcoss", key="d.txt")
    assert await s3_adapter.head(tenant_id="telcoss", key="d.txt") is None
    # Повторное удаление не падает.
    await s3_adapter.delete(tenant_id="telcoss", key="d.txt")


async def test_if_none_match_blocks_overwrite(s3_adapter: MinioAdapter) -> None:
    await s3_adapter.put(tenant_id="telcoss", key="once.txt", data=b"first")
    with pytest.raises(BlobAlreadyExists):
        await s3_adapter.put(
            tenant_id="telcoss", key="once.txt", data=b"second", if_none_match=True
        )


async def test_presigned_get_url_downloads(s3_adapter: MinioAdapter) -> None:
    payload = b"presigned body"
    await s3_adapter.put(tenant_id="telcoss", key="p.txt", data=payload)

    url = await s3_adapter.presigned_url(
        tenant_id="telcoss", key="p.txt", op="GET", ttl_seconds=300
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
    assert resp.status_code == 200
    assert resp.content == payload
