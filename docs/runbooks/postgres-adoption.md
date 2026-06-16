# Runbook — postgres-multi: операции и adoption

Сопровождает ADR-0013. Покрывает запуск слоя, provisioning, health,
backup/restore и план adoption telcoss (Week 12).

## 1. Поднять слой (local dev)

```bash
# сеть basic-infra-net должна существовать (создаётся другими профилями;
# если нет — docker network create basic-infra-net)
make up-postgres                 # PostGIS на 127.0.0.1:5434
docker compose ps postgres-multi # ожидаем healthy
```

## 2. Provision client project

```bash
make provision TENANT=telcoss
# создаёт БД `telcoss` + PostGIS. Идемпотентно — повтор безопасен.
```

Проверка:

```bash
PGPASSWORD=changeme-please psql -h 127.0.0.1 -p 5434 -U postgres -d telcoss \
  -c "SELECT extversion FROM pg_extension WHERE extname='postgis';"
```

## 3. Health из client project (SDK)

```python
from basic_infra_postgres_client import PostgresSettings, check_health
health = await check_health(PostgresSettings(), require_postgis=True)
assert health.ok, health.detail
```

## 4. Backup / restore (per-project)

```bash
# dump
PGPASSWORD=... pg_dump -h 127.0.0.1 -p 5434 -U postgres -Fc telcoss > telcoss.dump
# restore в свежую БД
make provision TENANT=telcoss
PGPASSWORD=... pg_restore -h 127.0.0.1 -p 5434 -U postgres -d telcoss telcoss.dump
```

Хранение дампов — HDD (`/mnt/HDD/telcoss/` posture), как остальные backups.

## 5. Deprovision (деструктивно)

```bash
make deprovision TENANT=telcoss        # требует --force внутри CLI; дропает БД
```

Защищён флагом `allow_destructive`; без него `LocalAdapter.deprovision`
бросает `PermissionError`. Делать только с подтверждённым backup.

## 6. Adoption telcoss (Week 12, non-breaking)

Последовательность (детали — в сессии Week 12):

1. `make provision TENANT=telcoss` на postgres-multi (порт 5434).
2. Прогнать telcoss Alembic-миграции против БД `telcoss` на 5434
   (telcoss владеет своими миграциями — платформа их не трогает).
3. Перенести данные: `pg_dump` со старого telcoss-postgres (5433) →
   `pg_restore` в `telcoss` на 5434. Сверить контрольные суммы/количества.
4. Переключить telcoss-сервисы на SDK `basic_infra_postgres_client`
   (`BASIC_INFRA_POSTGRES_*` в telcoss `.env`), провайдер `local`.
5. Прогнать telcoss test-suite против новой БД.
6. Остановить собственный postgres telcoss (5433). При желании
   канонизировать порт postgres-multi через `.env` override.

Откат: telcoss-сервисы возвращаются на 5433 (старый инстанс не удалять до
подтверждения adoption).

## 7. Provider switch local → managed (будущее)

1. Создать managed-БД вне приложения (Terraform).
2. `BASIC_INFRA_POSTGRES_PROVIDER=managed`, host/port/creds/sslmode в env.
3. Перенести данные (`pg_dump`/`pg_restore`).
4. Код client project не меняется.

> На Week 8 `ManagedAdapter.provision` — stub; шаг 1 выполняется вручную.
