# ADR-0013 — postgres-multi: shared PostgreSQL слой (database-per-client-project)

**Статус:** Accepted
**Дата:** 2026-05-31
**Контекст слоя:** Платформенный (basic-infra), Week 8

Резервирование номеров: **ADR-0012 закреплён за distributed tracing**
(OTEL + Tempo, Week 7+; см. bridge v12 §5). postgres-multi занимает 0013,
не 0012, даже если tracing на момент написания ещё не реализован.

---

## Контекст

basic-infra предоставляет client projects переносимые между провайдерами
слабосвязанные слои: LLM-gateway, storage (ADR-0010), observability
(ADR-0011). Следующий — общий слой PostgreSQL.

Client projects (`telcoss`, `pamyat-naroda-graph`, сам `basic-infra`) имеют
**несвязанные доменные модели**: telcoss — NetCracker-подобный инвентарь с
GIS (PostGIS), pamyat-naroda — генеалогический граф. Им нужна реляционная
БД с PostGIS, переносимость local↔cloud только через конфигурацию, и
сильная изоляция друг от друга.

`tenant` в платформе = client project (определение общее со storage и
observability).

---

## Решение

### 1. Модель изоляции — database-per-client-project

Каждый client project получает **отдельную БД** на инстансе PostgreSQL.

Отвергнутые альтернативы:

- **schema-per-tenant** — общий failure domain (один инстанс/БД на всех),
  миграции сцеплены, сложнее переносить отдельный проект в cloud. При
  несвязанных доменных моделях выгода (экономия на инстансах) не
  оправдывает потерю изоляции.
- **shared schema + row-level (tenant_id / RLS)** — бессмысленно при
  разных схемах проектов; мешает PostGIS-моделям telcoss; ненужная
  связанность.

Выгоды database-per-client-project:

- сильная изоляция (отдельные права, отдельный failure domain);
- provider portability — БД переезжает local→cloud целиком;
- независимые Alembic-миграции у каждого проекта;
- простой per-project dump/restore/backup.

### 2. Control plane / data plane разделены

- **Control plane** (`postgres/` — `PostgresPort` + `LocalAdapter` +
  `ManagedAdapter` + `cli`): provisioning БД, выдача DSN, health.
  Короткоживущие admin-операции при bootstrap/деплое. Держит admin-креды.
- **Data plane** (SDK `basic_infra_postgres_client`): tenant-scoped async/
  sync engine, session-фабрики, health. Client project импортирует только
  это; admin-кред не имеет.

Платформа даёт **connection/engine, не доменные схемы**. Hexagonal-граница
сохранена: платформенный слой не импортирует домен проекта. Alembic-миграции
и ORM-модели принадлежат client project.

### 3. Имя БД выводится из tenant детерминированно

`telcoss → telcoss`, `pamyat-naroda-graph → pamyat_naroda_graph` (дефисы →
подчёркивания, валидация под правила идентификаторов PostgreSQL, ≤ 63).

### 4. PostGIS — первоклассный

Образ `postgis/postgis:16-3.4`. PostGIS предзагружается в `template1`
(init-скрипт) и идемпотентно гарантируется `provision` (`CREATE EXTENSION
IF NOT EXISTS`) — последнее покрывает managed-инстансы без init-скрипта.

### 5. Provider portability

`BASIC_INFRA_POSTGRES_PROVIDER=local|managed`. Переключение — только через
env, без изменения кода. `ManagedAdapter` на Week 8 — частичный (см. Out of
scope).

---

## Config

SDK читает env vars с префиксом `BASIC_INFRA_POSTGRES_`:

```
BASIC_INFRA_POSTGRES_TENANT=telcoss
BASIC_INFRA_POSTGRES_ENV=dev
BASIC_INFRA_POSTGRES_PROVIDER=local
BASIC_INFRA_POSTGRES_HOST=localhost
BASIC_INFRA_POSTGRES_PORT=5434
BASIC_INFRA_POSTGRES_USER=app
BASIC_INFRA_POSTGRES_PASSWORD=...
```

Control plane (provisioning) читает отдельные admin-переменные
`POSTGRES_MULTI_*` (host/port/admin_user/admin_password) — client projects
их не получают.

> **`ENV` vs `BASIC_INFRA_POSTGRES_ENV`.** Тот же осознанный split, что в
> observability (ADR-0011 §Config): `ENV` — глобальный контекст платформы
> (compose labels), `BASIC_INFRA_POSTGRES_ENV` — SDK-namespaced. При деплое
> оба совпадают.

---

## Coexistence (переходный период)

telcoss держит собственный PostgreSQL на **5433**. postgres-multi публикуется
на **127.0.0.1:5434** — оба инстанса сосуществуют на vams-dev. Контейнерный
порт неизменен (5432 внутри `basic-infra-net`); смещена только host-публикация.

Adoption telcoss → Week 12: telcoss переносит схемы на postgres-multi БД
(`telcoss`), собственный postgres telcoss останавливается. Канонизация порта
(если потребуется) — отдельным `.env` override, как в observability-cutover.

---

## Out of scope (отложено)

- **ManagedAdapter.provision/deprovision** — stub. Managed-БД создаются вне
  приложения (Terraform/консоль провайдера). `dsn`/`health`/`exists`
  работают уже сейчас. Полная реализация — когда появится cloud-таргет.
- **PgBouncer / внешний pooling** — SQLAlchemy-пул достаточен для текущего
  масштаба. Отдельный ADR при появлении HA/cloud-нагрузки.
- **Per-tenant роли с гранулярными правами** — на Week 8 provision создаёт
  БД + PostGIS; SDK подключается под configured user. Hardening ролей —
  follow-up (рассмотреть в Week 12 adoption).
- **HA / реплики / PITR** — single instance per environment, как
  observability. При появлении SLA — отдельный ADR.

---

## Последствия

- Новый client project требует явного `provision` перед первым подключением
  (`make provision TENANT=<name>`). Это сознательный gate, не автосоздание.
- Резервное копирование становится per-project — проще точечно, но требует
  перечисления проектов (нет «одного дампа на всё»).
- Cloud-миграция отдельного проекта не затрагивает остальные.
