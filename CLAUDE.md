# basic-infra — Claude Code memory

Платформенный репозиторий экосистемы. Хост для shared инфраструктуры:
LLM gateway, storage layer, в будущем postgres-multi/redis-shared/observability.
Не прикладной код.

## Что это и что НЕ это

**Это:** платформенный слой, переиспользуемый клиентскими проектами
(`telcoss`, `pamyat-naroda-graph`, будущие). Контракты — порты и SDK.
Реализации — адаптеры. Деплоится как набор compose-профилей плюс
дистрибутируемые SDK-пакеты.

**Не это:** прикладная логика, доменные модели клиентов, обработка
конкретных типов документов. Это всё живёт в клиентских репозиториях.

См. `docs/adr/0001-platform-charter.md` для границ платформы.

## Связанные репозитории

- `~/telcoss/` — клиент №1, телеком-аудит. Зависит от basic-infra через
  SDK (`vams_llm_client`, `basic_infra_storage_client`).
- `~/PAMYAT-NARODA-GRAPH/` — клиент №2 (сейчас в паузе, LLM сервисы убраны
  из его compose).

## Жёсткие инварианты

### 1. Репозиторий public

basic-infra **должен оставаться public на GitHub**. Если сделать private —
`actions/checkout@v4` в клиентских репо при default `GITHUB_TOKEN` ломается
(нужен PAT). См. CI `vams_llm_client`.

### 2. LLM platform contract трогать нельзя

`llm/` — production для двух клиентов. Любые изменения контракта
(шапка запросов, формат ответов, имена env переменных
`BACKEND_REQUEST_TIMEOUT_SECONDS` и т.д.) — breaking change и требуют
отдельной согласованной сессии. По умолчанию — read-only.

### 3. `migrate-to-basic-infra` ветка НЕ мержится в `main`

Состояние на момент написания (см. bridge v11):

- `migrate-to-basic-infra` — integration ветка с Weeks 3+4+5.
- `main` — Week 2.
- Гейт ADR-0009 OPEN: regulatory extraction pass rate ~55-62%, target ≥80%.
- Compliance BC extraction structurally complete, но **NOT production-blessed**.

Пока гейт OPEN — `migrate-to-basic-infra → main` запрещено.

### 4. tenant ≡ клиентский проект

Платформенное определение из ADR-0010. Тенантами считаются клиентские
проекты (`telcoss`, `pamyat-naroda-graph`). Это переиспользуется в:

- `storage/` — prefix-based изоляция в едином bucket'е
- `postgres-multi` (будущий) — БД-на-тенанта
- `redis-shared` (будущий) — префикс ключей по тенанту

При работе с новыми платформенными слоями — сверяйтесь с этим определением.

### 5. Per-backend `timeout_seconds` в `llm/backends.yaml` побеждает env

`BACKEND_REQUEST_TIMEOUT_SECONDS` сам по себе недостаточен — если в
backends.yaml для конкретного backend стоит timeout, он перекрывает env.
Это известный lesson learned из reviewer-task сессии. Менять оба
одновременно.

## Conventions

- **Python:** 3.11+, async-first для I/O-bound кода.
- **Type hints:** strict mypy. Любая публичная функция платформы должна
  быть полностью типизирована.
- **Логирование:** structlog, JSON-output в проде.
- **Конфигурация:** pydantic-settings, env-prefix per компонент
  (`LLM_*`, `BASIC_INFRA_STORAGE_*`, ...).
- **DI:** не на уровне basic-infra (платформа не имеет своего app-уровня),
  но порядок аргументов конструкторов адаптеров должен быть совместим
  с тем, как клиентские проекты используют `dependency-injector`.
- **Тесты:** pytest + pytest-asyncio. Unit-тесты адаптеров — без сети.
  Интеграционные — через testcontainers или moto, помечать
  `@pytest.mark.integration`.
- **Russian-language домен в клиентских проектах НЕ трогать.** Extraction
  prompts в `telcoss/compliance/` написаны на русском намеренно (язык
  source documents). Это load-bearing, не case for translation.

## Карта репозитория (после Week 6)

```
basic-infra/
├── docs/
│   ├── adr/                ← architecture decisions
│   └── runbooks/           ← операционные процедуры
├── llm/                    ← LLM gateway (НЕ ТРОГАТЬ без согласования)
│   ├── compose/
│   └── backends.yaml
├── storage/                ← Week 6: BlobStorePort + adapters + compose
│   ├── ports/
│   ├── adapters/
│   ├── compose/minio.yml
│   └── tests/
├── sdk/
│   ├── vams_llm_client/                  ← LLM SDK
│   └── basic_infra_storage_client/       ← Storage SDK (Week 6)
└── docker-compose.yml
```

## Текущая горящая работа

- **Week 6 (в процессе):** storage layer — `feat/week6-storage-layer` ветка.
  postgres-multi и redis-shared — после storage завершён и приземлён.
- **Week 7 (планируется):** observability (Prometheus, Loki, Grafana, tracing).
- **Параллельно (вне номеров недель):** compliance prompt iteration v3+
  в `~/telcoss/` для закрытия гейта ADR-0009. Это **не часть basic-infra
  работы**, не делать в этом репо.

## Антипаттерны (don't section)

- **Не добавлять в basic-infra прикладную логику.** Если возникает
  соблазн «удобнее положить сюда» — это сигнал, что либо это не платформенный
  концепт, либо ему нужен отдельный порт/SDK.
- **Не делать gateway-сервисы для всего.** LLM gateway оправдан per-request
  ценностью. Storage — на стороне SDK (см. ADR-0010 §«SDK vs gateway»).
  Решение «делать ли gateway» — материал для нового ADR, не code-level.
- **Не вводить новые конфигурационные конвенции на лету.** Все env-prefixы
  и пути инициализации — через ADR или явное согласование. Это интерфейс
  для всех клиентских проектов.
- **Не запускать `pip install` без `--break-system-packages` или venv.**
  Python 3.12+ PEP 668 enforce'ит это.
- **Не коммитить .env файлы.** Креды для MinIO в `.env.example` — placeholder,
  не реальные.

## Если что-то непонятно

1. Прочитай ADR в `docs/adr/` — там зафиксированы все архитектурные решения.
2. Прочитай runbooks в `docs/runbooks/` — там операционные сценарии.
3. Прочитай последний bridge документ (если приложен к сессии) — там
   текущий state ecosystem.
4. **Не догадывайся о LLM gateway behaviour.** Если задача задевает `llm/` —
   спроси меня перед изменениями.
