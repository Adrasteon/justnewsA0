# JustNews Build System - Unified Makefile
# Phase 2C: Build & CI/CD System Refactoring

.PHONY: help install test lint format clean build deploy docs ci-check release

# Default target
help:
	@echo "JustNews Build System"
	@echo "=========================="
	@echo ""
	@echo "Available targets:"
	@echo "  help        Show this help message"
	@echo "  install     Install dependencies for development"
	@echo "  test        Run test suite with coverage"
	@echo "  lint        Run code quality checks"
	@echo "  format      Format code with consistent style"
	@echo "  clean       Clean build artifacts and cache files"
	@echo "  build       Build production artifacts"
	@echo "  deploy      Deploy to target environment"
	@echo "  docs        Generate and validate documentation"
	@echo "  ci-check    Run CI validation checks"
	@echo "  release     Create and publish release"
	@echo "  deploy-docker       Start JustNews Docker services"
	@echo "  deploy-docker-stop  Stop JustNews Docker services"
	@echo "  deploy-docker-status Show JustNews Docker service status"
	@echo "  deploy-docker-logs  Tail JustNews Docker service logs"
	@echo "  docker-migration-check Report Docker-first cutover compliance status"
	@echo "  monitor-install    Install GPU monitor user unit (local dev)"
	@echo "  monitor-enable     Enable & start GPU monitor service (user)"
	@echo "  monitor-status     Show GPU monitor status"
	@echo "  monitor-tail       Tail GPU monitor log"
	@echo "  monitor-install-rotate   Install logrotate policy (requires sudo)"
	@echo "  alertmanager-install    Install Alertmanager and copy example configs (requires sudo)"
	@echo "  alertmanager-enable     Enable & start Alertmanager (requires sudo)"
	@echo "  alertmanager-disable    Stop and disable Alertmanager (requires sudo)"
	@echo "  alertmanager-status     Show Alertmanager status and API info"
	@echo "  alertmanager-test       Send a test alert to local Alertmanager instance"
	@echo "  monitoring-check        Run Prometheus & Grafana validity checks (pytest tests/monitoring)"
	@echo "  index-build             Build or incrementally refresh local code index"
	@echo "  index-build-full        Force full rebuild of local code index"
	@echo "  index-query             Query local code index (use QUERY='...')"
	@echo "  index-auto-install      Install code index auto-update user service+timer"
	@echo "  index-auto-enable       Enable/start periodic code index timer"
	@echo "  index-auto-disable      Disable/stop periodic code index timer"
	@echo "  index-auto-status       Show code index timer/service status"
	@echo "  index-auto-run-now      Run one immediate autonomous index refresh"
	@echo "  index-bootstrap         Show new-chat index/bootstrap status"
	@echo "  index-bootstrap-json    Write new-chat bootstrap snapshot as JSON"
	@echo "  index-hermes-daily      Run daily Hermes refresh workflow"
	@echo "  index-telemetry-summary Summarize lightweight indexing telemetry"
	@echo "  index-status-report     Show token trend plus index health/daemon status"
	@echo "  index-telemetry-tail    Show recent telemetry events"
	@echo "  hermes-gateway-run      Run Hermes Telegram gateway in container mode"
	@echo "  hermes-stack-status     Show Hermes plus Honcho plus Telegram gateway status"
	@echo ""
	@echo "Environment variables:"
	@echo "  ENV         Target environment (development/staging/production)"
	@echo "  VERSION     Release version (for release target)"
	@echo "  DOCKER_TAG  Docker image tag (for deploy target)"
	@echo "  TELEMETRY_PATH  JSONL path for indexing telemetry events"
	@echo "  BOOTSTRAP_JSON_PATH  Output path for bootstrap JSON snapshot"

# Environment setup
ENV ?= development
VERSION ?= $(shell git describe --tags --abbrev=0 2>/dev/null || echo "v0.1.0")
DOCKER_TAG ?= latest

# Python and tools
# Prefer Python 3.12+ when available; fall back to python3 for non-test targets.
PYTHON ?= $(shell command -v python3.12 >/dev/null 2>&1 && command -v python3.12 || command -v python3)
PIP := $(PYTHON) -m pip
VENV_DIR ?= .venv
VENV_PY := $(VENV_DIR)/bin/python

