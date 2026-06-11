# ============================================================================
# AI Code Assistant — Makefile
# ============================================================================

.PHONY: help build up down restart logs test clean venv

# ── Default target ───────────────────────────────────────────────────────────

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Docker ───────────────────────────────────────────────────────────────────

build:  ## Build the Docker image
	docker compose build

up:  ## Start all services (daemonised)
	cp -n .env.production .env 2>/dev/null || true
	docker compose up -d

down:  ## Stop and remove all services
	docker compose down -v

restart:  ## Restart all services
	docker compose restart

logs:  ## Tail logs from all services
	docker compose logs -f --tail=100

ps:  ## Show running containers
	docker compose ps

shell:  ## Open a shell inside the app container
	docker compose exec app /bin/bash

# ── Local dev (no Docker) ────────────────────────────────────────────────────

venv:  ## Create a local virtualenv
	python -m venv .venv && .venv/bin/pip install -r requirements.txt

dev:  ## Start FastAPI with hot-reload (local)
	REDIS_ENABLED=false python run.py

test:  ## Run the test suite
	REDIS_ENABLED=false python test_graph.py
	REDIS_ENABLED=false python test_stream.py
	REDIS_ENABLED=false python test_mcp.py

clean:  ## Remove bytecode + __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
