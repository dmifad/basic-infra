# basic-infra — Claude Code memory

Платформенный репозиторий экосистемы. Хост для shared инфраструктуры:
LLM gateway, storage layer, observability foundations. По мере роста —
postgres-multi, redis-shared, distributed tracing.
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
  SDK (`vams_llm_client`, `basic_infra_storage_client`, в будущем
  `basic_infra_observability_client`).
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

### 3. Storage SDK contract — frozen после Week 6

`storage/ports/blob_store.py` — публичный контракт `BlobStorePort`.
Любые изменения breaking: ломают будущих adopter'ов. Известный технический
долг — client lifecycle в `_s3_compatible.py.get()` — будет починен в
Week 10 (вместе с pdf-intake adoption), refactor сохраняет совместимость
порта.

### 4. tenant ≡ клиентский проект

Платформенное определение из ADR-0010. Тенантами считаются клиентские
проекты (`telcoss`, `pamyat-naroda-graph`). Это переиспользуется в:

- `storage/` — prefix-based изоляция в едином bucket'е
- `observability/` — лейбл `tenant` в метриках и логах (ADR-0011)
- `postgres-multi` (Week 8) — БД-на-тенанта
- `redis-shared` (Week 9) — префикс ключей по тенанту

При работе с новыми платформенными слоями — сверяйтесь с этим определением.

### 5. Per-backend `timeout_seconds` в `llm/backends.yaml` побеждает env

`BACKEND_REQUEST_TIMEOUT_SECONDS` сам по себе недостаточен — если в
backends.yaml для конкретного backend стоит timeout, он перекрывает env.
Известный lesson learned из reviewer-task сессии. Менять оба
одновременно.

### 6. Observability контракты — frozen после Week 7

Контракт метрик (ADR-0011): имена `snake_case`, prefix по сервису,
стандартные лейблы `service`/`env`/`tenant`, без high-cardinality лейблов
(`request_id`/`user_id`/`document_id` и т.п.).

Контракт логов (ADR-0011): JSON одной строкой, обязательные поля
`timestamp`/`level`/`service`/`env`. `tenant` и `request_id` — авто из
contextvars.

SDK enforce'ит эти контракты: высоко-кардинальные лейблы отвергаются на
этапе `metrics.counter(...)`, `setup_logging` фиксирует формат.

### 7. Observability стек заменяет telcoss-овский — переходные порты

Платформенный observability **заменяет** собственный стек telcoss
(`~/telcoss/infra/compose/compose.observability.yml`). В переходный период
(Week 7-10) оба сосуществуют на `vams-dev`, поэтому платформенный стек
публикуется на смещённых host-портах, биндится на `127.0.0.1`:

- Prometheus `9190` (telcoss держит 9090) → cutover вернёт 9090
- Loki `3110` (telcoss 3100) → cutover вернёт 3100
- Grafana `3002` (telcoss 3001) → cutover вернёт 3000

Cutover — Week 11 (adoption-сессия telcoss). Контейнерные порты внутри
`basic-infra-net` не меняются (9090/3100/3000); смещены только host-публикации
через `PROMETHEUS_PORT`/`LOKI_PORT`/`GRAFANA_PORT` в `.env`.

## Что в репо НЕ относится к basic-infra

Bridge документы (`docs/architecture/bridge-vN.md`) описывают всю
экосистему. Контекст из них про другие репо — **информационный**, не
действующий ограничитель в этом репо:

- **ADR-0009 (regulatory extraction safeguards)** — живёт в `~/telcoss/`,
  не здесь. Любая фраза в bridge типа «gate OPEN» относится к
  ситуации в telcoss, не блокирует работу в basic-infra.
- **Ветка `migrate-to-basic-infra`** — это ветка `~/telcoss/`, не здесь.
  В basic-infra её нет и быть не должно.
- **Compliance prompt iteration** — работа в `~/telcoss/compliance/`,
  не в этом репо.

## Conventions

- **Python:** 3.11+, async-first для I/O-bound кода.
- **Type hints:** strict mypy. Любая публичная функция платформы должна
  быть полностью типизирована.
- **Логирование:** через `basic_infra_observability_client.setup_logging`
  (Week 7). До adoption — structlog напрямую с JSON output.