# Prefer project-local venv only when it satisfies test/runtime minimum (3.12+).
# Otherwise use a discovered 3.12 interpreter when available.
RUN_PY ?= $(shell \
	if [ -x "$(VENV_PY)" ] && "$(VENV_PY)" -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >/dev/null 2>&1; then \
		echo "$(VENV_PY)"; \
	elif command -v python3.12 >/dev/null 2>&1; then \
		command -v python3.12; \
	elif command -v python3 >/dev/null 2>&1; then \
		command -v python3; \
	else \
		echo python3; \
	fi)

# Indexing scripts require repo-specific compatibility; always prefer venv python.
INDEX_PY ?= $(shell \
	if [ -x "$(VENV_PY)" ]; then \
		echo "$(VENV_PY)"; \
	elif command -v python3 >/dev/null 2>&1; then \
		command -v python3; \
	else \
		echo python3; \
	fi)

# Directories
ROOT_DIR := $(shell pwd)
BUILD_DIR := $(ROOT_DIR)/build
DIST_DIR := $(BUILD_DIR)/dist
ARTIFACTS_DIR := $(BUILD_DIR)/artifacts
CONFIG_DIR := $(ROOT_DIR)/config

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

# Helper function for colored output
define log_info
	@echo "$(BLUE)[INFO]$(NC) $(1)"
endef

define log_success
	@echo "$(GREEN)[SUCCESS]$(NC) $(1)"
endef

define log_warning
	@echo "$(YELLOW)[WARNING]$(NC) $(1)"
endef

define log_error
	@echo "$(RED)[ERROR]$(NC) $(1)"
endef

# Installation targets
install: install-deps install-dev
	$(call log_success,"Development environment ready")

install-deps:
	$(call log_info,"Installing Python dependencies...")
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -r requirements.txt
	$(call log_success,"Dependencies installed")

install-dev:
	$(call log_info,"Installing development dependencies...")
	$(PIP) install -e .
	$(call log_success,"Development packages installed")

# Testing targets
DEV_REQUIREMENTS ?= requirements-bootstrap.txt
PYTEST_ALLOW_ANY_ENV ?= 1

test: ensure-dev-tools check-python-version test-unit test-integration
	$(call log_success,"All tests completed")

ensure-dev-tools:
	$(call log_info,"Ensuring required developer tools are available in active environment...")
	@$(RUN_PY) -c "import pytest,ruff,mypy" >/dev/null 2>&1 || { \
		echo "Dev tools missing (pytest/ruff/mypy). Installing minimal toolchain..."; \
		$(RUN_PY) -m pip install pytest pytest-asyncio pytest-cov ruff mypy; \
	}
	$(call log_success,"Developer tools are available")

check-python-version:
	@printf '$(BLUE)[INFO]$(NC) %s\n' "Validating Python runtime for tests (Python 3.12+ required)"
	@$(RUN_PY) -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" || \
		(printf '$(RED)[ERROR]$(NC) %s\n' "Tests require Python 3.12+. Current RUN_PY=$(RUN_PY). Create/use a 3.12 venv (e.g., 'uv python install 3.12 && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements-bootstrap.txt')."; exit 1)
	$(call log_success,"Python runtime is compatible with tests")

# Local pytest wrapper target via project-local UV/venv.
pytest-local:
	$(call log_info,"Running local pytest via scripts/dev/pytest.sh")
	$(shell [ -x ./scripts/dev/run_full_pytest_safe.sh ] || chmod +x ./scripts/dev/run_full_pytest_safe.sh)
	./scripts/dev/run_full_pytest_safe.sh

test-unit:
	$(call log_info,"Running unit tests...")
	ALLOW_ANY_PYTEST_ENV=$(PYTEST_ALLOW_ANY_ENV) $(RUN_PY) -m pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=xml \
		--cov-fail-under=80 -k "not integration" --tb=short
	$(call log_success,"Unit tests passed")

test-integration:
	$(call log_info,"Running integration tests...")
	ALLOW_ANY_PYTEST_ENV=$(PYTEST_ALLOW_ANY_ENV) $(RUN_PY) -m pytest tests/ -v -k "integration" --tb=short
	$(call log_success,"Integration tests passed")

