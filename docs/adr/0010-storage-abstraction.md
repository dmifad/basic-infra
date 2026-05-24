# ADR-0010: Абстракция хранилища блобов (MinIO/S3)

**Статус:** Принято
**Дата:** 2026-05-23
**Связанные ADR:** 0001 (Platform Charter), 0009 (Regulatory extraction safeguards — гейт OPEN)

---

## Контекст

На момент Week 6 в экосистеме нет общей абстракции хранилища блобов:

- `telcoss/pdf-intake` пишет файлы напрямую в `/var/telcoss/pdf-intake/` через host-volume mount.
- Других потребителей блобов сегодня нет, но скоро появятся: M&A dossier publication, Wiki BC (артефакты страниц), Audit BC (доказательная база), Field Worker BC.
- `pamyat-naroda-graph` пока не нуждается в блоб-хранилище, но к моменту его реактивации SDK уже должен существовать.

Текущая раскладка имеет три проблемы:

1. **Горизонтальное масштабирование.** Host-volume привязывает pdf-intake к конкретной машине.
2. **Облако.** Невозможно перенести в managed-окружение без переписывания путей в коде.
3. **Мультитенантность.** Сегодня платформа однотенантна по факту. Для миграции на модель «один basic-infra обслуживает несколько клиентских проектов» нужна явная изоляция данных.

## Решение

Вводится порт `BlobStorePort` в basic-infra с тремя реализациями: MinIO, AWS S3, локальная файловая система. SDK `basic_infra_storage_client` распространяет адаптеры клиентским репозиториям так же, как `vams_llm_client` распространяет клиента LLM-шлюза.

### Ключевые решения

#### 1. SDK-distributed, без gateway-сервиса

`vams_llm_client` ходит в gateway-сервис, потому что у LLM-шлюза есть платформенная ценность на уровне запроса: маршрутизация моделей, multi-provider fallback, observability, квоты.

Для блобов ни одно из этих свойств не релевантно на уровне запроса:

- Маршрутизация — на уровне окружения (dev → MinIO, prod → S3), а не запроса.
- Failover — не типичная схема для блобов.
- Observability — реализуется в SDK через structlog/OpenTelemetry hooks.
- Авторизация — per-tenant credentials, передаются в SDK при инициализации.

**Платформенный принцип:** платформенные заботы на уровне запроса получают gateway; прозрачная инфраструктура — SDK. Хранилище — на стороне SDK.

#### 2. Изоляция тенантов через префикс ключа

Один bucket на окружение (`basic-infra-dev`, `basic-infra-staging`, `basic-infra-prod`). Внутри bucket'а раскладка `{tenant_id}/{logical_key}`.

Альтернатива — bucket-per-tenant — рассматривалась и отвергнута:

- Создание bucket'ов требует административных путей, плохо композирующихся с deploy-time конфигурацией.
- Per-tenant retention/lifecycle выражаются через prefix-scoped правила.
- IAM проще: один target, не N.

Безопасность от cross-tenant утечек обеспечивается на уровне адаптера: `tenant_id` — первоклассный аргумент всех методов порта, никогда не вкладывается в `key` вызывающим кодом. Адаптер сам конструирует итоговый объектный ключ. Клиентский код физически не может пересечь границу тенанта.

К bucket-per-tenant возвращаемся только когда появится клиент с требованием «свой AWS-аккаунт» или «свой KMS-ключ». В этот момент вводится `TenantAwareBlobStore`-фабрика, диспатчащая в разные конкретные адаптеры per-tenant. Сейчас — преждевременно.

#### 3. Определение тенанта

`tenant ≡ клиентский проект`:

- `telcoss`
- `pamyat-naroda-graph`
- будущие клиентские проекты

Это определение **платформенное**, не storage-specific. Оно переиспользуется в `postgres-multi` (одна БД на тенанта) и `redis-shared` (префикс ключей по тенанту), которые приходят следующими в Week 6.

#### 4. Минимальный набор операций порта

Порт фиксирует только верby, которые нужны текущим и обозримым потребителям:

- `put`, `get`, `delete` — базовые CRUD.
- `head` — проверка существования и метаданные без скачивания.
- `list` — итерация по префиксу.
- `presigned_url` — выдача временных URL для GET и PUT (нужно для M&A dossier publication, чтобы внешние подписанты могли скачать файл без проксирования через telcoss).

Сознательно **не входит** в первую версию:

- Multipart upload — все текущие блобы укладываются в один PUT (PDF до ~50 МБ).
- Server-side copy — нет use case.
- Bucket-level operations — управляется через infra, не через runtime.
- Версионирование — bucket-level настройка, не runtime concern.

#### 5. Streaming I/O

`BlobData` экспонирует и `.stream() -> AsyncIterator[bytes]`, и `.bytes() -> bytes`. pdf-intake работает с многомегабайтными PDF, и buffer-everything API съест память на высокой параллельности. По умолчанию `.stream()` — рекомендуемый путь для всех потребителей кроме мелких метаданных.

### Архитектура

