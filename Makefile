.PHONY: lint lint-backend lint-frontend lint-fix lint-check format format-backend format-frontend test test-backend test-frontend test-integration test-arch test-arch-backend test-arch-frontend dev dev-mock mock-api up down migrate venv openapi openapi-check precommit-install

VENV_DIR := .venv-devlogplus
PYTHON := python3

# ── Environment ──────────────────────────────────────────────────────
venv: ## Create virtual environment and install all dependencies
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_DIR)/bin/pip install --upgrade pip
	$(VENV_DIR)/bin/pip install poetry
	$(VENV_DIR)/bin/poetry install
	@echo ""
	@echo "✅ Virtual environment ready. Activate it with:"
	@echo "   source $(VENV_DIR)/bin/activate"

# ── Linting ──────────────────────────────────────────────────────────
lint: lint-backend lint-frontend ## Run linter and auto-fix issues

lint-backend: ## Lint backend (auto-fix)
	poetry run ruff check --fix backend/
	poetry run ruff format backend/

lint-frontend: ## Lint frontend (auto-fix)
	cd frontend && npm run lint:fix

lint-check: ## Check lint without fixing (CI mode)
	poetry run ruff check backend/
	poetry run ruff format --check backend/
	cd frontend && npm run lint

lint-fix: lint ## Alias for lint

# ── Formatting ───────────────────────────────────────────────────────
format: format-backend format-frontend ## Format code

format-backend: ## Format backend
	poetry run ruff format backend/

format-frontend: ## Format frontend
	cd frontend && npm run format

# ── Testing ──────────────────────────────────────────────────────────
test: test-backend test-frontend ## Run all tests with coverage

test-backend: ## Run backend tests with coverage
	poetry run pytest backend/tests -v --cov=backend/app --cov-report=term-missing --cov-report=html:backend/htmlcov

test-bdd: ## Run only Gherkin BDD tests
	poetry run pytest backend/tests/bdd -v

test-arch: test-arch-backend test-arch-frontend ## Run architecture tests

test-arch-backend: ## Run backend architecture tests
	poetry run pytest backend/tests/test_architecture.py -v

test-arch-frontend: ## Run frontend architecture tests
	cd frontend && npx vitest run src/test/architecture.test.ts

test-frontend: ## Run frontend tests with coverage
	cd frontend && npm run test:coverage

test-integration: openapi ## Run frontend integration tests against Prism mock
	cd frontend && npm run test:integration

# ── Docker ───────────────────────────────────────────────────────────
up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

migrate: ## Run database migrations
	docker compose exec app alembic upgrade head

# ── Development ──────────────────────────────────────────────────────
dev: ## Start dev server locally (no Docker)
	poetry run uvicorn backend.app.main:app --reload --reload-dir backend

dev-mock: openapi ## Start frontend with Prism mock API (no backend needed)
	@echo "═══════════════════════════════════════════════════"
	@echo "  Starting Prism mock server + Vite dev server"
	@echo "  → Prism: http://localhost:4010"
	@echo "  → Vite:  http://localhost:5173"
	@echo "═══════════════════════════════════════════════════"
	@cd frontend && npx prism mock ../docs/openapi.json --host 0.0.0.0 --port 4010 --dynamic & \
		PRISM_PID=$$!; \
		npx wait-on http://localhost:4010 && \
		npx vite --mode mock; \
		kill $$PRISM_PID 2>/dev/null; wait $$PRISM_PID 2>/dev/null

mock-api: openapi ## Start Prism mock server standalone (port 4010)
	cd frontend && npm run mock-api

# ── OpenAPI ──────────────────────────────────────────────────────────
openapi: ## Export OpenAPI spec to docs/openapi.json
	poetry run python scripts/export_openapi.py

openapi-check: ## Verify docs/openapi.json is up to date (CI mode)
	poetry run python scripts/export_openapi.py --check

# ── Git hooks ────────────────────────────────────────────────────────
precommit-install: ## Install pre-commit hooks
	poetry run pre-commit install
	@echo "✅ Pre-commit hooks installed."

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