test-performance:
	$(call log_info,"Running performance tests...")
	ALLOW_ANY_PYTEST_ENV=$(PYTEST_ALLOW_ANY_ENV) $(RUN_PY) -m pytest tests/ -v -k "performance" --tb=short --durations=10
	$(call log_success,"Performance tests completed")

# Code quality targets

# Linting includes a check for reintroduced container/orchestration artifacts
# Start with a maintainable baseline scope; use `make lint-full` to audit legacy debt.
LINT_RUFF_PATHS ?= scripts/ci scripts/checks tests/unit
LINT_MYPY_PATHS ?= scripts/ci scripts/checks
LINT_NO_CONTAINERS_PATHS ?= scripts/ci scripts/checks tests/unit
lint: ensure-dev-tools check-processing-time lint-code lint-docs lint-no-containers lint-docker-canonical-runtime
	$(call log_success,"Code quality checks passed")

lint-full: ensure-dev-tools check-processing-time
	$(call log_info,"Running full-repo linting legacy debt audit...")
	ruff check . --fix
	mypy . --ignore-missing-imports
	$(call log_success,"Full-repo linting completed")

# Repo-specific checks
check-processing-time:
	$(call log_info,"Checking processing_time usage patterns...")
	python3 scripts/check_processing_time.py
	$(call log_success,"Processing time checks completed")

lint-code:
	$(call log_info,"Running code linting...")
	ruff check $(LINT_RUFF_PATHS) --fix
	mypy $(LINT_MYPY_PATHS) --ignore-missing-imports
	$(call log_success,"Code linting completed")

lint-docs:
	$(call log_info,"Running documentation checks...")
	$(PYTHON) scripts/ci/enforce_docs_policy.py
	$(call log_success,"Documentation checks passed")

# Repo checks for disallowed container references (fail CI if found)
lint-no-containers:
	$(call log_info,"Checking for disallowed container/orchestration references in code...")
	$(PYTHON) scripts/checks/no_container_refs.py $(LINT_NO_CONTAINERS_PATHS) || (printf '\033[0;31m[ERROR]\033[0m %s\n' "Disallowed container/orchestration references found in lint scope, see output above."; exit 1)
	$(call log_success,"No disallowed container/orchestration references outside allowed folders.")

lint-docker-canonical-runtime:
	$(call log_info,"Checking canonical Docker runtime files for contradictory legacy messaging...")
	$(PYTHON) scripts/checks/docker_canonical_runtime_guard.py
	$(call log_success,"Canonical Docker runtime messaging guard passed")

format:
	$(call log_info,"Formatting code...")
	ruff format .
	$(call log_success,"Code formatting completed")

# Build targets
build: clean build-artifacts
	$(call log_success,"Build completed")

build-artifacts: $(ARTIFACTS_DIR)
	$(call log_info,"Building production artifacts...")
	mkdir -p $(DIST_DIR)
	@if [ -f pyproject.toml ] || [ -f setup.py ]; then \
		$(PYTHON) -m pip wheel . -w $(DIST_DIR)/; \
	else \
		printf '$(YELLOW)[WARNING]$(NC) %s\n' "No root pyproject.toml/setup.py found; skipping wheel build and packaging runtime artifacts only."; \
	fi
	cp requirements.txt $(DIST_DIR)/
	cp requirements-bootstrap.txt $(DIST_DIR)/
	$(call log_info,"Creating artifact archive...")
	cd $(BUILD_DIR) && tar -czf artifacts/justnews-$(VERSION).tar.gz -C dist .
	$(call log_success,"Artifacts built in $(ARTIFACTS_DIR)")

build-containers:
	$(call log_info,"Container artifact build is now Docker-first. Use compose/image workflows for runtime packaging.")
	@echo "No-op: build-containers target retained for compatibility."

$(ARTIFACTS_DIR):
	mkdir -p $(ARTIFACTS_DIR)

# Deployment targets
deploy: deploy-check deploy-$(ENV)
	$(call log_success,"Deployment to $(ENV) completed")

