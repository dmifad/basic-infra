# basic-infra — Makefile
#
# Common operational tasks. Default profile is "basic"; for full LLM stack
# also enable llm-cpu or llm-gpu.

SHELL := /bin/bash
COMPOSE := docker compose
DEFAULT_PROFILE ?= llm-gpu
GATEWAY_HOST_PORT ?= 8003
GATEWAY_URL := http://localhost:$(GATEWAY_HOST_PORT)

# ─── Top-level targets ──────────────────────────────────────────────────────

.PHONY: help
help:
	@echo "basic-infra — targets:"
	@echo "  make up [PROFILE=llm-cpu|llm-gpu]  start gateway + redis + LLM stack"
	@echo "  make down                          stop all services"
	@echo "  make restart                       restart gateway service"
	@echo "  make logs [SERVICE=gateway]        follow logs"
	@echo "  make status                        check /ready"
	@echo "  make tenants-seed                  create telcoss + pamyat-naroda"
	@echo "  make tenants-list                  list all tenants"
	@echo "  make test                          run platform tests (storage + SDKs + observability)"
	@echo "  make test-integration              run integration tests (-m integration, moto S3)"
	@echo "  make lint                          ruff over storage/ sdk/ observability/"
	@echo "  make typecheck                     mypy over storage/ + SDK packages"
	@echo "  make test-gateway                  run LLM gateway tests (poetry)"
	@echo "  make test-sdk                      run vams_llm_client SDK tests (poetry)"
	@echo "  make lint-gateway                  ruff + mypy on gateway + vams SDK (poetry)"
	@echo "  make models-migrate                migrate models from pamyat-naroda"
	@echo "  make build                         rebuild gateway image"

# ─── Lifecycle ──────────────────────────────────────────────────────────────

.PHONY: up
up:
	$(COMPOSE) --profile basic --profile $(DEFAULT_PROFILE) up -d
	@echo
	@echo "basic-infra is up:"
	@echo "  Gateway:      $(GATEWAY_URL)"
	@echo "  Health:       curl $(GATEWAY_URL)/health"
	@echo "  Readiness:    curl $(GATEWAY_URL)/ready"

.PHONY: down
down:
	$(COMPOSE) down

.PHONY: restart
restart:
	$(COMPOSE) restart gateway

.PHONY: build
build:
	$(COMPOSE) build gateway

# ─── Diagnostics ────────────────────────────────────────────────────────────

.PHONY: logs
logs:
	@if [ -n "$(SERVICE)" ]; then \
		$(COMPOSE) logs -f $(SERVICE); \
	else \
		$(COMPOSE) logs -f; \
	fi

.PHONY: status
status:
	@curl -s $(GATEWAY_URL)/ready | jq . || curl -s $(GATEWAY_URL)/ready

# ─── Tenant management ─────────────────────────────────────────────────────

# Seeding runs on the host against the bind-mounted tenant DB (./tenants/),
# so it works whether or not the gateway container is running.
.PHONY: tenants-seed
tenants-seed:
	cd llm/gateway && TENANT_DB_PATH=$(CURDIR)/tenants/tenants.db \
		poetry run python $(CURDIR)/scripts/seed-tenants.py

.PHONY: tenants-list
tenants-list:
	$(COMPOSE) exec gateway python -m app.tenancy.cli tenant list

# ─── Tests & lint (platform layers: storage + SDKs + observability) ─────────

VENV            ?= .venv
PYTEST          := $(VENV)/bin/pytest
RUFF            := $(VENV)/bin/ruff
MYPY            := $(VENV)/bin/mypy
LINT_PATHS      := storage sdk observability postgres redis_shared
TYPECHECK_PATHS := storage \
                   sdk/basic_infra_storage_client/basic_infra_storage_client \
                   sdk/basic_infra_observability_client/basic_infra_observability_client \
                   postgres \
                   sdk/basic_infra_postgres_client/basic_infra_postgres_client \
                   redis_shared \
                   sdk/basic_infra_redis_client/basic_infra_redis_client

.PHONY: dev-install
dev-install:
	$(VENV)/bin/pip install -e ".[dev]"

# Platform-wide tests, run from the existing .venv. No PYTHONPATH prefix
# (resolution comes from root pyproject pythonpath). Integration excluded here.
.PHONY: test
test:
	$(PYTEST) -m "not integration"

.PHONY: test-integration
test-integration:
	$(PYTEST) -m integration

.PHONY: lint
lint:
	$(RUFF) check $(LINT_PATHS)

.PHONY: typecheck
typecheck:
	$(MYPY) $(TYPECHECK_PATHS)

# ─── Tests & lint (LLM gateway / vams SDK: poetry toolchain) ────────────────

.PHONY: test-gateway
test-gateway:
	cd llm/gateway && poetry run pytest

.PHONY: test-sdk
test-sdk:
	cd client-sdks/python && poetry run pytest

.PHONY: test-all
test-all: test test-gateway test-sdk

.PHONY: lint-gateway
lint-gateway:
	cd llm/gateway && poetry run ruff check . && poetry run mypy .
	cd client-sdks/python && poetry run ruff check . && poetry run mypy .

# ─── postgres-multi (ADR-0013) ──────────────────────────────────────────────

.PHONY: up-postgres
up-postgres:  ## поднять только postgres-multi (PostGIS на 127.0.0.1:5434)
	docker compose up -d postgres-multi

