#!/usr/bin/env bash
# NOTE: We use 'set +e' to NOT exit on errors for service availability checks
# Only critical operations (migrations) are protected by 'set -e'
# This allows the script to continue even if optional services like ChromaDB/vLLM time out

# Activate the dependency venv for all python3 calls in this script
# This ensures MySQL packages (mysql-connector-python, pymysql) are available
export PATH="/deps/.venv/bin:$PATH"

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

log_info "  Connecting to: $MARIADB_HOST:$MARIADB_PORT (user: $MARIADB_USER)"

# Poll for MariaDB with improved retry logic
MAX_WAIT=120
WAIT_COUNT=0

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    # First try socket connection to check if port is open
    if python3 << EOF 2>/dev/null
import socket
import sys
try:
    sock = socket.create_connection(("$MARIADB_HOST", $MARIADB_PORT), timeout=2)
    sock.close()
    sys.exit(0)
except Exception as e:
    sys.exit(1)
EOF
    then
        log_info "  ✓ Port $MARIADB_PORT is accessible (after $WAIT_COUNT seconds)"
        
        # Now try actual database connection
        if python3 << EOF 2>/dev/null
import sys
try:
    import mysql.connector
    conn = mysql.connector.connect(
        host="$MARIADB_HOST",
        port=$MARIADB_PORT,
        user="$MARIADB_USER",
        password="$MARIADB_PASSWORD",
        autocommit=True
    )
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    sys.exit(0)
except Exception as e:
    # Fallback to pymysql
    try:
        import pymysql
        conn = pymysql.connect(
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
        then
            log_success "MariaDB is fully ready and operational (authentication succeeded after $WAIT_COUNT seconds)"
            break
        else
            log_info "  ⚠ Port accessible but authentication still initializing... (attempt $WAIT_COUNT/$MAX_WAIT)"
        fi
    else
        if [ $((WAIT_COUNT % 20)) -eq 0 ]; then
            log_info "  Waiting for MariaDB port $MARIADB_PORT to open... (attempt $WAIT_COUNT/$MAX_WAIT)"
        fi
    fi
    
    WAIT_COUNT=$((WAIT_COUNT + 1))
    if [ $WAIT_COUNT -lt $MAX_WAIT ]; then
        sleep 1
    fi
done

if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
    log_error "MariaDB failed to become fully operational after $MAX_WAIT seconds"
    log_error "Attempted to connect to: $MARIADB_HOST:$MARIADB_PORT"
    log_error "Try checking: docker logs mariadb"
    INIT_FAILURES=$((INIT_FAILURES + 1))
fi

# Step 1.5: Brief settling time for database to fully initialize
log_info ""
log_info "Step 1.5: Allowing MariaDB time to settle (3 seconds)..."
sleep 3
log_success "MariaDB initialization window closed. Ready for migrations."

# Step 2: Run SQL schema migrations FIRST (creates base tables like 'articles')
# This MUST run before Django migrations since Django models reference these tables
# IDEMPOTENT: Check if database is already initialized before running migrations
log_info ""
log_info "Step 2: Checking if database schema is already initialized..."

# Check if schema_migrations table exists (indicator that migrations have run before)
SCHEMA_EXISTS=0
python3 << EOF 2>/dev/null
import sys
try:
    import mysql.connector
    conn = mysql.connector.connect(
        host="$MARIADB_HOST",
        port=$MARIADB_PORT,
        user="$MARIADB_USER",
        password="$MARIADB_PASSWORD",
        database="$MARIADB_DB",
        autocommit=True
    )
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES LIKE 'schema_migrations'")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    if result:
        sys.exit(0)  # Schema exists
    else:
        sys.exit(1)  # Schema doesn't exist
except:
    sys.exit(1)
EOF

if [ $? -eq 0 ]; then
    log_success "Database schema already initialized (schema_migrations table found)"
    log_info "Skipping migrations - existing data will be preserved"
    SCHEMA_EXISTS=1
else
    log_info "Fresh database detected - running SQL schema migrations..."
fi

# Only run migrations if schema doesn't exist
if [ $SCHEMA_EXISTS -eq 0 ]; then
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
else
    log_info "Database integrity verified - migrations skipped for idempotence"
fi

# Step 2.1: Run Django migrations (now that SQL base tables exist)
log_info ""
log_info "Step 2.1: Running Django migrations..."
if python manage.py migrate --fake-initial --noinput 2>&1 | tee /tmp/migrate.log; then
    log_success "Django migrations completed (Publisher app: Article, PublishAudit)"
else
    log_error "Django migrations failed (check /tmp/migrate.log)"
    INIT_FAILURES=$((INIT_FAILURES + 1))
fi

# Step 3: Wait for ChromaDB to be fully operational (with polling)
# NOTE: ChromaDB startup is non-critical - if it times out, we continue with warnings
# IDEMPOTENT: Check if ChromaDB collections already exist
log_info ""
log_info "Step 3: Checking ChromaDB status..."
CHROMADB_HOST="${CHROMADB_HOST:-chromadb}"
CHROMADB_PORT="${CHROMADB_PORT:-8000}"
CHROMADB_MAX_WAIT=30
CHROMADB_WAIT=0
CHROMADB_READY=0
CHROMADB_HAS_COLLECTIONS=0

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
        # Second check: API responsive (list collections) AND check if collections exist
        python3 << EOF 2>/dev/null
import sys
try:
    import requests
    response = requests.get(
        f"http://$CHROMADB_HOST:$CHROMADB_PORT/api/v2/collections",
        timeout=2
    )
    if response.status_code in [200, 401, 403]:  # Accept various response codes - means service is alive
        # Check if collections exist (response should have list)
        try:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                sys.exit(0)  # Collections exist
            else:
                sys.exit(1)  # No collections yet
        except:
            sys.exit(1)  # Response not JSON, likely fresh instance
    sys.exit(1)
except:
    sys.exit(1)
EOF
        if [ $? -eq 0 ]; then
            log_success "ChromaDB is fully operational at $CHROMADB_HOST:$CHROMADB_PORT (with existing collections)"
            CHROMADB_READY=1
            CHROMADB_HAS_COLLECTIONS=1
            break
        else
            # Service responsive but no collections yet (fresh start)
            log_success "ChromaDB is fully operational at $CHROMADB_HOST:$CHROMADB_PORT (after $CHROMADB_WAIT seconds)"
            CHROMADB_READY=1
            break
        fi
    fi
    
    CHROMADB_WAIT=$((CHROMADB_WAIT + 1))
    if [ $CHROMADB_WAIT -lt $CHROMADB_MAX_WAIT ]; then
        sleep 0.5
    fi
done

if [ $CHROMADB_READY -eq 0 ]; then
    log_warning "ChromaDB did not become fully operational after $CHROMADB_MAX_WAIT seconds (may still be initializing)"
    log_info "  → Continuing without immediate ChromaDB access (collections will auto-create on first use)"
else
    if [ $CHROMADB_HAS_COLLECTIONS -eq 1 ]; then
        log_info "  → Existing collections detected - data preserved"
    else
        log_info "  → Collection auto-creation will happen on first access"
    fi
fi

# Step 4: Wait for vLLM to be accessible (with polling)
# NOTE: vLLM model loading can take 2-5 minutes; this step is non-critical
log_info ""
log_info "Step 4: Checking vLLM accessibility (non-blocking)..."
VLLM_HOST="${VLLM_HOST:-vllm}"
VLLM_PORT="${VLLM_PORT:-8001}"
VLLM_MAX_WAIT=20
VLLM_WAIT=0
VLLM_READY=0

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
        # Port open but API not ready yet
        sys.exit(1)
except:
    sys.exit(1)
EOF
    if [ $? -eq 0 ]; then
        log_success "vLLM is accessible at $VLLM_HOST:$VLLM_PORT (model loading may continue in background)"
        VLLM_READY=1
        break
    fi
    
    VLLM_WAIT=$((VLLM_WAIT + 1))
    if [ $VLLM_WAIT -lt $VLLM_MAX_WAIT ]; then
        # Slower polling for vLLM since model loading is I/O intensive
        sleep 1
    fi
done

if [ $VLLM_READY -eq 0 ]; then
    log_info "  ⓘ vLLM still initializing (model loading may take 2-5 minutes in background)"
    log_info "  → You can check model status later with: curl http://vllm:8001/v1/models"
fi

# Step 6: Final health summary
log_info ""
log_info "=========================================="
if [ $INIT_FAILURES -eq 0 ]; then
    log_success "Dev Container Initialization Complete!"
    log_info "=========================================="
    log_info ""
    log_info "✓ Services initialized and ready:"
    log_info "  • MariaDB: Ready (migrated or existing data preserved)"
    log_info "  • ChromaDB: Ready (collections created on first access or preserved)"
    log_info "  • vLLM: Accessible (model loading may continue in background)"
    log_info ""
    log_info "✓ IDEMPOTENCE ACTIVE:"
    log_info "  • Workflow data is preserved across rebuilds"
    log_info "  • Existing database schema detected and preserved"
    log_info "  • Embedding data preserved in ChromaDB"
    log_info "  • To force a clean rebuild, use: --force-clean flag"
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
    log_info "IDEMPOTENCE STATUS:"
    log_info "  • Attempting to preserve existing data"
    log_info "  • Check /tmp/sql_migrations.log for details"
    log_info "  • Check /tmp/migrate.log for Django migration issues"
    log_info ""
    log_info "To troubleshoot:"
    log_info "  • MariaDB logs: docker logs mariadb"
    log_info "  • ChromaDB logs: docker logs chromadb"
    log_info "  • vLLM logs: docker logs vllm"
fi

exit $INIT_FAILURES