deploy-check:
	$(call log_info,"Running pre-deployment checks...")
	test -f $(CONFIG_DIR)/system_config.json || ($(call log_error,"Config file missing"); exit 1)
	$(PYTHON) -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" || \
			($(call log_error,"Python 3.12+ required"); exit 1)
	$(call log_success,"Pre-deployment checks passed")

deploy-development: deploy-check
	$(call log_info,"Deploying to development environment using Docker (canonical runtime)...")
	$(MAKE) deploy-docker
	$(call log_success,"Development deployment completed (via Docker)")

# Docker-first deployment lifecycle targets
deploy-docker: docker-preflight
	$(call log_info,"Starting JustNews Docker services...")
	bash scripts/ops/docker_compose.sh up
	$(call log_success,"Docker services started")

docker-preflight:
	$(call log_info,"Running Docker runtime preflight checks...")
	bash scripts/ops/docker_preflight.sh
	$(call log_success,"Docker runtime preflight checks passed")

deploy-docker-stop:
	$(call log_info,"Stopping JustNews Docker services...")
	bash scripts/ops/docker_compose.sh down
	$(call log_success,"Docker services stopped")

deploy-docker-status:
	$(call log_info,"Docker service status...")
	bash scripts/ops/docker_compose.sh status

deploy-docker-logs:
	$(call log_info,"Tailing Docker service logs...")
	bash scripts/ops/docker_compose.sh logs

docker-migration-check:
	$(call log_info,"Running Docker-first migration compliance check...")
	bash scripts/ops/docker_first_migration_check.sh

deploy-staging: deploy-check
	$(call log_info,"Deploying to staging environment using Docker (canonical runtime)...")
	$(MAKE) deploy-docker
	$(call log_success,"Staging deployment completed (via Docker)")

deploy-production: deploy-check
	$(call log_info,"Deploying to production environment using Docker (canonical runtime)...")
	$(MAKE) deploy-docker
	$(call log_success,"Production deployment completed (via Docker)")

# Documentation targets
docs: docs-generate docs-validate
	$(call log_success,"Documentation updated")

docs-generate:
	$(call log_info,"Generating API documentation...")
	# Generate OpenAPI/Swagger docs
	$(call log_success,"API documentation generated")

docs-validate:
	$(call log_info,"Validating documentation...")
	$(PYTHON) scripts/ci/enforce_docs_policy.py
	$(call log_success,"Documentation validation completed")

# CI validation targets
ci-check: check-processing-time lint test security-check
	$(call log_success,"CI checks passed")

# Local code indexing and retrieval (RAG helper)
QUERY ?=
TELEMETRY_PATH ?= run/indexing_telemetry.jsonl
BOOTSTRAP_JSON_PATH ?= run/index_bootstrap.json

index-build:
	$(call log_info,"Building incremental local code index...")
	$(INDEX_PY) scripts/indexing/build_code_index.py --root . --index-dir .cache/code_index --telemetry-path "$(TELEMETRY_PATH)"
	$(call log_success,"Local code index refreshed")

index-build-full:
	$(call log_info,"Building full local code index (no reuse)...")
	$(INDEX_PY) scripts/indexing/build_code_index.py --root . --index-dir .cache/code_index --full --telemetry-path "$(TELEMETRY_PATH)"
	$(call log_success,"Full local code index rebuilt")

index-query:
	@if [ -z "$(QUERY)" ]; then \
		echo "Usage: make index-query QUERY='publish republish taxonomy drift'"; \
		exit 1; \
	fi
	$(call log_info,"Querying local code index...")
	$(INDEX_PY) scripts/indexing/query_code_index.py "$(QUERY)" --root . --index-dir .cache/code_index --telemetry-path "$(TELEMETRY_PATH)"

index-auto-install:
	$(call log_info,"Installing code index auto-update user units")
	@mkdir -p ~/.config/systemd/user
	@cp scripts/indexing/code_index_autoupdate.service.example ~/.config/systemd/user/code-index-autoupdate.service
	@cp scripts/indexing/code_index_autoupdate.timer.example ~/.config/systemd/user/code-index-autoupdate.timer
	@if systemctl --user daemon-reload >/dev/null 2>&1; then \
		echo "systemd user units reloaded"; \
	else \
		echo "systemd user bus unavailable; daemon fallback will be used"; \
	fi
	$(call log_success,"Code index auto-update units/scripts installed")

