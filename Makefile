# HAYABUSA — developer entrypoints.
#
# Windows users without `make`: ./make.ps1 <target> exposes the same commands.

COMPOSE := docker compose
BACKEND := cd backend &&
FRONTEND := cd frontend &&

.DEFAULT_GOAL := help
.PHONY: help secrets up down restart build logs ps migrate revision downgrade \
        seed test lint fmt types check shell psql redis-cli clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- bootstrap --

secrets: ## Create .env from .env.example with freshly generated secrets
	@python scripts/gen_secrets.py

# ------------------------------------------------------------------- stack ---

up: ## Build and start the full stack in the background
	$(COMPOSE) up -d --build
	@echo ""
	@echo "  web   -> http://localhost:$${WEB_HOST_PORT:-3000}"
	@echo "  api   -> http://localhost:$${API_HOST_PORT:-8000}/api/docs"

down: ## Stop the stack (volumes preserved)
	$(COMPOSE) down

restart: ## Restart the application services, leaving datastores up
	$(COMPOSE) restart api worker beat web

build: ## Rebuild images without starting
	$(COMPOSE) build

logs: ## Tail logs from all services (make logs S=api for one)
	$(COMPOSE) logs -f --tail=100 $(S)

ps: ## Show service status
	$(COMPOSE) ps

# --------------------------------------------------------------- database ----

migrate: ## Apply all migrations
	$(COMPOSE) run --rm api alembic upgrade head

revision: ## Autogenerate a migration: make revision M="add vendor table"
	$(COMPOSE) run --rm api alembic revision --autogenerate -m "$(M)"

downgrade: ## Roll back one migration
	$(COMPOSE) run --rm api alembic downgrade -1

seed: ## Load curated sources, vendors and demo components
	$(COMPOSE) run --rm api python -m app.seed

psql: ## Open a psql shell on the application database
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-postgres} -d $${POSTGRES_DB:-hayabusa}

redis-cli: ## Open a redis-cli shell
	$(COMPOSE) exec redis redis-cli

# ------------------------------------------------------------------ quality --

test: ## Run the backend test suite
	$(BACKEND) uv run pytest -q

lint: ## Lint backend (ruff + mypy) and frontend (eslint + tsc)
	$(BACKEND) uv run ruff check .
	$(BACKEND) uv run mypy app
	$(FRONTEND) npm run lint
	$(FRONTEND) npm run typecheck

fmt: ## Format backend and frontend sources
	$(BACKEND) uv run ruff format .
	$(BACKEND) uv run ruff check --fix .
	$(FRONTEND) npm run format

check: lint test ## Lint everything, then test

types: ## Regenerate frontend API types from the running API's OpenAPI schema
	$(FRONTEND) npm run types

# --------------------------------------------------------------------- misc --

shell: ## Open a shell in the api container
	$(COMPOSE) exec api bash

clean: ## Stop the stack and delete its volumes (DESTROYS DATA)
	$(COMPOSE) down -v
