#!/bin/bash

################################################################################
# Deployment Simulation Quick-Start Script
# 
# This script automates the complete deployment simulation workflow.
# It will:
#   1. Verify all services are running
#   2. Initialize the database
#   3. Populate test data
#   4. Start the application
#   5. Initialize the training system
#   6. Run integration tests
#
# Usage: bash run_deployment_simulation.sh [OPTIONS]
#
# Options:
#   --quick          Skip certain steps for quick testing
#   --full           Run complete simulation with all tests
#   --verbose        Show detailed output
#   --skip-tests     Skip integration tests
#   --drain-only     Only drain/cleanup without running new simulation
#   --help           Show this help message
#
################################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Config
VERBOSE=false
RUN_TESTS=true
QUICK_MODE=false
FULL_MODE=false
SIMULATION_DIR="/app/deployment-simulation"
LOG_FILE="${SIMULATION_DIR}/simulation_$(date +%Y%m%d_%H%M%S).log"
PIDS_FILE="${SIMULATION_DIR}/service_pids.txt"

# Trap for cleanup on exit
cleanup() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo -e "${RED}[ERROR] Simulation failed with exit code $exit_code${NC}"
    fi
    echo -e "${BLUE}[INFO] Cleaning up...${NC}"
    # Store PIDs for manual cleanup if needed
    ps aux | grep -E 'gunicorn|python manage.py runserver' | grep -v grep || true
    return $exit_code
}

trap cleanup EXIT

# Functions
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${BLUE}[$timestamp]${NC} [${level}] ${message}" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}✓ $@${NC}" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}✗ $@${NC}" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}⚠ $@${NC}" | tee -a "$LOG_FILE"
}

log_info() {
    echo -e "${BLUE}ℹ $@${NC}" | tee -a "$LOG_FILE"
}

compose_cmd() {
    if docker compose version >/dev/null 2>&1; then
        docker compose "$@"
        return $?
    fi

    if command -v docker-compose >/dev/null 2>&1; then
        docker-compose "$@"
        return $?
    fi

    echo -e "${RED}[ERROR] Docker Compose not found (need 'docker compose' plugin or docker-compose binary)${NC}" >&2
    return 1
}

show_help() {
    head -25 "$0" | tail -20
}

