"""Порт хранилища блобов.

Определяет контракт между basic-infra и конкретными бэкендами хранения
(MinIO, S3, локальная файловая система). Клиентский код зависит от
этого порта, не от конкретных адаптеров.

Платформенные инварианты:

1. `tenant_id` — первоклассный аргумент всех методов. Адаптер сам
   конструирует итоговый объектный ключ из `tenant_id` и `key`.
   Клиентский код не может пересечь границу тенанта (см. ADR-0010).

2. Стриминг по умолчанию. `BlobData.stream()` рекомендуется для
   всего, что больше нескольких килобайт.

3. Минимальный набор операций. Multipart, server-side copy,
   bucket-level operations — out of scope первой версии.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Literal, Protocol, runtime_checkable

PresignedOp = Literal["GET", "PUT"]


@dataclass(frozen=True, slots=True)
class BlobRef:
    """Ссылка на конкретный блоб в хранилище.

    Возвращается из `put` и `list`. `tenant_id` и `key` — то, чем
    клиент адресует блоб; `etag`, `size`, `content_type` — метаданные.
    """

    tenant_id: str
    key: str
    etag: str
    size: int
    content_type: str | None = None


@dataclass(frozen=True, slots=True)
class BlobMetadata:
    """Метаданные блоба без скачивания содержимого.

    Возвращается из `head`.
    """

    tenant_id: str
    key: str
    size: int
    etag: str
    last_modified: datetime
    content_type: str | None = None
    user_metadata: dict[str, str] = field(default_factory=dict)


class BlobData:
    """Содержимое блоба, возвращаемое из `get`.

    Экспонирует два режима чтения:

    - `.stream()` — асинхронный итератор по байтовым чанкам.
      Рекомендуемый путь для всего, что больше ~64 КБ.
    - `.bytes()` — буферизация всего содержимого в память.
      Удобно для мелких объектов; на больших файлах съест RAM.

    Конкретные адаптеры наследуются от этого класса и реализуют оба
    метода через свой механизм стриминга.
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        key: str,
        size: int,
        content_type: str | None,
        etag: str,
    ) -> None:
        self.tenant_id = tenant_id
        self.key = key
        self.size = size
        self.content_type = content_type
        self.etag = etag

    def stream(self) -> AsyncIterator[bytes]:
        raise NotImplementedError

    async def bytes(self) -> bytes:
        chunks: list[bytes] = []
        async for chunk in self.stream():
            chunks.append(chunk)
        return b"".join(chunks)


@runtime_checkable
class BlobStorePort(Protocol):
    """Контракт хранилища блобов.

    Все методы — асинхронные. Все методы принимают `tenant_id` явно.
    """

    async def put(
        self,
        *,
        tenant_id: str,
        key: str,
        data: bytes | AsyncIterator[bytes],
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        if_none_match: bool = False,
    ) -> BlobRef:
        """Записать блоб.

        :param tenant_id: идентификатор тенанта.
        :param key: логический ключ блоба внутри тенанта.
        :param data: содержимое — bytes для мелких объектов, async iterator
            для стриминговой записи.
        :param content_type: MIME-тип. Сохраняется в метаданных объекта.
        :param metadata: пользовательские метаданные (string → string).
        :param if_none_match: если True, поднимает BlobAlreadyExists при
            существующем ключе. По умолчанию — перезапись разрешена.
        :returns: BlobRef с etag и размером записанного объекта.
        :raises BlobAlreadyExists: при if_none_match=True и существующем ключе.
        :raises BlobStoreUnavailable: при недоступности backend'а.
        """
        ...

    async def get(self, *, tenant_id: str, key: str) -> BlobData:
        """Прочитать блоб.

        :raises BlobNotFound: если ключ не существует.
        :raises BlobStoreUnavailable: при недоступности backend'а.
        """
        ...

    async def delete(self, *, tenant_id: str, key: str) -> None:
        """Удалить блоб.

        Идемпотентна: удаление несуществующего ключа не поднимает исключения.

        :raises BlobStoreUnavailable: при недоступности backend'а.
        """
        ...

    async def head(
        self, *, tenant_id: str, key: str
    ) -> BlobMetadata | None:
        """Получить метаданные без скачивания содержимого.

        :returns: BlobMetadata если ключ существует, None если нет.
        :raises BlobStoreUnavailable: при недоступности backend'а.
        """
        ...

    def list(
        self, *, tenant_id: str, prefix: str = ""
    ) -> AsyncIterator[BlobRef]:
        """Итерировать ключи тенанта по префиксу.

        Возвращает async iterator (не coroutine), чтобы поддерживать
        ленивую пагинацию для больших списков.

        :param prefix: префикс внутри тенантного пространства. Пустая
            строка — все ключи тенанта.
        """
        ...

    async def presigned_url(
        self,
        *,
        tenant_id: str,
        key: str,
        op: PresignedOp,
        ttl_seconds: int = 3600,
        content_type: str | None = None,
    ) -> str:
        """Получить временный URL для GET или PUT операции.

        Для GET — позволяет внешним потребителям скачать блоб без
        проксирования через прикладной сервис. Для PUT — позволяет
        внешним поставщикам загрузить файл напрямую.

        :param op: "GET" или "PUT".
        :param ttl_seconds: время жизни URL в секундах.
        :param content_type: для PUT — content-type, который должен быть
            указан загружающей стороной.
        :raises BlobStoreError: если backend не поддерживает presigned URL
            (например, FilesystemAdapter).
        """
        ...

    async def aclose(self) -> None:
        """Освободить ресурсы backend'а (сетевые клиенты, пулы соединений).

        Вызывается на shutdown потребителя. Бэкенды с долгоживущим клиентом
        (MinIO/S3) закрывают его здесь; FilesystemAdapter — no-op. Метод
        добавлен аддитивно: потребители, которые только вызывают операции
        порта, не затронуты — close важен лишь реализациям с lifecycle.
        """
        ...
