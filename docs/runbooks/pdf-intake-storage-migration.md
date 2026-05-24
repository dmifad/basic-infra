# Runbook: миграция pdf-intake с host-filesystem на BlobStore

**Контекст:** ADR-0010 вводит абстракцию хранилища блобов в basic-infra.
pdf-intake — единственный текущий потребитель блобов, и сегодня пишет
напрямую в `/var/telcoss/pdf-intake/` через host-volume mount.

**Цель:** перевести pdf-intake на `basic_infra_storage_client.AsyncBlobStoreClient`
без перерыва обслуживания, без big-bang переключения.

**Не цель этого документа:** разворачивать MinIO в production или
переносить данные в AWS. Этим занимаются отдельные операционные
процедуры в момент готовности.

---

## Гарантии

1. **Откат с одной правкой переменной окружения** на любой фазе кроме 6 и 7.
2. **Зеро потерь данных.** На каждом deploy-boundary существует одна
   точка истины для каждого блоба (либо filesystem, либо blob store),
   либо обе синхронизированы через dual-write.
3. **Зеро изменений в прикладной логике pdf-intake** после фазы 1.
   Дальнейшие переключения — конфигурационные.

---

## Фаза 1 — Adoption SDK с FilesystemAdapter

**Цель:** pdf-intake начинает ходить через `AsyncBlobStoreClient` вместо
прямой работы с `pathlib.Path`. Поведение на диске не меняется.

**Изменения:**

- `~/telcoss/pdf-intake/` — заменить прямые `open()` / `Path.write_bytes()`
  на `AsyncBlobStoreClient` вызовы.
- `BASIC_INFRA_STORAGE_BACKEND=filesystem`
- `BASIC_INFRA_STORAGE_FILESYSTEM_ROOT=/var/telcoss/pdf-intake`
- pdf-intake продолжает иметь host-volume mount `/var/telcoss/pdf-intake/`.
- Раскладка на диске после фазы 1:

      /var/telcoss/pdf-intake/telcoss/<existing key paths>/...
                              └─ tenant_id

  Новый уровень `telcoss/` — потому что SDK укладывает блобы как
  `{filesystem_root}/{tenant_id}/{key}`. **Это breaking для существующих
  файлов** — см. подфазу 1a.

### Фаза 1a — Reorganize existing files

Перед deploy с SDK: однократный скрипт, который перемещает существующие
файлы:

```bash
# DRY-RUN
find /var/telcoss/pdf-intake -mindepth 1 -maxdepth 1 -not -name telcoss \
  -exec echo mv {} /var/telcoss/pdf-intake/telcoss/ \;

# APPLY (после ручной верификации)
mkdir -p /var/telcoss/pdf-intake/telcoss
find /var/telcoss/pdf-intake -mindepth 1 -maxdepth 1 -not -name telcoss \
  -exec mv {} /var/telcoss/pdf-intake/telcoss/ \;
```

**Сценарий отката:** перенести файлы обратно (обратная команда),
выкатить предыдущий deploy.

### Verification

- Все существующие PDF читаются через новый код.
- `head` для существующих файлов возвращает корректные `size` и `etag`
  (etag вычисляется лениво из содержимого при первом `head`/`get` —
  см. `FilesystemAdapter._load_meta`).
- Новые загрузки появляются в `/var/telcoss/pdf-intake/telcoss/...`.

**Deploy boundary.** Дальше — только при стабильной работе фазы 1.

---

## Фаза 2 — Switch dev/staging на MinioAdapter

**Цель:** убедиться, что прикладной код работает с MinIO так же, как с ФС.

**Изменения (только dev/staging):**

- Поднять MinIO через `docker compose --profile storage up`.
- `BASIC_INFRA_STORAGE_BACKEND=minio`
- `BASIC_INFRA_STORAGE_BUCKET=basic-infra-dev`
- `BASIC_INFRA_STORAGE_ENDPOINT_URL=http://minio:9000`
- `BASIC_INFRA_STORAGE_ACCESS_KEY=...`
- `BASIC_INFRA_STORAGE_SECRET_KEY=...`
- Production остаётся на filesystem.

### Verification

- Интеграционные тесты pdf-intake проходят на MinIO.
- ETag для нового PUT согласуется (MinIO выдаёт MD5, FilesystemAdapter —
  sha256 — это **известное расхождение**; если код где-то сравнивает
  etag, переделать на content-hash в прикладном слое).
- Производительность приемлема (latency PUT/GET в пределах ~50 ms на
  локальной сети).

