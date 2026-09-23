.DEFAULT_GOAL := help
SHELL := /bin/bash
PY := apps/api/.venv/bin/python
PIP := apps/api/.venv/bin/pip

help: ## Show available commands
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

up: ## Start Postgres + Redis
	docker compose up -d

down: ## Stop local infrastructure
	docker compose down

install: install-api install-web ## Install all dependencies

install-api: ## Create the API virtualenv and install dependencies
	python3 -m venv apps/api/.venv
	$(PIP) install --upgrade pip
	$(PIP) install -e "apps/api[dev]"

install-web: ## Install frontend dependencies
	cd apps/web && npm install

migrate: ## Apply database migrations
	cd apps/api && .venv/bin/alembic upgrade head

api: ## Run the API in development mode
	cd apps/api && .venv/bin/uvicorn app.main:app --reload --port 8000

ingest: ## Refresh due retailer collections once
	cd apps/api && .venv/bin/python -m app.ingest --once

worker: ## Run the dedicated ingestion scheduler
	cd apps/api && .venv/bin/python -m app.ingest

web: ## Run the frontend in development mode
	cd apps/web && npm run dev

test: test-api test-web ## Run all unit/integration tests

test-api: ## Run backend tests
	cd apps/api && .venv/bin/pytest -q

test-web: ## Run frontend unit tests
	cd apps/web && npm run test

test-e2e: ## Run Playwright end-to-end tests
	cd apps/web && npm run test:e2e

lint: ## Lint and type-check everything
	cd apps/api && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd apps/web && npm run lint && npm run typecheck

format: ## Auto-format everything
	cd apps/api && .venv/bin/ruff format . && .venv/bin/ruff check --fix .
	cd apps/web && npm run format

build: ## Production build of the frontend
	cd apps/web && npm run build

verify: lint test build ## Everything CI runs

.PHONY: help up down install install-api install-web migrate api ingest worker web test test-api test-web test-e2e lint format build verify
