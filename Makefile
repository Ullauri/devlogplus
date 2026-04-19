.PHONY: lint lint-backend lint-frontend lint-fix lint-check format format-backend format-frontend test test-backend test-frontend test-integration test-mutation-frontend test-arch test-arch-backend test-arch-frontend run dev dev-mock mock-api up down backup migrate migrate-docker venv openapi openapi-check precommit-install eval eval-e2e eval-topic-extraction eval-profile-update eval-quiz-generation eval-quiz-evaluation eval-reading-generation eval-project-generation eval-project-evaluation mcp

VENV_DIR := .venv-devlogplus
PYTHON := python3

# ── Environment ──────────────────────────────────────────────────────
venv: ## Create virtual environment and install all dependencies
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_DIR)/bin/pip install --upgrade pip
	$(VENV_DIR)/bin/pip install poetry
	$(VENV_DIR)/bin/poetry install
	cd frontend && npm install
	@echo ""
	@echo "✅ Virtual environment ready. Activate it with:"
	@echo "   source $(VENV_DIR)/bin/activate"

# ── Run (native) ─────────────────────────────────────────────────────
run: ## Run the full application natively (build frontend + migrate + serve)
	@echo "═══════════════════════════════════════════════════"
	@echo "  DevLog+ — starting in native mode"
	@echo "═══════════════════════════════════════════════════"
	@echo ""
	@echo "▶ Building frontend…"
	cd frontend && npm run build
	@echo ""
	@echo "▶ Backing up data before migrations…"
	@bash scripts/backup.sh
	@echo ""
	@echo "▶ Running database migrations…"
	poetry run alembic upgrade head
	@echo ""
	@echo "▶ Starting server at http://localhost:8000"
	@echo "  (frontend served from frontend/dist)"
	@echo ""
	poetry run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

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
	$(MAKE) openapi-check

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

test-mutation-frontend: ## Run Stryker mutation tests on frontend (slow — manual only, not CI)
	cd frontend && npx stryker run

# ── Data backup ──────────────────────────────────────────────────────
backup: ## Backup database and workspace/projects to backups/<timestamp>/
	@bash scripts/backup.sh

# ── Database migrations ──────────────────────────────────────────────
migrate: backup ## Run database migrations (creates backup first)
	@echo "▶ Running database migrations…"
	poetry run alembic upgrade head

# ── Docker (development only) ────────────────────────────────────────
#    These targets are intended for local development and CI.
#    For real usage, prefer running natively with `make run`.
# ─────────────────────────────────────────────────────────────────────
up: ## [Dev] Start all Docker services (development only)
	docker compose up -d

down: ## [Dev] Stop all Docker services
	docker compose down

migrate-docker: ## [Dev] Run migrations inside Docker container
	docker compose exec app alembic upgrade head

# ── MCP server ───────────────────────────────────────────────────────
mcp: ## Start the MCP server (stdio transport, for Claude Code)
	poetry run python -m backend.app.mcp_server

# ── Development ──────────────────────────────────────────────────────
dev: ## Start backend dev server locally with hot-reload (no Docker)
	poetry run uvicorn backend.app.main:app --reload --reload-dir backend

dev-mock: openapi ## Start frontend with Prism mock API (no backend needed)
	@echo "═══════════════════════════════════════════════════"
	@echo "  Starting Prism mock server + Vite dev server"
	@echo "  → Prism: http://localhost:4010"
	@echo "  → Vite:  http://localhost:5173"
	@echo "═══════════════════════════════════════════════════"
	@cd frontend && npx prism mock ../docs/openapi.json --host 0.0.0.0 --port 4010 --dynamic --errors & \
		PRISM_PID=$$!; \
		npx wait-on http://localhost:4010 && \
		npx vite --mode mock; \
		kill $$PRISM_PID 2>/dev/null; wait $$PRISM_PID 2>/dev/null

mock-api: openapi ## Start Prism mock server standalone (port 4010)
	cd frontend && npm run mock-api

# ── OpenAPI ──────────────────────────────────────────────────────────
openapi: ## Export OpenAPI spec to docs/openapi.json and regenerate frontend types
	poetry run python scripts/export_openapi.py
	cd frontend && npm run openapi:types

openapi-check: ## Verify docs/openapi.json and frontend types are up to date (CI mode)
	poetry run python scripts/export_openapi.py --check
	cd frontend && npm run openapi:types:check

# ── Node Evaluations (manual only — never run in CI) ─────────────────
#    These targets run LLM accuracy/latency evaluations against
#    OpenRouter. They cost real money and should only be invoked
#    explicitly by a developer.
#
#    Usage:
#      make eval                          # run ALL node evals (default 5 iterations)
#      make eval ITERS=3                   # run ALL with 3 iterations
#      make eval-e2e                       # run full end-to-end userflow eval
#      make eval-e2e ITERS=2               # e2e with 2 iterations
#      make eval-topic-extraction          # run a single node eval
#      make eval-topic-extraction ITERS=10 # single node, 10 iterations
# ─────────────────────────────────────────────────────────────────────
ITERS ?= 3

eval: ## [Manual] Run ALL node evaluations (set ITERS=N to override, default 5)
	@echo "═══════════════════════════════════════════════════"
	@echo "  DevLog+ — Node Evaluation Suite"
	@echo "  Iterations per case: $(ITERS)"
	@echo "═══════════════════════════════════════════════════"
	poetry run python -m backend.scripts.evaluations.run_all --iterations $(ITERS)

eval-e2e: ## [Manual] Run end-to-end userflow evaluation (7 LLM calls per iteration)
	@echo "═══════════════════════════════════════════════════"
	@echo "  DevLog+ — End-to-End Userflow Evaluation"
	@echo "  Iterations per case: $(ITERS)"
	@echo "═══════════════════════════════════════════════════"
	poetry run python -m backend.scripts.evaluations.run_all --e2e --iterations $(ITERS)

eval-topic-extraction: ## [Manual] Evaluate topic_extraction node
	poetry run python -m backend.scripts.evaluations.nodes.eval_topic_extraction --iterations $(ITERS)

eval-profile-update: ## [Manual] Evaluate profile_update node
	poetry run python -m backend.scripts.evaluations.nodes.eval_profile_update --iterations $(ITERS)

eval-quiz-generation: ## [Manual] Evaluate quiz_generation node
	poetry run python -m backend.scripts.evaluations.nodes.eval_quiz_generation --iterations $(ITERS)

eval-quiz-evaluation: ## [Manual] Evaluate quiz_evaluation node
	poetry run python -m backend.scripts.evaluations.nodes.eval_quiz_evaluation --iterations $(ITERS)

eval-reading-generation: ## [Manual] Evaluate reading_generation node
	poetry run python -m backend.scripts.evaluations.nodes.eval_reading_generation --iterations $(ITERS)

eval-project-generation: ## [Manual] Evaluate project_generation node
	poetry run python -m backend.scripts.evaluations.nodes.eval_project_generation --iterations $(ITERS)

eval-project-evaluation: ## [Manual] Evaluate project_evaluation node
	poetry run python -m backend.scripts.evaluations.nodes.eval_project_evaluation --iterations $(ITERS)

# ── Git hooks ────────────────────────────────────────────────────────
precommit-install: ## Install pre-commit hooks
	poetry run pre-commit install
	@echo "✅ Pre-commit hooks installed."

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
