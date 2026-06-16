# Runbook: операции с observability stack

**Контекст:** ADR-0011 ввёл observability foundations в basic-infra
(Prometheus + Loki + Promtail + Grafana). Этот runbook — операционные
процедуры.

**Цель:** дать чёткие шаги для старта/остановки стека, доступа к UI,
управления retention, и базовое troubleshooting.

---

## Старт

```bash
cd ~/basic-infra
docker compose --profile observability up -d
```

Дождаться healthy:

```bash
docker compose ps prometheus loki promtail grafana
# Все статус "healthy" — стек готов.
```

Ожидаемое время старта: ~30 секунд (Loki разогревается дольше всех).

## Доступ к UI

В переходный период (Week 7-10) платформенный стек на смещённых портах,
чтобы не конфликтовать с telcoss observability (см. ADR-0011 §7):

| Компонент | URL (переходный) | URL (после cutover, Week 11) | Логин |
|---|---|---|---|
| Grafana | http://localhost:3002 | http://localhost:3000 | `admin` / `admin` (см. `.env`) |
| Prometheus | http://localhost:9190 | http://localhost:9090 | — |
| Loki | http://localhost:3110 (API only) | http://localhost:3100 | — |

Порты задаются в `.env` корня basic-infra (`PROMETHEUS_PORT`, `LOKI_PORT`,
`GRAFANA_PORT`). Все биндятся на `127.0.0.1` — наружу не торчат.

Сразу после старта Grafana уже сконфигурирована:

- Datasources: Prometheus + Loki провижионы.
- Dashboard: «basic-infra overview» в папке `basic-infra`.

## Остановка

```bash
docker compose --profile observability down
```

Volumes сохраняются (метрики и логи переживут перезапуск). Полная очистка:

```bash
docker compose --profile observability down -v
```

⚠ Удаляет всю историю метрик и логов в dev. В prod — не делать.

## Retention

| Компонент | Текущий retention | Где менять |
|---|---|---|
| Prometheus | 14 дней | `observability/compose/observability.yml` → `--storage.tsdb.retention.time` |
| Loki | 14 дней (336h) | `observability/loki/loki.yml` → `limits_config.retention_period` |
| Grafana | бесконечно (только сам конфиг) | — |

Изменение retention требует рестарта компонента. Старые данные за пределами
нового окна удаляются в течение следующего compactor cycle (~2 часа для Loki).

## Дашборды

### Чтобы добавить дашборд

1. Создать или экспортировать JSON в Grafana UI.
2. Положить в `observability/grafana/dashboards/<имя>.json`.
3. Закоммитить.
4. Перезапустить Grafana (или подождать 30 сек — провижионинг периодически
   перечитывает каталог).

### Чтобы изменить дашборд

UI-правки **теряются** при рестарте (`allowUiUpdates: false` в провижионинге).
Изменения идут через правку JSON в репо и PR.

## Adoption нового сервиса

Минимум для того чтобы сервис попал в observability:

1. **Логи (Promtail подхватывает автоматически)** — добавить в compose-файл
   контейнера лейблы:

   ```yaml
   labels:
     basic-infra.observability.logs: "true"
     basic-infra.observability.service: "<service-name>"
     basic-infra.observability.env: "${ENV:-dev}"
     basic-infra.observability.tenant: "<tenant>"  # опционально
   ```

2. **Метрики** — сервис в коде:

   ```python
   from basic_infra_observability_client import (
       ObservabilitySettings, setup_logging, setup_metrics, get_logger,
   )
   settings = ObservabilitySettings()
   setup_logging(settings)
   setup_metrics(settings)  # запускает /metrics на 9090
   ```

   Затем раскомментировать соответствующий блок в
   `observability/prometheus/prometheus.yml` (или дождаться Docker SD
   автодискавери — см. п. 3).

3. **Автодискавери (опционально)** — добавить в compose:

   ```yaml
   labels:
     basic-infra.observability.scrape: "true"
     basic-infra.observability.port: "9090"
   ```

   Prometheus автоматически добавит сервис в scrape targets (требует
   раскомментировать Docker SD блок в `prometheus.yml`).

## Troubleshooting

### Grafana показывает «No data»

1. Проверить, что сервис экспонирует `/metrics`:
   `curl http://<service>:9090/metrics`
2. Проверить, что Prometheus видит target:
   http://localhost:9090/targets — статус должен быть `UP`.
3. Проверить scrape config: `observability/prometheus/prometheus.yml`.

### Логи сервиса не появляются в Loki

1. Проверить, что контейнер имеет лейбл
   `basic-infra.observability.logs: "true"`:
   `docker inspect <container> | grep basic-infra.observability`
2. Проверить, что Promtail видит контейнер:
   `docker compose logs promtail | grep <service-name>`
3. Проверить, что Loki принимает данные:
   `docker compose logs loki | grep -i error`

### Loki не стартует

Чаще всего — несовместимость schema_config с существующим volume.
В dev: удалить volume и перезапустить. В prod: использовать команду
`loki migrate` (отдельная процедура, не входит в этот runbook).

### Метрика не появляется

1. Проверить, что `setup_metrics(settings)` был вызван при старте сервиса.
2. Проверить порт: env var `BASIC_INFRA_OBSERVABILITY_METRICS_PORT` (по
   умолчанию 9090).
3. Прямой запрос: `curl http://<service>:9090/metrics | grep <metric_name>`.
4. Если метрика создана, но `labels()` не вызван — она не появится в
   output (prometheus_client lazy-инициализирует label sets).

## Cutover с telcoss observability (Week 11)

До Week 11 telcoss держит собственный observability стек
(`~/telcoss/infra/compose/compose.observability.yml`: prometheus 9090,
grafana 3001, loki 3100, promtail, redis-exporter, postgres-exporter).
Платформенный стек его заменяет. Процедура cutover — отдельная adoption-
сессия в `~/telcoss/`, кратко:

1. Telcoss-сервисы адаптируют `basic_infra_observability_client`
   (logging + metrics).
2. redis-exporter / postgres-exporter переносятся в основную композицию
   telcoss (или basic-infra), скрейпятся платформенным Prometheus —
   раскомментировать соответствующий job в `prometheus.yml`.
3. Telcoss-овские дашборды экспортируются и переносятся в
   `observability/grafana/dashboards/`.
4. `compose.observability.yml` в telcoss удаляется.
5. Платформенный стек переключается на канонические порты: в `.env`
   корня basic-infra `PROMETHEUS_PORT=9090`, `LOKI_PORT=3100`,
   `GRAFANA_PORT=3000`. Рестарт стека.
6. ADR-0011 обновляется: «cutover завершён YYYY-MM-DD».

До завершения cutover **не запускайте оба стека на одних портах** —
переходные порты (9190/3110/3002) специально разведены, чтобы telcoss и
basic-infra observability могли работать одновременно.

## Что НЕ покрыто этим runbook

- **Алертинг** — отдельный ADR, отдельный runbook. Сначала наблюдаем
  baseline 2-4 недели после adoption, потом строим правила.
- **HA / federation** — отдельный ADR, появится при SLA-требованиях.
- **Tracing** — отдельный ADR (планируется 0012).
- **Backup observability data** — Prometheus и Loki в локальных volume;
  бэкап = бэкап volume. В prod рассматривать S3-backed Loki через
  `basic_infra_storage_client`.
- **Multi-environment Grafana** — пока один Grafana per env. Если
  захочется централизованный Grafana, читающий из нескольких Prometheus/Loki —
  отдельная задача.
