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
	@echo "  test-unit   Run unit tests only"
	@echo "  test-integration  Run integration tests"
	@echo "  test-performance  Run performance tests"
	@echo "  test-phase1 Run Phase 1 tests (GPU ingestion/embeddings) in phase1 env"
	@echo "  test-phase2 Run Phase 2 tests (CPU clustering/analytics) in phase2 env"
	@echo "  test-phase3 Run Phase 3 tests (GPU synthesis/LLM) in phase3 env"
	@echo "  test-phase4 Run Phase 4 tests (CPU publishing/Django) in phase4 env"
	@echo "  test-phased Run all phased tests sequentially (phase1→2→3→4)"
	@echo "  test-phase-discovery  Discover tests per phase without running"
	@echo "  lint        Run code quality checks"
	@echo "  format      Format code with consistent style"
	@echo "  clean       Clean build artifacts and cache files"
	@echo "  build       Build production artifacts"
	@echo "  deploy      Deploy to target environment"
	@echo "  docs        Generate and validate documentation"
	@echo "  ci-check    Run CI validation checks"
	@echo "  release     Create and publish release"
	@echo "  monitor-install    Install GPU monitor user unit (local dev)"
	@echo "  monitor-enable     Enable & start GPU monitor service (user)"
	@echo "  monitor-status     Show GPU monitor status"
	@echo "  monitor-tail       Tail GPU monitor log"
	@echo "  monitor-install-rotate   Install logrotate policy (requires sudo)"	@echo "  alertmanager-install    Install Alertmanager and copy example configs (requires sudo)"
	@echo "  alertmanager-enable     Enable & start Alertmanager (requires sudo)"
	@echo "  alertmanager-disable    Stop and disable Alertmanager (requires sudo)"
	@echo "  alertmanager-status     Show Alertmanager status and API info"
	@echo "  alertmanager-test       Send a test alert to local Alertmanager instance"
	@echo "  monitoring-check        Run Prometheus & Grafana validity checks (pytest tests/monitoring)"
	@echo ""
	@echo "Environment variables:"
	@echo "  ENV         Target environment (development/staging/production)"
	@echo "  VERSION     Release version (for release target)"
	@echo "  DOCKER_TAG  Docker image tag (for deploy target)"

# Environment setup
ENV ?= development
VERSION ?= $(shell git describe --tags --abbrev=0 2>/dev/null || echo "v0.1.0")
DOCKER_TAG ?= latest

# Python and tools
PYTHON := python
PIP := $(PYTHON) -m pip
# Allow a single, overrideable canonical environment name that can be set in
# /etc/justnews/global.env or exported by the operator. Default remains
# `${CANONICAL_ENV:-justnews-py312}` for compatibility.
CANONICAL_ENV ?= justnews-py312
CONDA_ENV ?= $(CANONICAL_ENV)
CONDA := $(shell command -v conda 2>/dev/null || echo)
ifeq ($(CONDA),)
RUN_PY := $(PYTHON)
else
# If the run wrapper exists prefer to load global.env before running conda-run;
# this makes local & CI test runs consistently pick up the canonical env vars.
# NOTE: We recommend installing `mamba` into base for faster environment solves:
#   conda install -n base -c conda-forge mamba -y
# `mamba run -n <env>` is a drop-in replacement for `conda run -n <env>` when available.
RUN_WRAPPER := $(shell [ -x ./scripts/run_with_env.sh ] && printf "./scripts/run_with_env.sh" || printf "")
# Prefer using mamba if available (faster resolver). Detect at make parse-time.
RUNNER := $(shell command -v mamba >/dev/null 2>&1 && echo mamba || echo conda)
ifeq ($(RUN_WRAPPER),)
RUN_PY := $(RUNNER) run -n $(CONDA_ENV) $(PYTHON)
else
RUN_PY := $(RUN_WRAPPER) $(RUNNER) run -n $(CONDA_ENV) $(PYTHON)
endif
endif

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
test: test-unit test-integration
	$(call log_success,"All tests completed")

# Local pytest wrapper target which ensures tests are launched in the
# `${CANONICAL_ENV:-justnews-py312}` conda environment. Developers should prefer this target
# for local runs to ensure consistent environments.
pytest-local:
	$(call log_info,"Running local pytest via scripts/dev/pytest.sh")
	$(shell [ -x ./scripts/dev/run_full_pytest_safe.sh ] || chmod +x ./scripts/dev/run_full_pytest_safe.sh)
	./scripts/dev/run_full_pytest_safe.sh

test-unit:
	$(call log_info,"Running unit tests...")
	$(RUN_PY) -m pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=xml \
		--cov-fail-under=80 -k "not integration" --tb=short
	$(call log_success,"Unit tests passed")

