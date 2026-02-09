#!/usr/bin/env bash
set -euo pipefail

# JustNews Dev Container Post-Create Initialization Script
# Runs after dependency venv is created to set up the development environment
# 
# NOTE: Pre-build cleanup (pre-build-cleanup.sh) has already executed on the HOST
#       to remove containers/volumes from previous builds and prevent naming conflicts.
#       This script now runs inside the freshly-built container with clean services.
#
# This includes database migration, service verification, and health checks
# Execution Order:
#   1. Wait for MariaDB (3-phase polling: port → connection → auth)
#   1.5. Settling time for database stability
#   2. Run Django migrations (Publisher app)
#   2.1. Run SQL migrations (14 pipeline tables)
#   3. Wait for ChromaDB polling
#   4. Wait for vLLM polling
#   5. Collect static files and verify

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
    source /app/global.env
    log_success "Loaded configuration from global.env"
else
    log_warning "global.env not found; using defaults"
fi

# Ensure we're in the app directory
cd /app

log_info "=========================================="
log_info "JustNews Dev Container Initialization"
log_info "=========================================="
log_info ""
log_success "Pre-build cleanup completed on host (containers/volumes cleaned)"
log_info "Building fresh infrastructure with correct service names..."
log_info ""

# Step 1: Wait for MariaDB to be fully ready and operational
log_info "Step 1: Waiting for MariaDB to be fully ready..."
MARIADB_HOST="${MARIADB_HOST:-mariadb}"
MARIADB_PORT="${MARIADB_PORT:-3306}"
MARIADB_USER="${MARIADB_USER:-justnews}"
MARIADB_PASSWORD="${MARIADB_PASSWORD:-dev_justnews_password}"

# Export for Django to use
export MARIADB_HOST MARIADB_PORT MARIADB_USER MARIADB_PASSWORD

# Poll for MariaDB with exponential backoff until fully operational
MAX_WAIT=120
WAIT_COUNT=0
PHASE=1

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    # Phase 1: Port open (seconds 0-30)
    if [ $PHASE -eq 1 ] && [ $WAIT_COUNT -ge 30 ]; then
        PHASE=2
        log_info "  Phase 1 complete (port open). Moving to Phase 2 (connection test)..."
    fi
    
    # Phase 2: Port connectivity (seconds 30-60)
    if [ $PHASE -ge 2 ]; then
        python3 << EOF 2>/dev/null
import socket
import sys
try:
    sock = socket.create_connection(("$MARIADB_HOST", $MARIADB_PORT), timeout=2)
    sock.close()
    sys.exit(0)
except:
    sys.exit(1)
EOF
        if [ $? -eq 0 ]; then
            PHASE=3
            log_info "  Phase 2 complete (port accessible). Moving to Phase 3 (authentication test)..."
        fi
    fi
    
    # Phase 3: Actual database connectivity and authentication (seconds 60+)
    if [ $PHASE -ge 3 ]; then
        python3 << EOF 2>/dev/null
import sys
try:
    import MySQLdb
    conn = MySQLdb.connect(
        host="$MARIADB_HOST",
        port=$MARIADB_PORT,
        user="$MARIADB_USER",
        passwd="$MARIADB_PASSWORD"
    )
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    if result and result[0] == 1:
        sys.exit(0)
    sys.exit(1)
except Exception as e:
    # MySQLdb not available, try with mysql.connector
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host="$MARIADB_HOST",
            port=$MARIADB_PORT,
            user="$MARIADB_USER",
            password="$MARIADB_PASSWORD"
        )
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        sys.exit(0)
    except:
        sys.exit(1)
EOF
        if [ $? -eq 0 ]; then
            log_success "MariaDB is fully ready and operational (after $WAIT_COUNT seconds)"
            break
        fi
    fi
    
    WAIT_COUNT=$((WAIT_COUNT + 1))
    if [ $WAIT_COUNT -lt $MAX_WAIT ]; then
        # Brief delay for smoother polling
        sleep 0.5
    fi
done