- **Метрики:** через `basic_infra_observability_client.metrics.*` (Week 7).
  Прямой `prometheus_client.Counter(...)` — антипаттерн, ломает контракт
  стандартных лейблов.
- **Конфигурация:** pydantic-settings, env-prefix per компонент
  (`LLM_*`, `BASIC_INFRA_STORAGE_*`, `BASIC_INFRA_OBSERVABILITY_*`, ...).
- **DI:** не на уровне basic-infra (платформа не имеет своего app-уровня),
  но порядок аргументов конструкторов адаптеров должен быть совместим
  с тем, как клиентские проекты используют `dependency-injector`.
- **Тесты:** pytest + pytest-asyncio. Unit-тесты — без сети.
  Интеграционные — через testcontainers или moto, помечать
  `@pytest.mark.integration`.
- **Compose сеть** называется `basic-infra-net` (не `basic-infra`).
- **Russian-language домен в клиентских проектах НЕ трогать.** Extraction
  prompts в `telcoss/compliance/` написаны на русском намеренно (язык
  source documents). Это load-bearing.

## Карта репозитория (после Week 7)

```
basic-infra/
├── docs/
│   ├── adr/                ← architecture decisions
│   ├── architecture/       ← bridge документы по экосистеме
│   └── runbooks/           ← операционные процедуры
├── llm/                    ← LLM gateway (НЕ ТРОГАТЬ без согласования)
│   ├── compose/
│   └── backends.yaml
├── storage/                ← Week 6: BlobStorePort + adapters + compose
│   ├── ports/
│   ├── adapters/
│   ├── compose/minio.yml
│   └── tests/
├── observability/          ← Week 7: Prometheus + Loki + Grafana + configs
│   ├── compose/observability.yml
│   ├── prometheus/
│   ├── loki/
│   ├── promtail/
│   └── grafana/
├── sdk/
│   ├── vams_llm_client/                          ← LLM SDK
│   ├── basic_infra_storage_client/               ← Storage SDK (Week 6)
│   └── basic_infra_observability_client/         ← Observability SDK (Week 7)
└── docker-compose.yml
```

## Текущая горящая работа

- **Week 7 (в процессе):** observability foundations — `feat/week7-observability` ветка.
- **Week 8 (планируется):** postgres-multi.
- **Week 9 (планируется):** redis-shared.
- **Tracing (Week 7+, планируется):** OTEL + Tempo. Отдельный ADR (0012).
- **Adoption работа** — отдельные сессии в клиентских репо
  (Week 10-12 для telcoss). Не делается в этом репо.

## Антипаттерны (don't section)

- **Не добавлять в basic-infra прикладную логику.** Если возникает
  соблазн «удобнее положить сюда» — это сигнал, что либо это не
  платформенный концепт, либо ему нужен отдельный порт/SDK.
- **Не делать gateway-сервисы для всего.** LLM gateway оправдан per-request
  ценностью. Storage — на стороне SDK (ADR-0010). Observability — тоже SDK
  (ADR-0011). Решение «делать ли gateway» — материал для нового ADR, не
  code-level.
- **Не использовать `prometheus_client.Counter(...)` напрямую** — только
  через `basic_infra_observability_client.metrics.*` (ADR-0011 §SDK enforce).
- **Не вводить новые конфигурационные конвенции на лету.** Все env-prefixы
  и пути инициализации — через ADR или явное согласование.
- **Не запускать `pip install` без `--break-system-packages` или venv.**
  Python 3.12+ PEP 668 enforce'ит это.
- **Не коммитить .env файлы.** Креды в `.env.example` — placeholder.
- **Не добавлять high-cardinality лейблы в метрики.** SDK отвергнёт
  на этапе создания instrument'а, но об этом всё равно нужно помнить.

## Если что-то непонятно

1. Прочитай ADR в `docs/adr/` — там зафиксированы все архитектурные решения.
2. Прочитай runbooks в `docs/runbooks/` — там операционные сценарии.
3. Прочитай последний bridge документ — там текущий state ecosystem.
4. **Не догадывайся о LLM gateway behaviour.** Если задача задевает `llm/` —
   спроси меня перед изменениями.
5. **Если bridge говорит про ADR-0009/migrate-to-basic-infra/compliance —
   это контекст из telcoss, не из этого репо. Не блокируйся на них.**
