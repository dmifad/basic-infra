"""Unit-тесты жизненного цикла клиента S3-совместимого адаптера.

Регрессия Week 10: раньше каждая операция открывала свой aiobotocore-клиент,
а ``get()`` вовсе не закрывал его — утечка соединений под нагрузкой. Теперь
клиент создаётся один раз, кэшируется на адаптере и закрывается в ``aclose()``.

Эти тесты не ходят в сеть и не поднимают moto: ``AioSession.create_client``
подменяется фейковым async-context-manager'ом, который считает создания/входы/
выходы. Так мы проверяем именно lifecycle, а не S3-семантику (она — в
``test_s3_adapter.py`` через moto).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncIterator

import pytest

from storage.adapters.minio import MinioAdapter

pytestmark = pytest.mark.asyncio


class _FakeStreamingBody:
    """Минимальный двойник aiobotocore StreamingBody для get()."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    async def __aenter__(self) -> "_FakeStreamingBody":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def iter_chunks(self, chunk_size: int) -> AsyncIterator[bytes]:
        yield self._data


class _FakeS3Client:
    """Двойник S3-клиента: отвечает на операции, которые трогают тесты."""

    async def put_object(self, **kwargs: Any) -> dict[str, Any]:
        return {"ETag": '"fake-etag"'}

    async def get_object(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "Body": _FakeStreamingBody(b"payload"),
            "ContentLength": len(b"payload"),
            "ContentType": "application/octet-stream",
            "ETag": '"fake-etag"',
        }

    async def head_object(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "ContentLength": 7,
            "ETag": '"fake-etag"',
            "LastModified": datetime.now(timezone.utc),
            "ContentType": "application/octet-stream",
            "Metadata": {},
        }

    async def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        return {}


class _RecordingClientCM:
    """Async-CM вокруг одного клиента, считающий enter/exit на общем ledger."""

    def __init__(self, ledger: dict[str, int], client: _FakeS3Client) -> None:
        self._ledger = ledger
        self._client = client

    async def __aenter__(self) -> _FakeS3Client:
        self._ledger["enter"] += 1
        return self._client

    async def __aexit__(self, *exc: object) -> bool:
        self._ledger["exit"] += 1
        return False


def _patch_session(
    adapter: MinioAdapter, ledger: dict[str, int]
) -> None:
    """Подменить create_client фабрикой, считающей создания клиента."""
    client = _FakeS3Client()

    def _create_client(*args: Any, **kwargs: Any) -> _RecordingClientCM:
        ledger["create"] += 1
        return _RecordingClientCM(ledger, client)

    adapter._session.create_client = _create_client


def _make_adapter() -> MinioAdapter:
    return MinioAdapter(
        endpoint_url="http://minio:9000",
        bucket="test-bucket",
        access_key="k",
        secret_key="s",
    )


async def test_client_constructed_once_across_mixed_ops() -> None:
    adapter = _make_adapter()
    ledger = {"create": 0, "enter": 0, "exit": 0}
    _patch_session(adapter, ledger)

    await adapter.put(tenant_id="telcoss", key="a.txt", data=b"payload")
    blob = await adapter.get(tenant_id="telcoss", key="a.txt")
    assert await blob.bytes() == b"payload"
    await adapter.head(tenant_id="telcoss", key="a.txt")
    await adapter.delete(tenant_id="telcoss", key="a.txt")

    # Несмотря на четыре операции — ровно одно создание и один вход в клиент.
    assert ledger["create"] == 1
    assert ledger["enter"] == 1
    # Клиент ещё не закрыт — aclose() не вызывался.
    assert ledger["exit"] == 0


async def test_client_closed_when_aclose_called() -> None:
    adapter = _make_adapter()
    ledger = {"create": 0, "enter": 0, "exit": 0}
    _patch_session(adapter, ledger)

    await adapter.head(tenant_id="telcoss", key="a.txt")
    assert ledger["exit"] == 0

    await adapter.aclose()
    assert ledger["exit"] == 1


async def test_aclose_without_any_op_is_noop() -> None:
    adapter = _make_adapter()
    ledger = {"create": 0, "enter": 0, "exit": 0}
    _patch_session(adapter, ledger)

    # Клиент ни разу не создавался — закрытие безопасно и ничего не делает.
    await adapter.aclose()
    assert ledger == {"create": 0, "enter": 0, "exit": 0}


async def test_aclose_is_idempotent() -> None:
    adapter = _make_adapter()
    ledger = {"create": 0, "enter": 0, "exit": 0}
    _patch_session(adapter, ledger)

    await adapter.head(tenant_id="telcoss", key="a.txt")
    await adapter.aclose()
    await adapter.aclose()

    # Один созданный клиент закрыт ровно один раз; повторный aclose — no-op.
    assert ledger["create"] == 1
    assert ledger["exit"] == 1


async def test_client_recreated_after_aclose() -> None:
    adapter = _make_adapter()
    ledger = {"create": 0, "enter": 0, "exit": 0}
    _patch_session(adapter, ledger)

    await adapter.head(tenant_id="telcoss", key="a.txt")
    await adapter.aclose()
    # Операция после закрытия лениво пересоздаёт клиент.
    await adapter.head(tenant_id="telcoss", key="a.txt")

    assert ledger["create"] == 2
    assert ledger["enter"] == 2
    assert ledger["exit"] == 1