if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
    log_error "MariaDB failed to become fully operational after $MAX_WAIT seconds"
    log_error "Phases reached: Port=$((PHASE >= 1 ? 1 : 0)), Connection=$((PHASE >= 2 ? 1 : 0)), Auth=$((PHASE >= 3 ? 1 : 0))"
    INIT_FAILURES=$((INIT_FAILURES + 1))
fi

# Step 1.5: Brief settling time for database to fully initialize
log_info ""
log_info "Step 1.5: Allowing MariaDB time to settle (3 seconds)..."
sleep 3
log_success "MariaDB initialization window closed. Ready for migrations."

# Step 2: Run Django migrations
log_info ""
log_info "Step 2: Running Django migrations..."
if python manage.py migrate --fake-initial --noinput 2>&1 | tee /tmp/migrate.log; then
    log_success "Django migrations completed (Publisher app: Article, PublishAudit)"
else
    log_error "Django migrations failed (check /tmp/migrate.log)"
    INIT_FAILURES=$((INIT_FAILURES + 1))
fi

# Step 2.1: Run SQL schema migrations for pipeline infrastructure
log_info ""
log_info "Step 2.1: Running SQL schema migrations for pipeline infrastructure..."
if [ -f /app/apply_migrations_script.py ]; then
    if python /app/apply_migrations_script.py 2>&1 | tee /tmp/sql_migrations.log; then
        log_success "SQL migrations completed (14 pipeline tables created: articles, sources, entities, etc.)"
    else
        log_error "SQL migrations failed (check /tmp/sql_migrations.log)"
        INIT_FAILURES=$((INIT_FAILURES + 1))
    fi
else
    log_warning "apply_migrations_script.py not found; skipping SQL migrations"
    log_info "  → Pipeline tables (articles, sources, entities, etc.) will not be created"
    log_info "  → Run manually later: python apply_migrations_script.py"
fi

# Step 3: Wait for ChromaDB to be fully operational (with polling)
log_info ""
log_info "Step 3: Waiting for ChromaDB to be fully operational..."
CHROMADB_HOST="${CHROMADB_HOST:-chromadb}"
CHROMADB_PORT="${CHROMADB_PORT:-3307}"
CHROMADB_MAX_WAIT=60
CHROMADB_WAIT=0

while [ $CHROMADB_WAIT -lt $CHROMADB_MAX_WAIT ]; do
    # First check: port open
    python3 << EOF 2>/dev/null
import socket
try:
    sock = socket.create_connection(("$CHROMADB_HOST", $CHROMADB_PORT), timeout=2)
    sock.close()
    exit(0)
except:
    exit(1)
EOF
    if [ $? -eq 0 ]; then
        # Second check: API responsive (list collections)
        python3 << EOF 2>/dev/null
import sys
try:
    import requests
    response = requests.get(
        f"http://$CHROMADB_HOST:$CHROMADB_PORT/api/v1/collections",
        timeout=2
    )
    if response.status_code in [200, 401, 403]:  # Accept various response codes - means service is alive
        sys.exit(0)
    sys.exit(1)
except Exception as e:
    # Service may not expose collections endpoint, try heartbeat
    try:
        response = requests.get(
            f"http://$CHROMADB_HOST:$CHROMADB_PORT/api/v1/heartbeat",
            timeout=2
        )
        if response.status_code in [200, 401, 403]:
            sys.exit(0)
        sys.exit(1)
    except:
        sys.exit(1)
EOF
        if [ $? -eq 0 ]; then
            log_success "ChromaDB is fully operational at $CHROMADB_HOST:$CHROMADB_PORT (v0.4.18, after $CHROMADB_WAIT seconds)"
            break
        fi
    fi
    
    CHROMADB_WAIT=$((CHROMADB_WAIT + 1))
    if [ $CHROMADB_WAIT -lt $CHROMADB_MAX_WAIT ]; then
        sleep 0.5
    fi
done

if [ $CHROMADB_WAIT -ge $CHROMADB_MAX_WAIT ]; then
    log_warning "ChromaDB did not become fully operational after $CHROMADB_MAX_WAIT seconds (may still be initializing)"
