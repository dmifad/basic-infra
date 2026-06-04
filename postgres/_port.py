"""Control-plane порт для postgres-multi слоя.

Порт описывает **provisioning** (control plane) per-client-project баз
данных: создание/удаление БД, выдача DSN, health инстанса. Data plane
(engine/session для запросов из самого client project) живёт в SDK
``basic_infra_postgres_client`` — порт его не покрывает намеренно, чтобы
платформенный слой не знал о доменных схемах проектов.

Модель изоляции: **database-per-client-project** (ADR-0013). ``tenant`` —
это client project (платформенное определение, общее со storage и
observability слоями).
"""
from __future__ import annotations

import re
from typing import NewType, Protocol, runtime_checkable

TenantId = NewType("TenantId", str)

# Имя БД выводится из tenant: lowercase, [a-z0-9_], дефисы → подчёркивания.
# Длина ≤ 63 (предел идентификатора PostgreSQL).
_TENANT_RE = re.compile(r"^[a-z][a-z0-9-]{0,61}[a-z0-9]$")


class InvalidTenantError(ValueError):
    """tenant не проходит валидацию для использования как имя БД."""


def database_name(tenant: TenantId) -> str:
    """Детерминированно вывести имя БД из tenant.

    Convention: lowercase, дефисы заменяются на подчёркивания. Имя
    валидируется против правил идентификаторов PostgreSQL (≤ 63 символа,
    начинается с буквы). Бросает :class:`InvalidTenantError` при нарушении.

    Примеры::

        telcoss              -> telcoss
        pamyat-naroda-graph  -> pamyat_naroda_graph
    """
    raw = str(tenant)
    if not _TENANT_RE.match(raw):
        raise InvalidTenantError(
            f"tenant {raw!r} невалиден: ожидается ^[a-z][a-z0-9-]{{0,61}}[a-z0-9]$"
        )
    name = raw.replace("-", "_")
    if len(name) > 63:
        raise InvalidTenantError(f"имя БД {name!r} превышает 63 символа")
    return name


@runtime_checkable
class PostgresPort(Protocol):
    """Control-plane контракт provisioning per-tenant баз данных.

    Все методы идемпотентны там, где это имеет смысл (``provision`` не
    падает, если БД уже есть; ``deprovision`` не падает, если БД нет).
    Реализации не держат пулов соединений — это короткоживущие admin
    операции, выполняемые при bootstrap/деплое, не на горячем пути.
    """

    async def provision(self, tenant: TenantId) -> None:
        """Создать БД для tenant и включить расширение PostGIS.

        Идемпотентно: если БД уже существует, метод гарантирует только
        наличие расширения и возвращается без ошибки.
        """
        ...

    async def deprovision(self, tenant: TenantId) -> None:
        """Удалить БД tenant.

        Идемпотентно: отсутствие БД — не ошибка. Деструктивно; вызывающий
        отвечает за резервные копии. Реализации обязаны отклонять вызов,
        если для инстанса не выставлен флаг разрешения деструктивных
        операций (см. ``LocalAdapter``).
        """
        ...

    async def exists(self, tenant: TenantId) -> bool:
        """True, если БД tenant существует на инстансе."""
        ...

    async def dsn(self, tenant: TenantId, *, driver: str = "asyncpg") -> str:
        """Вернуть SQLAlchemy DSN для БД tenant.

        :param driver: ``asyncpg`` (async) или ``psycopg`` (sync, psycopg3).
        """
        ...

    async def health(self) -> bool:
        """True, если инстанс PostgreSQL достижим (maintenance-БД)."""
        ...
