# SwarmScout Makefile
#
# One command per task. Designed so someone new to the project can read
# `make help` and know exactly what to run, without memorising the specific
# pytest / pnpm / forge invocations.
#
# Usage:
#   make help            — list every target with its one-line description
#   make install         — install everything needed to develop locally
#   make test            — run every test suite (Python, web, contracts)
#   make lint            — run every linter in check mode
#   make format          — fix every formatter-owned issue
#   make smoke           — hit the running API + dashboard with smoke_test.sh
#
# Conventions:
# - Every target is .PHONY unless it produces a file artefact.
# - Environment variables are read from .env when present; see .env.example.

.DEFAULT_GOAL := help
SHELL := /usr/bin/env bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c

# Colours for pretty help output.
BLUE   := \033[0;34m
GREEN  := \033[0;32m
YELLOW := \033[0;33m
NC     := \033[0m

# ---------------------------------------------------------------- meta

.PHONY: help
help: ## Show this help
	@echo ""
	@echo "$(BLUE)SwarmScout — make targets$(NC)"
	@echo ""
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

# ---------------------------------------------------------------- install

.PHONY: install
install: install-python install-web install-contracts install-hooks ## Install everything (python, web, contracts, pre-commit)

.PHONY: install-python
install-python: ## pip install with dev extras
	python -m pip install --upgrade pip
	pip install -e ".[dev]"

.PHONY: install-web
install-web: ## pnpm install in web/
	cd web && pnpm install --no-frozen-lockfile

.PHONY: install-contracts
install-contracts: ## Install forge-std submodule
	git submodule update --init --recursive
	cd contracts && forge install --no-commit || true

.PHONY: install-hooks
install-hooks: ## Install pre-commit hooks
	pre-commit install

# ---------------------------------------------------------------- services

.PHONY: up
up: ## Start Redis + Postgres (no agents)
	docker compose up -d redis postgres

.PHONY: up-all
up-all: ## Start the full stack (all agents, API, bot, web)
	docker compose up -d

.PHONY: down
down: ## Stop the whole compose stack (keeps volumes)
	docker compose down

.PHONY: nuke
nuke: ## Stop the stack AND delete all data volumes (irreversible)
	@read -p "This will delete Redis + Postgres data. Continue? [y/N] " ok
	@if [ "$$ok" = "y" ] || [ "$$ok" = "Y" ]; then \
	  docker compose down -v; \
	else \
	  echo "cancelled"; \
	fi

.PHONY: logs
logs: ## Tail all compose logs
	docker compose logs -f --tail=100

.PHONY: logs-%
logs-%: ## Tail one service, e.g. `make logs-hunter`
	docker compose logs -f --tail=200 $*

.PHONY: restart-%
restart-%: ## Restart one service, e.g. `make restart-bot`
	docker compose restart $*

# ---------------------------------------------------------------- tests

.PHONY: test
test: test-python test-web test-contracts ## Run every test suite

.PHONY: test-python
test-python: ## pytest with 100% coverage gate
	pytest

.PHONY: test-python-fast
test-python-fast: ## pytest without coverage (fast local iteration)
	pytest --no-cov -x

.PHONY: test-web
test-web: ## vitest with coverage gate
	cd web && pnpm test

.PHONY: test-contracts
test-contracts: ## forge test
	cd contracts && forge test -vvv

.PHONY: coverage-python
coverage-python: ## pytest + open HTML coverage report
	pytest --cov-report=html
	@echo "open htmlcov/index.html"

.PHONY: coverage-contracts
coverage-contracts: ## forge coverage report
	cd contracts && forge coverage --report lcov

# ---------------------------------------------------------------- lint + type

.PHONY: lint
lint: lint-python lint-web ## Run every linter in check mode

.PHONY: lint-python
lint-python: ## ruff check + mypy strict
	ruff check .
	ruff format --check .
	mypy agents api bot

.PHONY: lint-web
lint-web: ## biome check + tsc
	cd web && pnpm biome check .
	cd web && pnpm typecheck

.PHONY: format
format: ## Apply every auto-fixer
	ruff check --fix .
	ruff format .
	cd web && pnpm biome format --write .

# ---------------------------------------------------------------- schemas

.PHONY: schemas
schemas: ## Export Pydantic -> JSON Schema -> zod (drift-gate artefacts)
	python scripts/export_schemas.py
	node scripts/generate_zod.ts

# ---------------------------------------------------------------- deploy

.PHONY: deploy-contract
deploy-contract: ## Deploy FindingsRegistry to BNB Testnet (requires $AGENT_WALLET_PRIVATE_KEY)
	cd contracts && forge script script/Deploy.s.sol \
	  --rpc-url bsc_testnet \
	  --broadcast \
	  --private-key $$AGENT_WALLET_PRIVATE_KEY

.PHONY: deploy-vps
deploy-vps: ## Rsync + compose up on the VPS (requires $DEPLOY_HOST, $DEPLOY_USER)
	bash scripts/deploy.sh

.PHONY: seed-wallet
seed-wallet: ## Request testnet BNB for the agent wallet
	bash scripts/seed_testnet_wallet.sh

# ---------------------------------------------------------------- smoke + demo

.PHONY: smoke
smoke: ## Post-deploy smoke test (hits /health, /briefs, /metrics, dashboard)
	bash scripts/smoke_test.sh

.PHONY: demo-video
demo-video: ## Record the 3-minute demo video via Playwright
	bash scripts/record_demo_video.sh

# ---------------------------------------------------------------- ops

.PHONY: status
status: ## Show docker compose ps
	docker compose ps

.PHONY: db-shell
db-shell: ## Open a psql shell on the running Postgres
	docker compose exec postgres psql -U swarmscout

.PHONY: redis-shell
redis-shell: ## Open a redis-cli shell on the running Redis
	docker compose exec redis redis-cli

.PHONY: cost-today
cost-today: ## Tally LLM spend over the last 24 hours
	docker compose exec postgres psql -U swarmscout -c \
	  "SELECT provider, model, COUNT(*), ROUND(SUM(cost_usd)::numeric, 4) AS usd \
	     FROM llm_calls WHERE created_at > NOW() - INTERVAL '24 hours' \
	    GROUP BY 1, 2 ORDER BY 4 DESC;"

# ---------------------------------------------------------------- clean

.PHONY: clean
clean: ## Remove build artefacts but keep dependencies
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml
	rm -rf contracts/cache contracts/out
	cd web && rm -rf .next coverage playwright-report test-results

.PHONY: clean-all
clean-all: clean ## Also remove installed deps (node_modules, .venv)
	rm -rf node_modules .venv
	cd web && rm -rf node_modules