index-auto-enable:
	$(call log_info,"Enabling and starting code index auto-update timer")
	@if systemctl --user enable --now code-index-autoupdate.timer >/dev/null 2>&1; then \
		echo "code-index-autoupdate.timer enabled"; \
	else \
		echo "systemd user bus unavailable; starting daemon fallback"; \
		bash scripts/indexing/index_autoupdate_daemon.sh start; \
	fi
	$(call log_success,"Code index auto-update enabled")

index-auto-disable:
	$(call log_info,"Disabling and stopping code index auto-update timer")
	@systemctl --user disable --now code-index-autoupdate.timer >/dev/null 2>&1 || true
	@bash scripts/indexing/index_autoupdate_daemon.sh stop >/dev/null 2>&1 || true
	$(call log_success,"Code index auto-update timer disabled")

index-auto-status:
	$(call log_info,"Code index auto-update status")
	@if systemctl --user status code-index-autoupdate.timer --no-pager --lines=5 >/dev/null 2>&1; then \
		systemctl --user status code-index-autoupdate.timer --no-pager --lines=5 || true; \
		systemctl --user status code-index-autoupdate.service --no-pager --lines=5 || true; \
	else \
		echo "systemd user bus unavailable; daemon fallback status:"; \
		bash scripts/indexing/index_autoupdate_daemon.sh status; \
	fi

index-auto-run-now:
	$(call log_info,"Running immediate autonomous index refresh")
	@$(INDEX_PY) scripts/indexing/autonomous_index_update.py --root . --index-dir .cache/code_index --telemetry-path "$(TELEMETRY_PATH)"
	$(call log_success,"Autonomous index refresh completed")

index-bootstrap:
	$(call log_info,"Collecting new-chat bootstrap context")
	@$(INDEX_PY) scripts/indexing/bootstrap_context.py --root . --index-dir .cache/code_index --telemetry-path "$(TELEMETRY_PATH)"

index-bootstrap-json:
	$(call log_info,"Writing new-chat bootstrap JSON snapshot")
	@mkdir -p "$(dir $(BOOTSTRAP_JSON_PATH))"
	@$(INDEX_PY) scripts/indexing/bootstrap_context.py --root . --index-dir .cache/code_index --telemetry-path "$(TELEMETRY_PATH)" --json > "$(BOOTSTRAP_JSON_PATH)"
	@echo "Wrote $(BOOTSTRAP_JSON_PATH)"

index-hermes-daily:
	$(call log_info,"Running daily Hermes/index refresh workflow")
	@bash scripts/indexing/daily_hermes_refresh.sh
	$(call log_success,"Daily Hermes/index refresh workflow completed")

index-telemetry-summary:
	$(call log_info,"Summarizing indexing telemetry")
	@$(INDEX_PY) scripts/indexing/telemetry_summary.py --path "$(TELEMETRY_PATH)"

index-status-report:
	$(call log_info,"Reporting indexer health and daemon status with token trend")
	@$(INDEX_PY) scripts/indexing/token_health_report.py --telemetry-path "$(TELEMETRY_PATH)" --index-dir .cache/code_index --daemon-script scripts/indexing/index_autoupdate_daemon.sh

index-telemetry-tail:
	$(call log_info,"Showing recent indexing telemetry events")
	@tail -n 20 "$(TELEMETRY_PATH)" || true

hermes-gateway-run:
	$(call log_info,"Starting Hermes Telegram gateway in container mode")
	@mkdir -p /root/.hermes/logs
	@nohup hermes gateway run --replace >/root/.hermes/logs/gateway.out 2>&1 &
	@sleep 2
	@ps -ef | grep -E 'hermes gateway run|gateway/run.py' | grep -v grep || true
	@echo "gateway log: /root/.hermes/logs/gateway.out"
	$(call log_success,"Hermes gateway background run requested")

