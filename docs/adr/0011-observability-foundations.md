# ADR-0011: Observability foundations (metrics + logs + visualization)

**Статус:** Принято
**Дата:** 2026-05-24
**Связанные ADR:** 0001 (Platform Charter), 0010 (Storage Abstraction — SDK pattern precedent)

---

## Контекст

После Week 6 basic-infra состоит из двух платформенных слоёв (LLM gateway,
storage layer), каждый со своим SDK. По мере роста экосистемы понадобится
ответить на типовые операционные вопросы:

- Кто из клиентов сейчас активен? Какая нагрузка?
- Какие сервисы падают и как часто?
- Какие запросы к LLM gateway медленные?
- Где затыки в pdf-intake pipeline?
- Какой объём хранилища потребляет каждый тенант?

Сегодня единственный способ ответить — `docker compose logs` плюс `grep`.
Это не масштабируется. Требуется observability stack: метрики, логи и
визуализация.

Альтернатива «не строить ничего, разбираться по факту» отвергается:
debugging-долг растёт быстрее, чем инфраструктурный, и однажды попадание
в production-инцидент без observability обходится дороже всей этой работы.

## Решение

Платформа предоставляет **observability foundations**:

1. **Prometheus** — pull-based метрики, scrape `/metrics` endpoints сервисов.
2. **Loki + Promtail** — централизованные логи. Сервисы пишут JSON в stdout,
   Promtail собирает из Docker и шлёт в Loki.
3. **Grafana** — визуализация, провижионинг datasources и dashboards as code.
4. **`basic_infra_observability_client` SDK** — клиентский пакет с
   `setup_logging`, метрик-хелперами и contextvar-инфраструктурой.

Pattern зеркалит ADR-0010 (storage): платформа = compose-профиль + SDK,
adoption — это работа клиентского репозитория, отдельной сессией.

### Ключевые решения

#### 1. Pull-метрики, push-логи

Метрики собираются Prometheus'ом через scrape — сервисы экспонируют
`/metrics` и не знают ничего про Prometheus. Стандартный pull-паттерн,
простой для нестабильных рабочих нагрузок (батч-воркеры, эфемерные
контейнеры — нет; для них push gateway, см. альтернативы).

Логи шлёт Promtail, читая Docker socket. Сервисы пишут JSON в stdout —
им не нужно знать про Loki. Это даёт нулевую связанность приложения с
бэкендом логирования.

#### 2. Multi-tenancy через лейблы, не через отдельные инстансы

Все метрики имеют стандартный набор лейблов:

- `service` — имя сервиса (`pdf-intake`, `compliance-worker`, ...)
- `env` — окружение (`dev` / `staging` / `prod`)
- `tenant` — клиентский проект (`telcoss`, `pamyat`)
- `instance` — id контейнера/пода (заполняется Prometheus автоматически)

Loki получает те же лейблы из Promtail (по Docker container labels или из
JSON-логов через pipeline stages).

Альтернатива — отдельные Prometheus/Loki инстансы per tenant — отвергнута
по тем же причинам, что и bucket-per-tenant в ADR-0010: преждевременная
сложность. Один инстанс per environment, изоляция через label, политики
доступа через Grafana orgs/teams когда понадобится.

#### 3. Single instance per environment

В этом ADR — не HA. Dev/staging/prod каждый получает по одному инстансу
каждого компонента стека. Резервирование, кластеризация, federation — out
of scope, добавятся отдельным ADR когда появится конкретный SLA-driver.

#### 4. Dashboards as code

JSON-дашборды лежат в `observability/grafana/dashboards/` и провижионятся
Grafana при старте. Изменения дашбордов идут через PR, не через UI.

Базовый дашборд `basic-infra-overview.json` — uptime/error rate/log volume
per service. Per-component дашборды (LLM gateway, storage) — добавятся
по мере появления данных.

#### 5. SDK как обязательный путь instrumentation

Сервисы инструментируются исключительно через `basic_infra_observability_client`.
Прямое использование `prometheus_client` или `logging` в клиентских проектах —
антипаттерн.

Это обеспечивает:

- Единый формат логов (JSON, заданный набор полей).
- Единые конвенции лейблов метрик (см. п. 2).
- Единый механизм context propagation (`request_id`, `tenant_id` через
  contextvars).
- Возможность подменить backend без правок в клиентских репо
  (например, перейти с Loki на Vector — точка изменения только в SDK).

#### 6. structlog как logging-фронтенд

structlog уже в vocabulary проекта (выбран в Week 1 для telcoss). SDK
конфигурирует его на JSON output, с фиксированными процессорами для
context binding. stdlib `logging` через `structlog.stdlib.BoundLogger`
для совместимости со стороонними библиотеками.