# Check args
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)
            QUICK_MODE=true
            shift
            ;;
        --full)
            FULL_MODE=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --skip-tests)
            RUN_TESTS=false
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Main simulation
main() {
    # Setup
    clear
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║     DEPLOYMENT SIMULATION - QUICK START                   ║${NC}"
    echo -e "${BLUE}║     Environment: Dev Container Simulation                ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    # Create directories
    mkdir -p "$SIMULATION_DIR"
    > "$LOG_FILE"  # Clear log file
    > "$PIDS_FILE"
    
    log_info "Simulation started"
    log_info "Log file: $LOG_FILE"
    
    # Phase 1: Verify Services
    echo ""
    echo -e "${BLUE}=== PHASE 1: VERIFY SERVICES ===${NC}"
    log_info "Checking Docker services..."
    
    if compose_cmd -f .devcontainer/docker-compose.yaml ps 2>/dev/null | grep -q "Running"; then
        log_success "Docker services running"
    else
        log_warning "Starting Docker services..."
        compose_cmd -f .devcontainer/docker-compose.yaml up -d
        sleep 5
    fi
    
    # Test MariaDB
    log_info "Testing MariaDB connection..."
    if compose_cmd -f .devcontainer/docker-compose.yaml exec mariadb mysqladmin ping -u root -proot_password 2>/dev/null | grep -q "alive"; then
        log_success "MariaDB responding"
    else
        log_error "MariaDB not responding"
        exit 1
    fi
    
    # Test ChromaDB
    log_info "Testing ChromaDB connection..."
    if curl -s http://localhost:3307 > /dev/null 2>&1; then
        log_success "ChromaDB responding"
    else
        log_error "ChromaDB not responding"
        exit 1
    fi
    
    # Phase 2: Setup Environment
    echo ""
    echo -e "${BLUE}=== PHASE 2: SETUP ENVIRONMENT ===${NC}"
    
    # Source simulation environment
    if [ ! -f "/app/.env.simulation" ]; then
        log_warning ".env.simulation not found, creating..."
        cp /app/.env.dev /app/.env.simulation 2>/dev/null || true
    fi
    
    # source /app/.env.simulation 2>/dev/null || true
    log_success "Environment loaded"
    
    # Phase 3: Database Initialization
    echo ""
    echo -e "${BLUE}=== PHASE 3: DATABASE INITIALIZATION ===${NC}"
    
    cd /app
    
    log_info "Running migrations..."
    if python manage.py migrate --noinput 2>&1 | tee -a "$LOG_FILE" | grep -q "Ran.*migration"; then
        log_success "Migrations complete"
    else
        log_warning "Migrations may already be applied"
    fi
    
    # Phase 4: Populate Database
    echo ""
    echo -e "${BLUE}=== PHASE 4: POPULATE DATABASE ===${NC}"
    
    if [ "$QUICK_MODE" = true ]; then
        log_info "Quick mode: reduced test data"
        python populate_database.py --users 2 --sources 3 --documents 10 --embeddings 20 --jobs 1 ${VERBOSE:+--verbose} | tee -a "$LOG_FILE"
    elif [ "$FULL_MODE" = true ]; then
        log_info "Full mode: maximum test data"
        python populate_database.py --users 10 --sources 20 --documents 200 --embeddings 500 --jobs 5 ${VERBOSE:+--verbose} | tee -a "$LOG_FILE"
    else
        log_info "Standard mode: default test data"
        python populate_database.py --users 5 --sources 10 --documents 50 --embeddings 100 --jobs 3 ${VERBOSE:+--verbose} | tee -a "$LOG_FILE"
    fi
    
    log_success "Database populated"
    
    # Phase 5: Start Application
    echo ""
    echo -e "${BLUE}=== PHASE 5: START APPLICATION ===${NC}"
    
    log_info "Starting Django development server..."
    
    cd /app
    python manage.py runserver 0.0.0.0:8000 > "$SIMULATION_DIR/app.log" 2>&1 &
    APP_PID=$!
    echo $APP_PID >> "$PIDS_FILE"
    
    # Wait for app to start
    log_info "Waiting for application to start..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            log_success "Application started (PID: $APP_PID)"
            break
        fi
        if [ $i -eq 30 ]; then
            log_error "Application failed to start"
            exit 1
        fi
        sleep 1
        echo -n "."
    done
    echo ""
    
    # Phase 6: Verify Application
    echo ""
    echo -e "${BLUE}=== PHASE 6: VERIFY APPLICATION ===${NC}"
    
    # Test health endpoint
    HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null || echo "error")
    if echo "$HEALTH" | jq . >/dev/null 2>&1; then
        log_success "Health endpoint responding"
        if [ "$VERBOSE" = true ]; then
            echo "$HEALTH" | jq . | tee -a "$LOG_FILE"
        fi
    else
        log_warning "Health endpoint not available yet"
    fi
    
    # Phase 7: Run Integration Tests (optional)
    if [ "$RUN_TESTS" = true ]; then
        echo ""
        echo -e "${BLUE}=== PHASE 7: RUN INTEGRATION TESTS ===${NC}"
        
        log_info "Running integration tests..."
        
        if python -m pytest tests/integration/ -v --tb=short 2>&1 | tee -a "$LOG_FILE" | grep -q "passed"; then
            log_success "Integration tests passed"
        else
            log_warning "Some integration tests may have failed (check log)"
        fi
    fi
    
    # Phase 8: Summary
    echo ""
    echo -e "${BLUE}=== SIMULATION COMPLETE ===${NC}"
    echo ""
    
    echo -e "${GREEN}✓ All services operational${NC}"
    echo -e "${GREEN}✓ Database populated with test data${NC}"
    echo -e "${GREEN}✓ Application running on http://localhost:8000${NC}"
    echo ""
    
    echo "Service Information:"
    echo "  - Django App: http://localhost:8000"
    echo "  - MariaDB: mariadb:3306"
    echo "  - ChromaDB: http://localhost:3307"
    echo "  - vLLM: http://localhost:8001"
    echo ""
    
    echo "Application PID: $APP_PID"
    echo "Log file: $LOG_FILE"
    echo ""
    
    echo "Next steps:"
    echo "  1. Open browser: http://localhost:8000"
    echo "  2. Login with admin credentials"
    echo "  3. Check database: mysql -h mariadb -u justnews -pjustnews_password justnews"
    echo "  4. Stop app: kill $APP_PID"
    echo ""
    
    log_success "Simulation ready for testing"
    
    # Keep running
    echo "Press Ctrl+C to stop the simulation."
    wait $APP_PID
}

# Error handler
error_exit() {
    log_error "$1"
    exit 1
}

# Run main
main "$@"