hermes-stack-status:
	$(call log_info,"Checking Hermes Honcho and Telegram gateway status")
	@echo "=== Hermes status ==="
	@hermes status || true
	@echo ""
	@echo "=== Honcho status ==="
	@hermes honcho status || true
	@echo ""
	@echo "=== Honcho mode ==="
	@hermes honcho mode || true
	@echo ""
	@echo "=== Gateway process check (container-safe) ==="
	@ps -ef | grep -E 'hermes gateway run|gateway/run.py' | grep -v grep || echo "Gateway process not found"
	@echo ""
	@echo "=== Gateway service status (systemd user) ==="
	@hermes gateway status || true
	@echo ""
	@echo "=== Gateway log tail ==="
	@tail -n 60 /root/.hermes/logs/gateway.out 2>/dev/null || echo "No gateway log found at /root/.hermes/logs/gateway.out"

# Validate global.env has PYTHON_BIN (CI-friendly check; does not require root)
.PHONY: check-global-env
check-global-env:
	$(call log_info,"Validating /etc/justnews/global.env or example config contains PYTHON_BIN")
	bash infrastructure/scripts/validate-global-env.sh || { $(call log_error,"global.env PYTHON_BIN validation failed"); exit 1; }
	$(call log_success,"global.env validation OK")

security-check:
	$(call log_info,"Running security checks...")
	$(PIP) check
	@if command -v bandit >/dev/null 2>&1; then \
		bandit -q -r . -x tests,build,dist,.venv || exit 1; \
	else \
		echo "bandit not installed; install with '$(PIP) install bandit' for static security scanning"; \
	fi
	$(call log_success,"Security checks completed")

# Release targets
release: release-check release-build release-publish
	$(call log_success,"Release $(VERSION) published")

release-check:
	$(call log_info,"Running release checks...")
	test -n "$(VERSION)" || ($(call log_error,"VERSION must be set"); exit 1)
	git tag -l | grep -q "^$(VERSION)$" && ($(call log_error,"Tag $(VERSION) already exists"); exit 1)
	$(call log_success,"Release checks passed")

release-build: build
	$(call log_info,"Building release artifacts...")
	# Additional release-specific build steps
	$(call log_success,"Release artifacts built")

release-publish:
	$(call log_info,"Publishing release $(VERSION)...")
	git tag $(VERSION)
	git push origin $(VERSION)
	# Publish to artifact repository
	$(call log_success,"Release $(VERSION) published")

# Cleanup targets
clean: clean-build clean-cache clean-test
	$(call log_success,"Cleanup completed")

clean-build:
	$(call log_info,"Cleaning build artifacts...")
	rm -rf $(BUILD_DIR) dist/ *.egg-info/
	$(call log_success,"Build artifacts cleaned")

clean-cache:
	$(call log_info,"Cleaning cache files...")
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name "*.pyo" -delete 2>/dev/null || true
	$(call log_success,"Cache files cleaned")

clean-test:
	$(call log_info,"Cleaning test artifacts...")
	rm -f .coverage coverage.xml
	rm -rf .pytest_cache
	$(call log_success,"Test artifacts cleaned")

# Development helpers
dev-setup: install
	$(call log_info,"Setting up development environment...")
	pre-commit install
	git config core.hooksPath .githooks
	$(call log_success,"Development environment ready")

env-bootstrap:
	$(call log_info,"Bootstrapping UV/venv environment from requirements-bootstrap.txt")
	@if command -v uv >/dev/null 2>&1; then \
		uv venv $(VENV_DIR); \
		uv pip install --python $(VENV_PY) -r requirements-bootstrap.txt; \
	else \
		$(PYTHON) -m venv $(VENV_DIR); \
		$(VENV_PY) -m pip install --upgrade pip setuptools wheel; \
		$(VENV_PY) -m pip install -r requirements-bootstrap.txt; \
	fi
	$(call log_success,"UV/venv bootstrap completed")

dev-update:
	$(call log_info,"Updating development dependencies...")
	$(PIP) install --upgrade -r requirements.txt
	pre-commit autoupdate
	$(call log_success,"Dependencies updated")

# GPU Monitor management
.PHONY: monitor-install monitor-enable monitor-disable monitor-install-rotate monitor-status monitor-tail alertmanager-install alertmanager-enable alertmanager-disable alertmanager-status alertmanager-test index-auto-install index-auto-enable index-auto-disable index-auto-status index-auto-run-now index-bootstrap index-bootstrap-json index-hermes-daily index-telemetry-summary index-status-report index-telemetry-tail hermes-gateway-run hermes-stack-status

