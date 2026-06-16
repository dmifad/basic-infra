"""Контекстное хранилище через contextvars.

Используется для:

- ``request_id`` — корреляционный идентификатор, подставляется во все
  логи и (через histogram exemplar при необходимости) в метрики.
- ``tenant_override`` — для multi-tenant воркеров, обслуживающих
  несколько тенантов в одном процессе (один контейнер, разные tenant_id
  в разных запросах). Перебивает ``tenant`` из настроек на время блока.

contextvars автоматически работают с asyncio: каждая task получает
свою копию контекста.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_request_id: ContextVar[str | None] = ContextVar(
    "basic_infra_observability_request_id", default=None
)
_tenant_override: ContextVar[str | None] = ContextVar(
    "basic_infra_observability_tenant_override", default=None
)


def get_request_id() -> str | None:
    """Возвращает текущий request_id или None если не установлен."""
    return _request_id.get()


def set_request_id(value: str) -> None:
    """Устанавливает request_id для текущего контекста.

    Используйте ``request_scope`` для автоматического сброса.
    """
    _request_id.set(value)


def get_tenant_override() -> str | None:
    """Возвращает tenant override или None."""
    return _tenant_override.get()


@contextmanager
def request_scope(request_id: str | None = None) -> Iterator[str]:
    """Контекст-менеджер для request lifecycle.

    Устанавливает request_id (генерирует UUID4 если не передан),
    автоматически сбрасывает при выходе.

    Использование::

        with request_scope() as rid:
            log.info("processing request")  # автоматически содержит request_id=rid
    """
    if request_id is None:
        request_id = str(uuid.uuid4())
    token = _request_id.set(request_id)
    try:
        yield request_id
    finally:
        _request_id.reset(token)


@contextmanager
def tenant_scope(tenant_id: str) -> Iterator[None]:
    """Контекст-менеджер для tenant override.

    Перебивает дефолтный tenant из настроек на время блока. Используется
    в multi-tenant worker'ах.

    Использование::

        with tenant_scope("telcoss"):
            process_document()  # все логи и метрики в этом блоке — с tenant=telcoss
    """
    token = _tenant_override.set(tenant_id)
    try:
        yield
    finally:
        _tenant_override.reset(token)