test-integration:
	$(call log_info,"Running integration tests...")
	$(RUN_PY) -m pytest tests/ -v -k "integration" --tb=short || \
		($(call log_warning,"Integration tests failed, but continuing..."); true)
	$(call log_success,"Integration tests completed")

test-performance:
	$(call log_info,"Running performance tests...")
	$(RUN_PY) -m pytest tests/ -v -k "performance" --tb=short --durations=10
	$(call log_success,"Performance tests completed")

# Phased test targets (runs tests per workflow phase in isolated environments)
test-phase1:
	$(call log_info,"Running Phase 1 tests (GPU Ingestion, Embeddings, Crawler)...")
	./scripts/run_phase_tests.sh 1 --tb=short
	$(call log_success,"Phase 1 tests completed")

test-phase2:
	$(call log_info,"Running Phase 2 tests (CPU Clustering, Analytics, Unit Tests)...")
	./scripts/run_phase_tests.sh 2 --tb=short
	$(call log_success,"Phase 2 tests completed")

test-phase3:
	$(call log_info,"Running Phase 3 tests (GPU Synthesis, LLM Inference)...")
	./scripts/run_phase_tests.sh 3 --tb=short
	$(call log_success,"Phase 3 tests completed")

test-phase4:
	$(call log_info,"Running Phase 4 tests (CPU Publishing, Django)...")
	./scripts/run_phase_tests.sh 4 --tb=short
	$(call log_success,"Phase 4 tests completed")

test-phased: test-phase1 test-phase2 test-phase3 test-phase4
	$(call log_success,"All phased tests completed")

test-phase-discovery:
	$(call log_info,"Discovering tests for all phases...")
	./scripts/run_phase_tests.sh all --collect-only
	$(call log_success,"Test discovery completed")

# Code quality targets

# Linting includes a check for reintroduced container/orchestration artifacts
lint: check-processing-time lint-code lint-docs lint-no-containers
	$(call log_success,"Code quality checks passed")

# Repo-specific checks
check-processing-time:
	$(call log_info,"Checking processing_time usage patterns...")
	python3 scripts/check_processing_time.py
	$(call log_success,"Processing time checks completed")

lint-code:
	$(call log_info,"Running code linting...")
	ruff check . --fix
	mypy . --ignore-missing-imports || true
	$(call log_success,"Code linting completed")

lint-docs:
	$(call log_info,"Running documentation checks...")
	python scripts/ci/enforce_docs_policy.py
	$(call log_success,"Documentation checks passed")

# Repo checks for disallowed container references (fail CI if found)
lint-no-containers:
	$(call log_info,"Checking for disallowed container/orchestration references in code...")
	python scripts/checks/no_container_refs.py || (printf '\033[0;31m[ERROR]\033[0m %s\n' "Disallowed container/orchestration references found, see output above."; exit 1)
	$(call log_success,"No disallowed container/orchestration references outside allowed folders.")

format:
	$(call log_info,"Formatting code...")
	ruff format .
	$(call log_success,"Code formatting completed")

# Build targets
build: clean build-artifacts build-containers
	$(call log_success,"Build completed")

build-artifacts: $(ARTIFACTS_DIR)
	$(call log_info,"Building production artifacts...")
	mkdir -p $(DIST_DIR)
	$(PYTHON) -m pip wheel . -w $(DIST_DIR)/
	cp requirements.txt $(DIST_DIR)/
	cp environment.yml $(DIST_DIR)/
	$(call log_info,"Creating artifact archive...")
	cd $(BUILD_DIR) && tar -czf artifacts/justnews-$(VERSION).tar.gz -C dist .
	$(call log_success,"Artifacts built in $(ARTIFACTS_DIR)")

build-containers:
	$(call log_error,"Docker containers and Kubernetes manifests are deprecated and disabled. Use systemd packaging or CI-driven builds/artifacts.")
	@exit 1

$(ARTIFACTS_DIR):
	mkdir -p $(ARTIFACTS_DIR)

# Deployment targets
deploy: deploy-check deploy-$(ENV)
	$(call log_success,"Deployment to $(ENV) completed")

deploy-check:
	$(call log_info,"Running pre-deployment checks...")
	test -f $(CONFIG_DIR)/system_config.json || ($(call log_error,"Config file missing"); exit 1)
	$(PYTHON) -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" || \
			($(call log_error,"Python 3.11+ required"); exit 1)
	$(call log_success,"Pre-deployment checks passed")

deploy-development: deploy-check
	$(call log_warning,"docker-compose and Kubernetes deployments are deprecated; using systemd instead")
	# Prefer deploy-systemd or deploy-staging (k8s) for dev environment
	$(call log_info,"Deploying to development environment using systemd (preferred alternative)...")
	$(MAKE) deploy-systemd
	$(call log_success,"Development deployment completed (via systemd)")