#### 7. Платформенный стек заменяет per-project observability

На момент Week 7 `~/telcoss/` держит **собственный полный observability
стек** в `infra/compose/compose.observability.yml`: Prometheus (host 9090),
Grafana (3001), Loki (3100), Promtail, плюс redis-exporter и
postgres-exporter. Это временное per-project решение.

Платформенный observability **заменяет** его. Конечное состояние: telcoss
(и другие клиенты) не держат своих Prometheus/Loki/Grafana, а пишут метрики
и логи в единый платформенный стек basic-infra. telcoss-специфичные
экспортёры (redis-exporter, postgres-exporter) переезжают в композицию
клиента, но скрейпятся платформенным Prometheus.

**Переходный период (Week 7 — Week 10):** оба стека сосуществуют на одной
машине `vams-dev`. Чтобы не конфликтовать по host-портам, платформенный
стек публикуется на смещённых портах:

| Сервис | telcoss (existing) | basic-infra (transitional) | basic-infra (после cutover) |
|---|---|---|---|
| Prometheus | 9090 | **9190** | 9090 |
| Loki | 3100 | **3110** | 3100 |
| Grafana | 3001 | **3002** | 3000 |

Все host-порты платформенного стека биндятся на `127.0.0.1` (как telcoss) —
наружу не торчат.

**Cutover (Week 11):** в adoption-сессии telcoss
`compose.observability.yml` удаляется, экспортёры перенаправляются на
платформенный Prometheus, логи — на платформенный Loki. После этого
платформенный стек переключается на канонические порты (9090/3100/3000)
через `.env` override — telcoss-овские порты освобождаются.

Контейнерные (внутрисетевые) порты не меняются: внутри `basic-infra-net`
сервисы общаются по 9090/3100/3000 независимо от host-публикации. Конфликт
существует только на host-уровне, поэтому правится только публикацией.

### Архитектура

```
basic-infra/
├── observability/
│   ├── compose/
│   │   └── observability.yml          ← Prometheus + Loki + Promtail + Grafana
│   ├── prometheus/
│   │   └── prometheus.yml             ← scrape config
│   ├── loki/
│   │   └── loki.yml                   ← Loki config
│   ├── promtail/
│   │   └── promtail.yml               ← Docker log shipping
│   └── grafana/
│       ├── provisioning/
│       │   ├── datasources/           ← Prometheus + Loki datasources
│       │   └── dashboards/            ← dashboard provider config
│       └── dashboards/
│           └── basic-infra-overview.json
└── sdk/
    └── basic_infra_observability_client/
        ├── pyproject.toml
        └── basic_infra_observability_client/
            ├── __init__.py
            ├── config.py              ← pydantic-settings
            ├── logging_setup.py       ← structlog config
            ├── metrics.py             ← prometheus_client helpers
            └── context.py             ← contextvars: request_id, tenant_id
```

### Конфигурация

SDK читает env vars с префиксом `BASIC_INFRA_OBSERVABILITY_`:

```
BASIC_INFRA_OBSERVABILITY_SERVICE_NAME=pdf-intake
BASIC_INFRA_OBSERVABILITY_ENV=dev
BASIC_INFRA_OBSERVABILITY_TENANT=telcoss
BASIC_INFRA_OBSERVABILITY_METRICS_PORT=9090     # порт /metrics endpoint самого сервиса (внутрисетевой)
BASIC_INFRA_OBSERVABILITY_LOG_LEVEL=INFO
BASIC_INFRA_OBSERVABILITY_LOG_FORMAT=json     # json | console (dev)
```

> **`ENV` vs `BASIC_INFRA_OBSERVABILITY_ENV`.**
> Compose-сторона платформы использует глобальную переменную `ENV`
> (labels, Promtail pipeline stages). SDK читает `BASIC_INFRA_OBSERVABILITY_ENV`
> через pydantic-settings prefix — изолированно, без коллизий с хостовым окружением.
> При деплое клиентского сервиса оба значения совпадают — это норма, не дублирование.
> Split осознанный; унификация через `AliasChoices` отклонена (скрытый приоритет).

Host-порты самого стека (в переходный период, см. п. 7) задаются
отдельными переменными в `.env` корня basic-infra:

```
PROMETHEUS_PORT=9190     # cutover → 9090
LOKI_PORT=3110           # cutover → 3100
GRAFANA_PORT=3002        # cutover → 3000
```

`service_name` и `env` обязательны; `tenant` обязателен в multi-tenant
сервисах, необязателен для платформенных компонентов (Prometheus сам
имеет лейбл `service=prometheus`, `tenant` для него не определён).

### Контракт логов

