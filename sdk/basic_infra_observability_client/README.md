# basic-infra-observability-client

SDK для observability basic-infra. Дистрибутирует:

- `setup_logging` — structlog → JSON в stdout, формат соответствует
  ADR-0011 (`timestamp`, `level`, `service`, `env`, `tenant`, `request_id`).
- `setup_metrics` — `prometheus_client` инициализация и `/metrics`
  HTTP-сервер.
- `metrics.counter / gauge / histogram` — instrument-фабрики с
  автоматическими стандартными лейблами.
- `request_scope`, `tenant_scope` — контекст-менеджеры для request_id и
  tenant override.

См. [ADR-0011](../../docs/adr/0011-observability-foundations.md) для контекста.

## Установка

```bash
pip install "basic-infra-observability-client @ git+https://github.com/<org>/basic-infra.git#subdirectory=sdk/basic_infra_observability_client"
```

## Конфигурация

Через env vars:

```bash
BASIC_INFRA_OBSERVABILITY_SERVICE_NAME=pdf-intake
BASIC_INFRA_OBSERVABILITY_ENV=dev  # SDK-specific; compose-сторона читает ENV (глобальная платформы)
BASIC_INFRA_OBSERVABILITY_TENANT=telcoss
BASIC_INFRA_OBSERVABILITY_METRICS_PORT=9090
BASIC_INFRA_OBSERVABILITY_LOG_LEVEL=INFO
BASIC_INFRA_OBSERVABILITY_LOG_FORMAT=json  # console для dev
```

## Базовая адаптация

```python
from basic_infra_observability_client import (
    ObservabilitySettings,
    setup_logging,
    setup_metrics,
    get_logger,
    metrics,
    request_scope,
)

settings = ObservabilitySettings()
setup_logging(settings)
setup_metrics(settings)   # запускает /metrics на 9090

log = get_logger(__name__)

# Объявление метрик
documents_received = metrics.counter(
    "pdf_intake_documents_received_total",
    "Documents received by pdf-intake",
    labels=["source"],
)

processing_duration = metrics.histogram(
    "pdf_intake_processing_duration_seconds",
    "PDF processing duration",
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
)

# Request lifecycle
def handle_document(doc, source):
    with request_scope() as rid:
        log.info("received", document_id=doc.id, source=source)
        documents_received.labels(source=source).inc()
        # ... обработка ...
```

## Запреты

- **High-cardinality labels** в метриках (request_id, user_id, document_id) —
  отвергаются на этапе создания instrument'а через `ValueError`. Эти
  идентификаторы идут в логи (LogQL поиск), не в метрики.
- **Прямое использование `prometheus_client.Counter/...`** в обход SDK —
  ломает контракт стандартных лейблов. Линтер не отлавливает, но при
  ревью замечается.

## Контракт логов

Каждая запись — JSON одной строкой:

```json
{
  "timestamp": "2026-05-24T11:00:00.123Z",
  "level": "info",
  "service": "pdf-intake",
  "env": "dev",
  "tenant": "telcoss",
  "request_id": "...",
  "event": "document received",
  ...
}
```

`service`, `env`, `tenant`, `request_id` подставляются автоматически —
прикладной код не передаёт их вручную.

## Контракт метрик

- Имена — `snake_case`, prefix по сервису (`pdf_intake_*`,
  `storage_*`, `compliance_*`).
- Стандартные лейблы (`service`, `env`, `tenant`) — добавляются SDK.
- Доп. лейблы — только низкокардинальные перечисления (status,
  source, document_kind).
