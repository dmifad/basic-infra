# basic-infra — Makefile
#
# Common operational tasks. Default profile is "basic"; for full LLM stack
# also enable llm-cpu or llm-gpu.

SHELL := /bin/bash
COMPOSE := docker compose
DEFAULT_PROFILE ?= llm-gpu

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
	@echo "  make test                          run gateway tests"
	@echo "  make test-sdk                      run SDK tests"
	@echo "  make lint                          ruff + mypy on gateway + SDK"
	@echo "  make models-migrate                migrate models from pamyat-naroda"
	@echo "  make build                         rebuild gateway image"

# ─── Lifecycle ──────────────────────────────────────────────────────────────

.PHONY: up
up:
	$(COMPOSE) --profile basic --profile $(DEFAULT_PROFILE) up -d
	@echo
	@echo "basic-infra is up:"
	@echo "  Gateway:      http://localhost:8003"
	@echo "  Health:       curl http://localhost:8003/health"
	@echo "  Readiness:    curl http://localhost:8003/ready"

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
	@curl -s http://localhost:8003/ready | jq . || curl -s http://localhost:8003/ready

# ─── Tenant management ─────────────────────────────────────────────────────

.PHONY: tenants-seed
tenants-seed:
	$(COMPOSE) exec gateway python -m scripts.seed_tenants

.PHONY: tenants-list
tenants-list:
	$(COMPOSE) exec gateway basic-infra tenant list

# ─── Tests & lint ──────────────────────────────────────────────────────────

.PHONY: test
test:
	cd llm/gateway && poetry run pytest

.PHONY: test-sdk
test-sdk:
	cd client-sdks/python && poetry run pytest

.PHONY: test-all
test-all: test test-sdk

.PHONY: lint
lint:
	cd llm/gateway && poetry run ruff check . && poetry run mypy .
	cd client-sdks/python && poetry run ruff check . && poetry run mypy .

# ─── Operational ────────────────────────────────────────────────────────────

.PHONY: models-migrate
models-migrate:
	bash scripts/migrate-models-from-pamyat.sh
