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
LINT_PATHS      := storage sdk observability
TYPECHECK_PATHS := storage \
                   sdk/basic_infra_storage_client/basic_infra_storage_client \
                   sdk/basic_infra_observability_client/basic_infra_observability_client

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

# ─── Operational ────────────────────────────────────────────────────────────

.PHONY: models-migrate
models-migrate:
	bash scripts/migrate-models-from-pamyat.sh