Каждая запись — JSON одной строкой, обязательные поля:

```json
{
  "timestamp": "2026-05-24T11:00:00.123Z",
  "level": "info",
  "logger": "...",
  "service": "pdf-intake",
  "env": "dev",
  "tenant": "telcoss",
  "request_id": "...",
  "event": "...",
  ...
}
```

`request_id` и `tenant` подставляются автоматически из contextvars (если
заданы). Прикладной код не указывает их явно.

### Контракт метрик

Имена метрик — `snake_case`, prefix по сервису:

```
pdf_intake_documents_received_total
pdf_intake_processing_duration_seconds
compliance_extraction_pass_rate
storage_blob_put_total
storage_blob_get_duration_seconds
```

Стандартные лейблы (см. п. 2). Никаких high-cardinality лейблов
(`user_id`, `request_id`) — это контракт-уровневое правило, нарушение
ломает Prometheus.

## Альтернативы

### A1. OpenTelemetry as the single ingest

Отвергнуто на этом этапе — материал отдельного ADR. OTEL даёт unified
ingest для метрик/логов/трейсов, но требует существенно более сложного
коллектора и адаптации существующих сервисов. structlog + prometheus_client
дают 80% ценности за 20% сложности. OTEL добавляется в Week 7+ (tracing) и
там же ставится вопрос о миграции метрик/логов на OTEL collector.

### A2. ELK stack (Elasticsearch + Kibana)

Отвергнуто. Loki значительно дешевле в эксплуатации (label-based индекс
вместо полнотекстового), лучше интегрируется с Grafana, не требует JVM-
тюнинга. ELK имеет преимущества для search-heavy workflow (security,
forensics) — для платформенного observability это излишне.

### A3. Cloud-managed (Datadog, New Relic, Honeycomb)

Отвергнуто на текущем этапе — основная причина self-hosted Prometheus/Loki/Grafana
заключается в том, что они уже работают в той же docker-сети, что и остальные
компоненты экосистемы, и не требуют исходящего сетевого доступа из
закрытых клиентских окружений. Если/когда появится production-deployment с
доступом наружу, cloud-managed переоценивается отдельным ADR.

### A4. Push gateway для всех метрик

Отвергнуто как default. Push gateway имеет смысл для коротко-живущих
батч-задач (cron-jobs, миграционные скрипты). Для long-running сервисов
pull стандартен и проще. Push gateway добавляется при появлении конкретной
необходимости (отдельный compose service, не часть foundations).

### A5. Alertmanager в Week 7

Отвергнуто. Алертинг без зрелых дашбордов и без accumulated signal/noise
baseline даёт ложные срабатывания. Сначала наблюдаем 2-4 недели реальных
данных через адоптированные сервисы, потом строим alerting rules.

## Последствия

### Положительные

- Появляется общая визуализация работы всей экосистемы.
- Adoption-cost минимальный: 3 строки в `main` каждого сервиса плюс
  декларация метрик там, где они нужны.
- Контракт лейблов гарантирует, что dashboards остаются работоспособными
  при добавлении новых сервисов.

### Отрицательные

- Появляется третий inter-repo SDK (после `vams_llm_client` и
  `basic_infra_storage_client`). Версионирование и совместимость придётся
  координировать.
- Docker compose стек растёт на 4 контейнера в локальном dev.
  Ресурсы — несколько сотен MB RAM, незначительно, но не нулевой.
- Сервисам нужно открыть дополнительный порт `/metrics`. Безопасность —
  metrics endpoint должен быть internal-only, не публиковать наружу.

### Нейтральные

- Adoption выполняется в applied track (Week 11), не часть Week 7.
- Tracing откладывается на отдельный ADR (планируется как 0012).

## Связанные документы

- `docs/runbooks/observability-operations.md` — операционные процедуры
  (старт стека, retention, troubleshooting).
- ADR-0001 — Platform Charter.
- ADR-0010 — Storage abstraction (SDK pattern precedent).

## Открытые вопросы (на будущие сессии)

- **Retention policy.** Сейчас Prometheus 14 дней, Loki 14 дней.
  Production может требовать дольше; отдельный ADR при росте.
- **HA.** Single instance per env. При появлении SLA-требований —
  Prometheus federation / Loki в microservices mode / Grafana HA.
- **Alerting.** Через 2-4 недели после adoption — отдельный ADR на
  Alertmanager / Loki rules / on-call policy.
- **Tracing.** OTEL + Tempo, отдельным ADR (0012).
- **Cardinality budget.** Когда сервисов станет больше десятка —
  написать policy по допустимым лейблам и значениям.
- **Cost.** Self-hosted сегодня; cloud-managed переоценивается при
  появлении production-deployment с доступом наружу.
