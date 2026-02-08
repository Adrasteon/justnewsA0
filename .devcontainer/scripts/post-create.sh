#!/usr/bin/env bash
set -euo pipefail

# JustNews Dev Container Post-Create Initialization Script
# Runs after dependency venv is created to set up the development environment
# This includes database migration, service verification, and health checks

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓ SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[⚠ WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗ ERROR]${NC} $1"
}

# Track initialization status
INIT_FAILURES=0

# Get configuration from global.env
if [ -f /app/global.env ]; then
    export $(grep -v '^#' /app/global.env | grep -v '^\s*$' | xargs)
    log_success "Loaded configuration from global.env"
else
    log_warning "global.env not found; using defaults"
fi

# Ensure we're in the app directory
cd /app

log_info "=========================================="
log_info "JustNews Dev Container Initialization"
log_info "=========================================="

# Step 1: Wait for MariaDB to be ready
log_info "Step 1: Waiting for MariaDB to be ready..."
MARIADB_HOST="${MARIADB_HOST:-mariadb}"
MARIADB_PORT="${MARIADB_PORT:-3306}"
MARIADB_USER="${MARIADB_USER:-justnews}"
MARIADB_PASSWORD="${MARIADB_PASSWORD:-dev_justnews_password}"

MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if nc -z "$MARIADB_HOST" "$MARIADB_PORT" 2>/dev/null; then
        log_success "MariaDB is accessible at $MARIADB_HOST:$MARIADB_PORT"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
        log_info "  Attempt $RETRY_COUNT/$MAX_RETRIES: waiting for MariaDB..."
        sleep 1
    fi
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    log_error "MariaDB failed to start after $MAX_RETRIES attempts"
    INIT_FAILURES=$((INIT_FAILURES + 1))
else
    log_success "MariaDB is ready"
fi

# Step 2: Run Django migrations
log_info ""
log_info "Step 2: Running Django migrations..."
if python manage.py migrate --noinput 2>&1 | tee /tmp/migrate.log; then
    log_success "Django migrations completed"
else
    log_error "Django migrations failed (check /tmp/migrate.log)"
    INIT_FAILURES=$((INIT_FAILURES + 1))
fi

# Step 3: Verify service connectivity
log_info ""
log_info "Step 3: Verifying service connectivity..."

# Check ChromaDB
CHROMADB_HOST="${CHROMADB_HOST:-chromadb}"
CHROMADB_PORT="${CHROMADB_PORT:-3307}"
if nc -z "$CHROMADB_HOST" "$CHROMADB_PORT" 2>/dev/null; then
    log_success "ChromaDB accessible at $CHROMADB_HOST:$CHROMADB_PORT"
else
    log_warning "ChromaDB not yet accessible at $CHROMADB_HOST:$CHROMADB_PORT (may still be starting)"
fi

# Check vLLM
VLLM_HOST="${VLLM_HOST:-vllm}"
VLLM_PORT="${VLLM_PORT:-8001}"
if nc -z "$VLLM_HOST" "$VLLM_PORT" 2>/dev/null; then
    log_success "vLLM accessible at $VLLM_HOST:$VLLM_PORT"
else
    log_warning "vLLM not yet accessible at $VLLM_HOST:$VLLM_PORT (model loading in progress)"
fi

# Step 4: Collect static files for Django
log_info ""
log_info "Step 4: Collecting static files..."
if python manage.py collectstatic --noinput 2>&1 | grep -q "static files"; then
    log_success "Static files collected"
elif grep -q "up to date" /dev/stdin 2>&1; then
    log_success "Static files already up to date"
else
    log_info "Static files collection completed"
fi

# Step 5: Final health summary
log_info ""
log_info "=========================================="
if [ $INIT_FAILURES -eq 0 ]; then
    log_success "Dev Container Initialization Complete!"
    log_info "=========================================="
    log_info ""
    log_info "Next steps:"
    log_info "  1. Verify database: python -c \"from database.utils import create_database_service; db = create_database_service(); print('✓ DB Connected')\""
    log_info "  2. Test vLLM: curl http://vllm:8001/v1/models"
    log_info "  3. Run tests: pytest tests/ -m 'not gpu' --tb=short"
    log_info ""
else
    log_warning "Dev Container Initialization Completed with $INIT_FAILURES warning(s)"
    log_info "=========================================="
    log_warning "Some services may not be fully ready. They may still be initializing."
    log_info "You can manually verify service status with docker-compose ps"
fi

exit $INIT_FAILURES