monitor-install:
	$(call log_info,"Installing GPU monitor user systemd unit (copies example to ~/.config/systemd/user)")
	@mkdir -p ~/.config/systemd/user
	@cp scripts/gpu_monitor.service.example ~/.config/systemd/user/gpu-monitor.service
	@systemctl --user daemon-reload
	$(call log_success,"GPU monitor unit installed (run 'make monitor-enable' to start)")

monitor-enable:
	$(call log_info,"Enabling and starting GPU monitor service (user)")
	@systemctl --user enable --now gpu-monitor.service
	$(call log_success,"GPU monitor enabled and running")

monitor-disable:
	$(call log_info,"Stopping and disabling GPU monitor service (user)")
	@systemctl --user disable --now gpu-monitor.service || true
	$(call log_success,"GPU monitor disabled")

monitor-install-rotate:
	$(call log_info,"Installing logrotate policy for GPU monitor (requires sudo)")
	@sudo ./scripts/install_logrotate.sh
	$(call log_success,"Logrotate policy installed")

vllm-install-unit:
	$(call log_info,"Install vLLM systemd unit example to /etc/systemd/system (requires sudo)")
	@sudo cp infrastructure/systemd/vllm-mistral-7b.service.example /etc/systemd/system/vllm-mistral-7b.service
	@sudo systemctl daemon-reload
	$(call log_success,"vLLM systemd unit installed; run 'sudo systemctl enable --now vllm-mistral-7b' to start")

alertmanager-install-unit:
	$(call log_info,"Install Alertmanager systemd unit example (idempotent, requires sudo)")
	@sudo mkdir -p /etc/alertmanager
	@sudo cp infrastructure/systemd/alertmanager.service.example /etc/systemd/system/alertmanager.service
	@sudo systemctl daemon-reload
	$(call log_success,"Alertmanager unit installed; run 'sudo systemctl enable --now alertmanager' or run './scripts/install_alertmanager_unit.sh --enable' to enable/start")

vllm-install-and-start: vllm-install-unit
	$(call log_info,"Enable and start vLLM systemd unit (requires sudo)")
	@sudo systemctl enable --now vllm-mistral-7b.service
	$(call log_success,"vLLM systemd unit enabled and started")

modelstore-fetch-mistral:
	$(call log_info,"Fetch the canonical Mistral model into ModelStore (requires network)")
	@$(PYTHON) models/fetch_model_to_modelstore.py --model mistralai/Mistral-7B-Instruct-v0.3
	$(call log_success,"Mistral model staged into ModelStore (check $(MODEL_STORE_ROOT)/base_models)")

vllm-start:
	$(call log_info,"Start vLLM service (user)")
	@if [ -x ./scripts/start_vllm.sh ]; then \
		./scripts/start_vllm.sh; \
	else \
		echo "scripts/start_vllm.sh missing; use systemd unit targets instead (vllm-install-unit / vllm-install-and-start)."; \
		exit 1; \
	fi
	$(call log_success,"vLLM start requested; check 'make monitor-status' for status")

vllm-stop:
	$(call log_info,"Stop vLLM service (user)")
	@if [ -x ./scripts/stop_vllm.sh ]; then \
		./scripts/stop_vllm.sh; \
	else \
		echo "scripts/stop_vllm.sh missing; stop via systemd (sudo systemctl stop vllm-mistral-7b.service)."; \
		exit 1; \
	fi
	$(call log_success,"vLLM stop requested")

vllm-smoke-test:
	$(call log_info,"Run vLLM smoke test (requires network port 7060)")
	@if [ -x ./scripts/vllm_smoke_test.sh ]; then \
		./scripts/vllm_smoke_test.sh; \
	else \
		echo "scripts/vllm_smoke_test.sh missing; run manual check: curl -sS http://127.0.0.1:7060/v1/models"; \
		exit 1; \
	fi
	$(call log_success,"vLLM smoke test finished")

monitor-status:
	$(call log_info,"GPU monitor service status")
	@systemctl --user status gpu-monitor.service --no-pager --lines=5 || true