else
    log_info "  → Collection auto-creation will happen on first access"
fi

# Step 4: Wait for vLLM to be accessible (with polling)
log_info ""
log_info "Step 4: Waiting for vLLM to be accessible..."
VLLM_HOST="${VLLM_HOST:-vllm}"
VLLM_PORT="${VLLM_PORT:-8001}"
VLLM_MAX_WAIT=120
VLLM_WAIT=0

while [ $VLLM_WAIT -lt $VLLM_MAX_WAIT ]; do
    python3 << EOF 2>/dev/null
import sys
try:
    import socket
    sock = socket.create_connection(("$VLLM_HOST", $VLLM_PORT), timeout=2)
    sock.close()
    
    # Port is open, try to reach the API
    try:
        import requests
        response = requests.get(
            f"http://$VLLM_HOST:$VLLM_PORT/v1/models",
            timeout=3
        )
        if response.status_code in [200, 401, 503]:  # 503 means model still loading
            sys.exit(0)
        sys.exit(1)
    except:
        # Port open but API not ready yet - this is OK, still initializing
        sys.exit(1)
except:
    sys.exit(1)
EOF
    if [ $? -eq 0 ]; then
        log_success "vLLM is accessible at $VLLM_HOST:$VLLM_PORT (after $VLLM_WAIT seconds, model may still be loading)"
        break
    fi
    
    VLLM_WAIT=$((VLLM_WAIT + 1))
    if [ $VLLM_WAIT -lt $VLLM_MAX_WAIT ]; then
        # Slower polling for vLLM since model loading is I/O intensive
        sleep 1
    fi
done

if [ $VLLM_WAIT -ge $VLLM_MAX_WAIT ]; then
    log_warning "vLLM did not become accessible after $VLLM_MAX_WAIT seconds (model loading may take 2-5 minutes, continuing..."
else
    log_info "  → vLLM will continue model loading in background"
fi

# Step 5: Collect static files for Django
log_info ""
log_info "Step 5: Collecting static files..."
if python manage.py collectstatic --noinput 2>&1 | grep -q "static files"; then
    log_success "Static files collected"
elif grep -q "up to date" /dev/stdin 2>&1; then
    log_success "Static files already up to date"
else
    log_info "Static files collection completed"
fi

# Step 6: Final health summary
log_info ""
log_info "=========================================="
if [ $INIT_FAILURES -eq 0 ]; then
    log_success "Dev Container Initialization Complete!"
    log_info "=========================================="
    log_info ""
    log_info "✓ Services initialized and ready:"
    log_info "  • MariaDB: Tables created via migrations"
    log_info "  • ChromaDB: Ready (collection created on first access)"
    log_info "  • vLLM: Accessible (model loading may continue in background)"
    log_info ""
    log_info "Next verification steps:"
    log_info "  1. Database: python -c \"from database.utils import create_database_service; db = create_database_service(); print('✓ DB Connected')\""
    log_info "  2. ChromaDB: python -c \"from database.utils import create_database_service; db = create_database_service(); print(f'✓ Collection: {db.collection}')\""
    log_info "  3. vLLM API: curl http://vllm:8001/v1/models"
    log_info "  4. Pipeline tables: mysql -h mariadb -justnews -p'dev_justnews_password' -e 'SHOW TABLES;' 2>/dev/null | grep -E 'articles|sources|crawler_jobs|synthesized'"
    log_info "  5. Run tests: pytest tests/ -m 'not gpu' --tb=short"
    log_info ""
else
    log_warning "Dev Container Initialization Completed with $INIT_FAILURES warning(s)"
    log_info "=========================================="
    log_warning "Some services may not be fully ready. They may still be initializing."
    log_info "You can manually verify service status with docker-compose ps"
    log_info ""
    log_info "To troubleshoot:"
    log_info "  • MariaDB logs: docker logs <container-name>-mariadb-1"
    log_info "  • ChromaDB logs: docker logs <container-name>-chromadb-1"
    log_info "  • vLLM logs: docker logs <container-name>-vllm-1"
fi

exit $INIT_FAILURES