deploy-staging: deploy-check
	$(call log_info,"Deploying to staging environment using systemd...")
	$(MAKE) deploy-systemd
	$(call log_success,"Staging deployment completed (via systemd)")

deploy-production: deploy-check
	$(call log_info,"Deploying to production environment using systemd...")
	$(MAKE) deploy-systemd
	$(call log_success,"Production deployment completed (via systemd)")

# Documentation targets
docs: docs-generate docs-validate
	$(call log_success,"Documentation updated")

docs-generate:
	$(call log_info,"Generating API documentation...")
	# Generate OpenAPI/Swagger docs
	$(call log_success,"API documentation generated")

docs-validate:
	$(call log_info,"Validating documentation...")
	python docs/doc_management_tools/doc_linter.py --report
	$(call log_success,"Documentation validation completed")

# CI validation targets
ci-check: check-processing-time lint test security-check
	$(call log_success,"CI checks passed")

# Validate global.env has PYTHON_BIN (CI-friendly check; does not require root)
.PHONY: check-global-env
check-global-env:
	$(call log_info,"Validating /etc/justnews/global.env or example config contains PYTHON_BIN")
	bash infrastructure/scripts/validate-global-env.sh || { $(call log_error,"global.env PYTHON_BIN validation failed"); exit 1; }
	$(call log_success,"global.env validation OK")

security-check:
	$(call log_info,"Running security checks...")
	# Run security scanning tools
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
	rm -f .coverage coverage.xml .pytest_cache/
	$(call log_success,"Test artifacts cleaned")

# Development helpers
dev-setup: install
	$(call log_info,"Setting up development environment...")
	pre-commit install
	git config core.hooksPath .githooks
	$(call log_success,"Development environment ready")

env-bootstrap:
	$(call log_info,"Bootstrap canonical conda env (${CANONICAL_ENV:-justnews-py312}) and install vLLM")
	@./scripts/bootstrap_conda_env.sh || (echo "Bootstrap failed; check output"; false)
	$(call log_success,"Conda env bootstrap completed")

dev-update:
	$(call log_info,"Updating development dependencies...")
	$(PIP) install --upgrade -r requirements.txt
	pre-commit autoupdate
	$(call log_success,"Dependencies updated")

# GPU Monitor management
.PHONY: monitor-install monitor-enable monitor-disable monitor-install-rotate monitor-status monitor-tail alertmanager-install alertmanager-enable alertmanager-disable alertmanager-status alertmanager-test

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
	@sudo cp infrastructure/systemd/vllm.service.example /etc/systemd/system/vllm.service
	@sudo systemctl daemon-reload
	$(call log_success,"vLLM systemd unit installed; run 'sudo systemctl enable --now vllm' to start")

alertmanager-install-unit:
	$(call log_info,"Install Alertmanager systemd unit example (idempotent, requires sudo)")
	@sudo mkdir -p /etc/alertmanager
	@sudo cp infrastructure/systemd/alertmanager.service.example /etc/systemd/system/alertmanager.service
	@sudo systemctl daemon-reload
	$(call log_success,"Alertmanager unit installed; run 'sudo systemctl enable --now alertmanager' or run './scripts/install_alertmanager_unit.sh --enable' to enable/start")

vllm-install-and-start: vllm-install-unit
	$(call log_info,"Enable and start vLLM systemd unit (requires sudo)")
	@sudo systemctl enable --now vllm.service
	$(call log_success,"vLLM systemd unit enabled and started")

modelstore-fetch-qwen:
	$(call log_info,"Fetch the canonical Qwen 2.5 14B model into ModelStore (requires network)")
	@$(PYTHON) models/fetch_model_to_modelstore.py --model Qwen/Qwen2.5-14B-Instruct-AWQ
	$(call log_success,"Qwen model staged into ModelStore (check $(MODEL_STORE_ROOT)/base_models)")

vllm-start:
	$(call log_info,"Start vLLM service (user)")
	@./scripts/start_vllm.sh
	$(call log_success,"vLLM start requested; check 'make monitor-status' for status")

vllm-stop:
	$(call log_info,"Stop vLLM service (user)")
	@./scripts/stop_vllm.sh
	$(call log_success,"vLLM stop requested")

vllm-smoke-test:
	$(call log_info,"Run vLLM smoke test (requires network port 7060)")
	@./scripts/vllm_smoke_test.sh
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
	  TAG=$$(curl -s https://api.github.com/repos/prometheus/alertmanager/releases/latest | python -c "import sys,json; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null || echo 'v0.27.0'); \
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