monitor-tail:
	$(call log_info,"Tailing GPU monitor log")
	@tail -n 200 run/gpu_monitor.log || true

# Alertmanager management (system-wide)
alertmanager-install:
	$(call log_info,"Install Alertmanager: apt if available, else download release (requires sudo)")
	@sudo apt-get update || true
	@sudo apt-get install -y prometheus-alertmanager || sudo apt-get install -y alertmanager || \
	( echo "Falling back to release download" && TMPDIR=$$(mktemp -d) && \
	  ARCH=$$(uname -m); \
	  case $$ARCH in x86_64) ARCH=linux-amd64 ;; aarch64) ARCH=linux-arm64 ;; *) ARCH=linux-amd64 ;; esac; \
	  TAG=$$(curl -s https://api.github.com/repos/prometheus/alertmanager/releases/latest | $(PYTHON) -c "import sys,json; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null || echo 'v0.27.0'); \
	  URL="https://github.com/prometheus/alertmanager/releases/download/$$TAG/alertmanager-$${TAG#v}.$$ARCH.tar.gz"; \
	  curl -fsSL -o $$TMPDIR/am.tar.gz "$$URL"; tar -xzf $$TMPDIR/am.tar.gz -C $$TMPDIR; BIN=$$(find $$TMPDIR -type f -name alertmanager | head -n1); sudo install -m 0755 $$BIN /usr/local/bin/alertmanager; rm -rf $$TMPDIR )
	@sudo mkdir -p /etc/alertmanager/templates /var/lib/alertmanager
	@if [ -f monitoring/alertmanager/alertmanager.example.yml ]; then sudo cp monitoring/alertmanager/alertmanager.example.yml /etc/alertmanager/alertmanager.yml; fi
	@if [ -f monitoring/alertmanager/mcp_bus_templates.tmpl ]; then sudo cp monitoring/alertmanager/mcp_bus_templates.tmpl /etc/alertmanager/templates/ ; fi
	@sudo useradd --system --no-create-home --shell /usr/sbin/nologin alertmanager || true
	@sudo chown -R alertmanager:alertmanager /etc/alertmanager /var/lib/alertmanager || true
	@sudo systemctl daemon-reload || true
	$(call log_success,"Alertmanager install step complete; run 'make alertmanager-enable' to start the service")

monitoring-check:
	$(call log_info,"Run monitoring sanity checks (prometheus rules + grafana dashboard JSON)")
	$(RUN_PY) -m pytest tests/monitoring -q
	$(call log_success,"Monitoring checks completed")
alertmanager-enable:
	$(call log_info,"Enabling and starting Alertmanager (requires sudo)")
	@sudo systemctl enable --now alertmanager.service
	$(call log_success,"Alertmanager enabled and started")

alertmanager-disable:
	$(call log_info,"Stopping and disabling Alertmanager (requires sudo)")
	@sudo systemctl disable --now alertmanager.service || true
	$(call log_success,"Alertmanager disabled")

alertmanager-status:
	$(call log_info,"Alertmanager systemd status and API check")
	@sudo systemctl status alertmanager.service --no-pager --lines=5 || true
	@echo "Alertmanager API status:"; curl -sS http://127.0.0.1:9093/api/v2/status || true

alertmanager-test:
	$(call log_info,"Sending a test alert to local Alertmanager (requires Alertmanager running)")
	@echo '[{"labels":{"alertname":"MCPBusTestAlert","service":"mcp_bus","severity":"warning"},"annotations":{"summary":"Test alert from Make","description":"This is a test alert generated by make alertmanager-test"}}]' | curl -sS -XPOST -H "Content-Type: application/json" --data @- http://127.0.0.1:9093/api/v2/alerts || true
	$(call log_success,"Test alert sent (check receivers or Alertmanager UI)")
# Information targets
info:
	@echo "JustNews Build Information"
	@echo "================================"
	@echo "Version: $(VERSION)"
	@echo "Environment: $(ENV)"
	@echo "Python: $(shell $(PYTHON) --version)"
	@echo "Build Directory: $(BUILD_DIR)"
	@echo "Config Directory: $(CONFIG_DIR)"

# Default target reminder
.DEFAULT_GOAL := help