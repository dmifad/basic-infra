# basic_infra_postgres_client

Data-plane SDK для подключения client project к своей tenant-БД в слое
**postgres-multi** (модель изоляции: database-per-client-project, ADR-0013).

Control plane (provisioning баз) живёт отдельно — в пакете `postgres`
платформы. Client project никогда не держит admin-креды; SDK подключается
только к своей БД.

## Установка

```bash
pip install -e sdk/basic_infra_postgres_client
```

## Конфигурация

Через env vars (префикс `BASIC_INFRA_POSTGRES_`):

```bash
BASIC_INFRA_POSTGRES_TENANT=telcoss
BASIC_INFRA_POSTGRES_ENV=dev              # SDK-specific; compose-сторона читает ENV (глобальная платформы)
BASIC_INFRA_POSTGRES_PROVIDER=local       # local | managed
BASIC_INFRA_POSTGRES_HOST=localhost
BASIC_INFRA_POSTGRES_PORT=5434            # basic-infra shifted (telcoss держит 5433)
BASIC_INFRA_POSTGRES_USER=app
BASIC_INFRA_POSTGRES_PASSWORD=...
# BASIC_INFRA_POSTGRES_DATABASE=...       # по умолчанию выводится из TENANT
# BASIC_INFRA_POSTGRES_SSLMODE=require    # managed выставляет автоматически
```

`tenant`, `user`, `password` обязательны. `database` по умолчанию выводится
из `tenant` (дефисы → подчёркивания: `pamyat-naroda-graph` → `pamyat_naroda_graph`).

## Базовая адаптация

```python
from basic_infra_postgres_client import (
    PostgresSettings, async_session_factory, session_scope, check_health,
)

settings = PostgresSettings()             # из env
factory = async_session_factory(settings)

# readiness-проба
health = await check_health(settings, require_postgis=True)
assert health.ok

# транзакционная область
async with session_scope(factory) as session:
    await session.execute(...)            # доменные запросы проекта
```

Sync-вариант: `sync_session_factory` / `sync_session_scope` (psycopg3).

## Provider portability

Переключение `local` ↔ `managed` — только через `BASIC_INFRA_POSTGRES_PROVIDER`
и connection-параметры в env. Код client project не меняется.

## Что НЕ входит в SDK

- Доменные модели и Alembic-миграции — ими владеет client project. Платформа
  даёт connection/engine, не схемы (hexagonal: platform не импортирует домен).
- Provisioning баз — control plane (`postgres.LocalAdapter` / `ManagedAdapter`).
- Connection pooling за пределами SQLAlchemy-пула (PgBouncer) — отложено
  (ADR-0013 §Out of scope).