.PHONY: down-postgres
down-postgres:  ## остановить postgres-multi
	docker compose stop postgres-multi && docker compose rm -f postgres-multi

.PHONY: provision
provision:  ## provision tenant: make provision TENANT=telcoss
	@test -n "$(TENANT)" || (echo "TENANT не задан: make provision TENANT=<name>" && exit 1)
	PYTHONPATH=. $(VENV)/bin/python -m postgres.cli provision $(TENANT)

# Double-gated: Makefile CONFIRM=yes AND the CLI's own --confirm (rc 2 if
# missing) — matching redis-deprovision, so a tenant DB can't be dropped by a
# bare invocation.
.PHONY: deprovision
deprovision:  ## ОПАСНО: make deprovision TENANT=x CONFIRM=yes
	@test -n "$(TENANT)" || (echo "TENANT не задан" && exit 1)
	@if [ "$(CONFIRM)" != "yes" ]; then \
		echo "refusing: set CONFIRM=yes to deprovision $(TENANT)"; exit 2; \
	fi
	PYTHONPATH=. $(VENV)/bin/python -m postgres.cli deprovision $(TENANT) --confirm

# ─── tracing / Tempo (ADR-0012) ─────────────────────────────────────────────
#
# Compose-only: Tempo has no control-plane CLI (unlike postgres-multi) — it
# provisions nothing per-tenant. Profile-gated under `tracing`.

.PHONY: up-tracing
up-tracing:  ## поднять только Tempo (127.0.0.1:3210/4417/4418). Без Grafana-датасорса — см. up-observability-full
	docker compose up -d tempo

.PHONY: down-tracing
down-tracing:  ## остановить Tempo (stop+rm, НЕ down — down <svc> сносит весь проект)
	docker compose stop tempo && docker compose rm -f tempo

.PHONY: up-observability-full
up-observability-full:  ## observability (Prometheus/Loki/Grafana) + tracing (Tempo) вместе — Tempo datasource резолвится в Grafana
	docker compose --profile observability --profile tracing up -d

# ─── redis-shared (ADR-0014) ────────────────────────────────────────────────
#
# Shared platform Redis, tenant isolation by ACL user + key-namespace. Separate
# from the LLM-stack redis. Profile redis-shared, host port 6380, AOF on NVMe.

.PHONY: redis-acl-bootstrap
redis-acl-bootstrap:  ## сгенерировать git-ignored users.acl из .example (идемпотентно; no-op если уже есть)
	@if [ -f redis_shared/acl/users.acl ]; then \
		echo "redis_shared/acl/users.acl already present — no-op"; \
	else \
		pass=$$(grep -E '^BASIC_INFRA_REDIS_ADMIN_PASSWORD=' .env 2>/dev/null | head -1 | cut -d= -f2-); \
		if [ -z "$$pass" ]; then \
			pass=$$(openssl rand -hex 24); \
			printf '\n# Week 9 redis-shared control-plane admin\nBASIC_INFRA_REDIS_ADMIN_USERNAME=admin\nBASIC_INFRA_REDIS_ADMIN_PASSWORD=%s\n' "$$pass" >> .env; \
			echo "autogenerated admin password -> .env"; \
		else \
			echo "reusing BASIC_INFRA_REDIS_ADMIN_PASSWORD from .env"; \
		fi; \
		sed -e "s/REPLACE_WITH_STRONG_ADMIN_PASSWORD/$$pass/" -e '/^[[:space:]]*#/d' -e '/^[[:space:]]*$$/d' redis_shared/acl/users.acl.example > redis_shared/acl/users.acl; \
		echo "wrote redis_shared/acl/users.acl (redis aclfile rejects # comments — stripped)"; \
	fi

.PHONY: up-redis-shared
up-redis-shared:  ## поднять только shared Redis (127.0.0.1:6380)
	docker compose up -d redis-shared

# NEVER `docker compose down redis-shared` (Week 8: down <svc> сносит весь
# проект на Compose 5.x). stop + rm одного сервиса.
.PHONY: down-redis-shared
down-redis-shared:  ## остановить shared Redis (stop+rm, НЕ down)
	docker compose stop redis-shared && docker compose rm -f redis-shared

# Control-plane CLI uses $(VENV)/bin/python (Week 8 lesson). SDK must be
# installed into $(VENV) so redis_shared can import basic_infra_redis_client.
.PHONY: redis-provision
redis-provision:  ## provision tenant: make redis-provision TENANT=telcoss
	$(VENV)/bin/python -m redis_shared.cli provision --tenant $(TENANT)

# Double-gated: Makefile CONFIRM=yes AND the CLI's own --confirm. PURGE=yes also
# deletes the tenant's namespace keys. The guard postgres deprovision still lacks.
.PHONY: redis-deprovision
redis-deprovision:  ## ОПАСНО: make redis-deprovision TENANT=x CONFIRM=yes [PURGE=yes]
	@if [ "$(CONFIRM)" != "yes" ]; then \
		echo "refusing: set CONFIRM=yes to deprovision $(TENANT)"; exit 2; \
	fi
	$(VENV)/bin/python -m redis_shared.cli deprovision --tenant $(TENANT) --confirm $(if $(filter yes,$(PURGE)),--purge,)

# ─── Operational ────────────────────────────────────────────────────────────

.PHONY: models-migrate
models-migrate:
	bash scripts/migrate-models-from-pamyat.sh