```
~/basic-infra/
├── storage/
│   ├── ports/
│   │   ├── blob_store.py        # BlobStorePort, BlobRef, BlobData, BlobMetadata
│   │   └── exceptions.py        # BlobNotFound, BlobStoreError, ...
│   ├── adapters/
│   │   ├── filesystem.py        # FilesystemAdapter
│   │   ├── minio.py             # MinioAdapter (S3-compatible через aiobotocore)
│   │   └── s3.py                # S3Adapter (AWS S3 через aiobotocore)
│   └── compose/
│       └── minio.yml            # docker compose profile для локального MinIO
├── sdk/
│   └── basic_infra_storage_client/
│       ├── pyproject.toml
│       └── basic_infra_storage_client/
│           ├── client.py        # BlobStoreClient (sync)
│           ├── async_client.py  # AsyncBlobStoreClient
│           └── config.py        # pydantic-settings конфигурация
```

Клиентские репозитории зависят только от SDK-пакета. Прямой импорт `storage.adapters.*` из клиентского кода не предполагается.

### Конфигурация

SDK читает переменные окружения через pydantic-settings:

```
BASIC_INFRA_STORAGE_BACKEND=minio|s3|filesystem
BASIC_INFRA_STORAGE_ENDPOINT_URL=http://minio:9000     # для minio/s3
BASIC_INFRA_STORAGE_BUCKET=basic-infra-dev             # для minio/s3
BASIC_INFRA_STORAGE_ACCESS_KEY=...                     # для minio; для s3 fallback после IAM
BASIC_INFRA_STORAGE_SECRET_KEY=...
BASIC_INFRA_STORAGE_REGION=us-east-1                   # для s3
BASIC_INFRA_STORAGE_FILESYSTEM_ROOT=/var/telcoss/pdf-intake  # для filesystem
```

Выбор бэкенда — environment-level решение. Один и тот же клиентский код работает с любым адаптером.

## Альтернативы

### A1. Blob-storage gateway service в basic-infra

Зеркалит LLM-gateway: отдельный сервис, клиенты ходят по HTTP, gateway проксирует в реальный backend.

Отвергнуто:
- Нет платформенной ценности на уровне запроса (см. выше).
- Удваивает сетевой hop без выгоды.
- Усложняет presigned-URL поток (gateway не может выдать presigned URL для S3 напрямую без сложной schemы делегирования).

### A2. Bucket-per-tenant

Каждому тенанту — свой bucket.

Отвергнуто на текущем этапе:
- Требует административных IAM-операций при онбординге тенанта.
- Bucket name globally unique в AWS — нужно решать коллизии и naming convention поверх tenant_id.
- На текущем масштабе (1-3 тенанта) overkill.
- К нему можно вернуться без breaking change в SDK: интерфейс порта останется тем же, изменится лишь конкретная реализация.

### A3. Прямое использование `aiobotocore`/`minio` в каждом клиентском проекте

Отвергнуто:
- Дублирование конфигурационного и аутентификационного кода.
- Cross-tenant изоляцию пришлось бы повторять в каждом репо.
- Невозможно централизованно менять backend (S3 → GCS, MinIO → Ceph).

### A4. Content-addressed storage (CAS) поверх блобов

Хранить блобы по hash содержимого, не по логическому ключу. Дедупликация «бесплатно».

Отвергнуто: out of scope. Имеет смысл для Wiki BC (одинаковые изображения на разных страницах) и Audit BC (одинаковые приложения к разным заявкам), но требует отдельного слоя поверх блоб-порта. Возможен будущий ADR.

## Последствия

### Положительные

- pdf-intake перестаёт быть привязан к конкретной машине.
- Появляется путь в облако без рефакторинга прикладного кода.
- Зафиксировано платформенное определение тенанта, переиспользуется в postgres-multi и redis-shared.
- M&A dossier publication получает presigned-URL flow «из коробки».

### Отрицательные

- Появляется второй inter-repo SDK после `vams_llm_client`. Версионирование и совместимость придётся поддерживать.
- Host-volume mounts для pdf-intake становятся deprecated; в прод требуется либо S3-доступ, либо развёрнутый MinIO.
- Локальный dev-цикл усложняется на один контейнер (MinIO).

### Нейтральные

- Миграция pdf-intake — отдельный многофазный процесс (см. `docs/runbooks/pdf-intake-storage-migration.md`). Не часть Week 6.
- Тенантная модель потребует синхронного развёртывания с `postgres-multi` для консистентной семантики `tenant_id` по всей платформе.

## Связанные документы

- `docs/runbooks/pdf-intake-storage-migration.md` — пошаговая миграция pdf-intake с host-filesystem на BlobStore.
- ADR-0001 — Platform Charter, определяет границы basic-infra.
- ADR-0009 — Regulatory extraction safeguards, контекст состояния compliance BC на момент принятия этого ADR (gate OPEN, deferred).

## Открытые вопросы (на будущие сессии)

- **Lifecycle policies.** Сейчас хранилище не управляет retention. Когда появится требование (compliance audit trail, GDPR-подобные сценарии) — отдельный ADR.
- **Replication между регионами.** Out of scope, поднимается при появлении SLA-требований.
- **CAS поверх блобов.** См. A4.
- **Tenant onboarding workflow.** Сейчас тенант — просто строка в конфиге. По мере роста потребуется явный процесс (валидация, квоты, billing hooks).