**Deploy boundary.** Дальше — только после двух недель стабильной
работы dev/staging на MinIO.

---

## Фаза 3 — Production dual-write

**Цель:** в production адаптер пишет одновременно в filesystem и в MinIO/S3,
читает из filesystem. Это safety net.

**Изменения:**

- Ввести композитный адаптер `DualWriteAdapter` (не входит в Week 6;
  см. ниже «Что нужно построить дополнительно»).
- Production: `BASIC_INFRA_STORAGE_BACKEND=dual_write`
- `DUAL_WRITE_PRIMARY=filesystem` (источник истины при чтении)
- `DUAL_WRITE_SECONDARY=s3` (зеркало)
- Запись: PUT в оба, success при успехе обоих. Расхождение → метрика
  `storage_dual_write_divergence_total`, alert на ненулевое значение.
- Удаление: DELETE из обоих.

### Verification

- Метрика divergence равна нулю на протяжении 7 дней.
- Все новые PDF присутствуют в обеих репликах.

**Deploy boundary.** Дальше — только при стабильной нулевой divergence.

---

## Фаза 4 — Backfill

**Цель:** скопировать существующие файлы из filesystem в MinIO/S3, чтобы
secondary стал полной копией primary.

**Изменения:**

- Скрипт `scripts/backfill_storage.py`:
  - Итерирует `client_fs.list()` (FilesystemAdapter, tenant=telcoss).
  - Для каждого блоба проверяет `client_s3.head()`; если нет — копирует.
  - Считает checksum после копирования; сравнивает с filesystem.
  - Идемпотентен — можно перезапускать.
- Запуск в maintenance window, либо параллельно с dual-write
  (новые файлы dual-write обрабатывает сам, скрипт догоняет старые).

### Verification

- `client_fs.list()` и `client_s3.list()` возвращают одинаковое
  множество ключей.
- Случайная выборка из 100 файлов: bytewise-равенство.

**Deploy boundary.** Дальше — только после полного backfill и совпадения.

---

## Фаза 5 — Reads switch to blob store

**Цель:** primary становится S3. Filesystem продолжает writes как
безопасность.

**Изменения:**

- `DUAL_WRITE_PRIMARY=s3`
- `DUAL_WRITE_SECONDARY=filesystem`

### Verification

- Latency reads приемлема.
- Никаких BlobNotFound на путях, существовавших до миграции.

**Deploy boundary.** Дальше — только после 7 дней стабильной работы.

---

## Фаза 6 — Stop filesystem writes

**Цель:** filesystem становится архивом.

**Изменения:**

- `BASIC_INFRA_STORAGE_BACKEND=s3` (без dual_write обёртки).
- Host-volume mount в compose сохраняется, но read-only.

**Точка невозврата:** после фазы 6 новые блобы не пишутся в filesystem.
Откат на filesystem-only потребует backward backfill (из S3 в ФС).

### Verification

- Через 30 дней после фазы 6 — резервная копия filesystem на cold-storage.
- Затем — удаление host-volume mount.

---

## Фаза 7 — Cleanup

**Цель:** удалить миграционный код.

**Изменения:**

- `DualWriteAdapter` удалён из basic-infra (или перенесён в `experimental/`).
- `FilesystemAdapter` остаётся (используется для dev/tests).
- ADR-0010 обновляется: «миграция pdf-intake завершена YYYY-MM-DD».

---

## Что нужно построить дополнительно (вне Week 6)

- `DualWriteAdapter` — композитный адаптер, оборачивающий два других.
  Не входит в Week 6, потому что преждевременен: до окончания фазы 2
  не нужен. Реализация очевидна (~150 строк, делегирование с метриками).
- Метрика `storage_dual_write_divergence_total` — Prometheus counter,
  инкрементируется при расхождении PUT/DELETE между primary и secondary.
  Зависит от observability layer (Week 7).
- Скрипт `scripts/backfill_storage.py` — пишется на момент фазы 4.

## Контрольный лист откатов

| Фаза | Команда отката |
|---|---|
| 1 | git revert; обратно `mv` файлов в фазе 1a |
| 2 | `BASIC_INFRA_STORAGE_BACKEND=filesystem` (только staging) |
| 3 | `BASIC_INFRA_STORAGE_BACKEND=filesystem` (выключить dual-write) |
| 4 | n/a — backfill идемпотентен, можно прервать |
| 5 | `DUAL_WRITE_PRIMARY=filesystem` |
| 6 | требует backward backfill, не считается тривиальным откатом |
| 7 | git revert (`DualWriteAdapter` восстановим из истории) |
