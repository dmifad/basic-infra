# Runbook — shared Redis adoption (ADR-0014)

How to stand the shared Redis up and adopt it in a client project (telcoss,
Week 12).

## 1. Host prep (one-time, vams-dev)

NVMe hot-data dir for AOF persistence:

```bash
sudo mkdir -p /home/vams/telcoss-data/redis-shared
# redis:7.2-alpine runs as uid 999 (redis); make /data writable by it:
sudo chown -R 999:999 /home/vams/telcoss-data/redis-shared
```

The ACL directory must be writable by the redis uid too: `ACL SAVE` writes a
temp file in the aclfile's directory and atomic-renames it (so the directory —
not just the file — is bind-mounted, and must be writable by uid 999). Prod:

```bash
sudo chown -R 999:999 redis_shared/acl    # redis owns its aclfile dir; chmod 750
```

Dev shortcut without sudo (works because the redis group matches the dir group):
`chmod 775 redis_shared/acl`. Without this, provisioning fails with
`Opening temp ACL file for ACL SAVE: Permission denied`.

Generate the live ACL file with an admin password before first start. The live
`redis_shared/acl/users.acl` is **git-ignored** (it holds the password; the repo
is public) — only the placeholder `redis_shared/acl/users.acl.example` is tracked.
Generate the live file from the template with:

```bash
make redis-acl-bootstrap
```

Idempotent: no-op if `redis_shared/acl/users.acl` already exists. On a fresh host
it renders the live file from `users.acl.example` and keeps the admin password in
sync with `.env` — reusing `BASIC_INFRA_REDIS_ADMIN_PASSWORD` if already set,
otherwise autogenerating one and appending `BASIC_INFRA_REDIS_ADMIN_USERNAME=admin`
+ `BASIC_INFRA_REDIS_ADMIN_PASSWORD=<generated>` to `.env`. The control plane
(`127.0.0.1:6380`) authenticates as that admin; the two must match.

## 2. Bring it up

```bash
make up-redis-shared        # docker compose up -d redis-shared
docker compose --profile redis-shared config --services | grep redis-shared   # listed
docker compose config --services | grep -q '^redis-shared$' && echo LEAK || echo gated
# liveness (auth-free): PONG or NOAUTH both mean "up"
docker exec <redis-shared-container> redis-cli ping
```

Tear down only this service (NEVER `docker compose down redis-shared` — on
Compose 5.x that tears down the whole project; Week 8 lesson):

```bash
make down-redis-shared      # stop + rm -f redis-shared
```

## 3. Provision a tenant (control plane)

```bash
# repo uses $(VENV)/bin; the SDK must be installed in that venv so the control
# plane can import basic_infra_redis_client (pip install -e sdk/basic_infra_redis_client)
export BASIC_INFRA_REDIS_ADMIN_HOST=127.0.0.1
export BASIC_INFRA_REDIS_ADMIN_PORT=6380
export BASIC_INFRA_REDIS_ADMIN_USERNAME=admin
export BASIC_INFRA_REDIS_ADMIN_PASSWORD=...   # the admin pass from step 1

make redis-provision TENANT=telcoss
# prints username (app_telcoss), a one-time password, namespace, dsn.
# Store the password in the tenant's secrets — it is NOT retrievable later.
```

Deprovision is double-gated (CLI `--confirm` + Makefile `CONFIRM=yes`):

```bash
make redis-deprovision TENANT=telcoss CONFIRM=yes            # remove ACL user
make redis-deprovision TENANT=telcoss CONFIRM=yes PURGE=yes  # + delete namespace keys
```

## 4. Adopt in a client project (telcoss, Week 12)

Path dep (telcoss is poetry):

```toml
[tool.poetry.dependencies]
basic_infra_redis_client = { path = "../basic-infra/sdk/basic_infra_redis_client", develop = true }
```

Env (per tenant):

```bash
BASIC_INFRA_REDIS_HOST=redis-shared        # in-network name; 6379 internal
BASIC_INFRA_REDIS_PORT=6379
BASIC_INFRA_REDIS_TENANT=telcoss
BASIC_INFRA_REDIS_USERNAME=app_telcoss
BASIC_INFRA_REDIS_PASSWORD=...             # from provisioning
BASIC_INFRA_REDIS_ENV=staging              # explicit; not the app ENV
```

Use it (keys auto-namespaced; the ACL enforces the prefix regardless):

```python
from basic_infra_redis_client import create_async_client, get_settings

settings = get_settings()
ns = settings.namespacer()
r = create_async_client(settings)
await r.set(ns.key("session:42"), "…")     # -> telcoss:session:42
```

The client must share the `basic-infra-net` network so `redis-shared` resolves.

## 5. Optional — tie into tracing (ADR-0012)

To get Redis spans correlated with the rest of a request, instrument redis in the
client app:

```python
from opentelemetry.instrumentation.redis import RedisInstrumentor
RedisInstrumentor().instrument()
```

(`opentelemetry-instrumentation-redis` is a consumer-side dep; not part of this
SDK.)

## 6. Cutover note (Week 11/12)

The shifted host port 6380 flips to canonical 6379 with the rest of the stack.
In-network clients are unaffected (they use `redis-shared:6379`).
