#!/usr/bin/env bash
set -euo pipefail

# JustNews Publisher Website Development Server
# Runs Django dev server on port 8100 for local website testing

# Colors
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

# Default port from env or command line
PUBLISHER_PORT="${1:-${PUBLISHER_PORT:-8100}}"
PUBLISHER_HOST="${PUBLISHER_HOST:-0.0.0.0}"

log_info "JustNews Publisher Development Server"
log_info "======================================="
log_info ""

# Ensure we're in the app directory
cd /app

# Check if database is initialized
log_info "Checking database..."
if python manage.py migrate --check 2>&1 | grep -q "No migrations to apply"; then
    log_success "Database migrations are up to date"
elif python manage.py migrate --check 2>&1 | grep -q "is not currently possible"; then
    log_warning "Database migrations needed. Running migration..."
    python manage.py migrate --noinput
    log_success "Migrations completed"
else
    log_success "Database is ready"
fi

log_info ""
log_info "Starting Django development server..."
log_info "======================================="
log_info ""
log_info "📰 Publisher Website: http://localhost:${PUBLISHER_PORT}/"
log_info ""
log_info "Available pages:"
log_info "  • Home              http://localhost:${PUBLISHER_PORT}/"
log_info "  • Archive           http://localhost:${PUBLISHER_PORT}/archive/"
log_info "  • By Category       http://localhost:${PUBLISHER_PORT}/world/"
log_info "  • Admin Panel       http://localhost:${PUBLISHER_PORT}/admin/"
log_info "  • Article API       http://localhost:${PUBLISHER_PORT}/api/publish/ (POST)"
log_info ""
log_info "Press Ctrl+C to stop the server"
log_info ""

# Run the development server
python manage.py runserver ${PUBLISHER_HOST}:${PUBLISHER_PORT}
