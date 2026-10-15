# Common tasks. Run `make help` for the list.
.PHONY: help setup api web worker test lint format e2e check bench

help:
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-8s %s\n", $$1, $$2}'

setup: ## install backend (with embedded Postgres) and frontend dependencies, migrate
	cd backend && uv sync --extra localdb && uv run novelforge migrate
	cd frontend && npm ci

api: ## run the API on :8000 (with an in-process job worker)
	cd backend && uv run novelforge serve --reload

web: ## run the frontend dev server on :5173
	cd frontend && npm run dev

worker: ## run background jobs in a separate process
	cd backend && JOBS_IN_PROCESS=false uv run novelforge worker

lint: ## ruff lint + format check, TypeScript type check
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run -s typecheck

format: ## apply ruff formatting
	cd backend && uv run ruff format .

test: ## backend tests and frontend unit tests
	cd backend && uv run pytest
	cd frontend && npm test

e2e: ## Playwright end-to-end tests (starts its own API and database)
	cd frontend && npm run e2e

check: lint test e2e ## everything CI runs

bench: ## regenerate every benchmark corpus and result (~30 min, CPU)
	bench/run_all.sh
