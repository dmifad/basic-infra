# basic_infra_redis_client

Data-plane SDK for the basic-infra shared Redis layer (ADR-0014).

Tenant isolation is by **ACL user + key-prefix namespace** on a single Redis
instance (db 0) — not by db number. The control plane (`redis/`) provisions
`app_<tenant>` restricted to `~<namespace>:*`; this SDK connects as that user and
prefixes keys via `RedisSettings.namespacer()`.

```python
from basic_infra_redis_client import create_async_client, get_settings

settings = get_settings()          # env BASIC_INFRA_REDIS_*
ns = settings.namespacer()
r = create_async_client(settings)
await r.set(ns.key("session:42"), "…")   # -> "<namespace>:session:42"
```

Env: `BASIC_INFRA_REDIS_HOST/PORT/USERNAME/PASSWORD/TENANT/SSL/ENV`. `ENV` is the
explicit deployment-env (not the app ENV).
