#!/usr/bin/env bash
set -euo pipefail

# scripts/setup_postgres.sh
# DEPRECATED: Postgres is no longer the primary deployment database for
# JustNews (migrated to MariaDB + Chroma). This script is retained for
# historical/reference purposes only and is not recommended for new deployments.
# Use your environment's MariaDB provisioning procedures instead.
# Usage:
#   sudo ./scripts/setup_postgres.sh [--db-user USER] [--db-password PASS] [--db-name DB] [--memory-db NAME] [--pg-version 16] [--no-install]
# Example:
#   sudo ./scripts/setup_postgres.sh --db-password password123

# Defaults
DB_USER=${DB_USER:-justnews_user}
DB_PASSWORD=${DB_PASSWORD:-password123}
DB_NAME=${DB_NAME:-justnews}
MEMORY_DB_NAME=${MEMORY_DB_NAME:-justnews_memory}
PG_VERSION=${PG_VERSION:-16}
INSTALL_PG=${INSTALL_PG:-yes}
INSTALL_PGVECTOR=${INSTALL_PGVECTOR:-yes}
GLOBAL_ENV_PATH=/etc/justnews/global.env

function log() { echo "[setup-postgres] $*"; }

function usage() {
  cat <<EOF
Usage: sudo $0 [options]

Options:
  --db-user USER           Database username (default: ${DB_USER})
  --db-password PASS       Database password (default: <provided>)
  --db-name NAME           Primary database name (default: ${DB_NAME})
  --memory-db NAME         Memory DB name (default: ${MEMORY_DB_NAME})
  --pg-version VERSION     Postgres major version to install (default: ${PG_VERSION})
  --no-install             Skip package installation steps (assume postgres already installed)
  --no-pgvector            Skip attempting to install/enable pgvector
  -h, --help               Show this help
EOF
}

# Parse args
while [[ ${#} -gt 0 ]]; do
  case "$1" in
    --db-user) DB_USER="$2"; shift 2;;
    --db-password) DB_PASSWORD="$2"; shift 2;;
    --db-name) DB_NAME="$2"; shift 2;;
    --memory-db) MEMORY_DB_NAME="$2"; shift 2;;
    --pg-version) PG_VERSION="$2"; shift 2;;
    --no-install) INSTALL_PG=no; shift;;
    --no-pgvector) INSTALL_PGVECTOR=no; shift;;
    -h|--help) usage; exit 0;;
    *) log "Unknown arg: $1"; usage; exit 2;;
  esac
done

if [[ "$EUID" -ne 0 ]]; then
  log "This script must be run with sudo/root. Re-run with: sudo $0 ..."
  exit 1
fi

# Install Postgres if requested
if [[ "$INSTALL_PG" == "yes" ]]; then
  log "Attempting to install PostgreSQL ${PG_VERSION} and contrib packages"
  # Add Postgres APT repo (idempotent)
  if ! grep -q "apt.postgresql.org" /etc/apt/sources.list.d/* 2>/dev/null; then
    log "Adding PGDG apt repository"
    set +e
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /tmp/pgdg.key && \
      install -o root -g root -m 644 /tmp/pgdg.key /etc/apt/trusted.gpg.d/pgdg.asc && rm -f /tmp/pgdg.key
    set -e
    echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list || true
  fi
  apt-get update -y
  # Install packages (best-effort fallback to distro packages)
  if ! apt-get install -y postgresql-${PG_VERSION} postgresql-client-${PG_VERSION} postgresql-contrib; then
    log "Failed to install distribution-specific Postgres packages; falling back to generic 'postgresql' package"
    apt-get install -y postgresql postgresql-contrib
  fi
  systemctl enable --now postgresql
fi

# Create role (idempotent)
log "Creating/updating role '${DB_USER}'"
# Use escaped dollar signs so the shell does not expand $$ to the PID; keep the DO block on one line to avoid '\n' escapes being interpreted
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN CREATE ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASSWORD}'; ELSE ALTER ROLE ${DB_USER} WITH PASSWORD '${DB_PASSWORD}'; END IF; END \$\$;"

# Create databases (idempotent)
log "Creating databases if missing: ${DB_NAME}, ${MEMORY_DB_NAME}"
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" 2>/dev/null || log "Database ${DB_NAME} exists or create suppressed"
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${MEMORY_DB_NAME} OWNER ${DB_USER};" 2>/dev/null || log "Database ${MEMORY_DB_NAME} exists or create suppressed"

# Attempt to enable vector extension in primary DB
if [[ "$INSTALL_PGVECTOR" == "yes" ]]; then
  log "Attempting to enable 'vector' extension in ${DB_NAME} (pgvector)."
  if sudo -u postgres psql -d "${DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null; then
    log "'vector' extension is available and enabled (or already present)."
  else
    log "pgvector extension not available via package; attempting to install server-side package (best-effort)"
    set +e
    apt-get install -y postgresql-server-dev-${PG_VERSION} make gcc || apt-get install -y postgresql-server-dev-all make gcc || true
    apt-get install -y postgresql-${PG_VERSION}-pgvector || apt-get install -y postgresql-pgvector || true
    set -e
    if sudo -u postgres psql -d "${DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null; then
      log "pgvector extension installed and enabled"
    else
      log "pgvector still unavailable. The system will continue; vector-dependent features may be disabled until operator installs pgvector"
    fi
  fi

  # Also attempt to enable pgvector in the memory DB (some migrations require the vector type)
  log "Attempting to enable 'vector' extension in ${MEMORY_DB_NAME} (pgvector)"
  if sudo -u postgres psql -d "${MEMORY_DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null; then
    log "'vector' extension is available and enabled in ${MEMORY_DB_NAME}."
  else
    log "pgvector not available for memory DB; attempting package install (best-effort)"
    set +e
    apt-get install -y postgresql-server-dev-${PG_VERSION} make gcc || apt-get install -y postgresql-server-dev-all make gcc || true
    apt-get install -y postgresql-${PG_VERSION}-pgvector || apt-get install -y postgresql-pgvector || true
    set -e
    if sudo -u postgres psql -d "${MEMORY_DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null; then
      log "pgvector extension installed and enabled in ${MEMORY_DB_NAME}"
    else
      log "pgvector still unavailable in ${MEMORY_DB_NAME}. Memory migrations that use VECTOR types will fail until operator installs pgvector"
    fi
  fi
fi

# Apply core SQL migrations (scripts/migrations)
if compgen -G "scripts/migrations/[0-9]*.sql" >/dev/null; then
  log "Applying SQL migrations in scripts/migrations to ${DB_NAME}"
  for f in $(ls scripts/migrations/[0-9]*.sql 2>/dev/null | sort); do
    log "Applying $f"
    sudo -u postgres psql -d "${DB_NAME}" -f "$f"
  done
else
  log "No SQL files found in scripts/migrations/"
fi

# Apply memory agent SQL migrations to the memory DB
if compgen -G "agents/memory/db_migrations/[0-9]*.sql" >/dev/null; then
  log "Applying SQL migrations in agents/memory/db_migrations to ${MEMORY_DB_NAME}"
  for f in $(ls agents/memory/db_migrations/[0-9]*.sql 2>/dev/null | sort); do
    log "Applying $f to ${MEMORY_DB_NAME}"
    sudo -u postgres psql -d "${MEMORY_DB_NAME}" -f "$f"
  done
else
  log "No SQL files found in agents/memory/db_migrations/"
fi

# Apply stored-proc/business SQL if present
if [[ -f deploy/sql/canonical_selection.sql ]]; then
  log "Applying deploy/sql/canonical_selection.sql to ${DB_NAME}"
  sudo -u postgres psql -d "${DB_NAME}" -f deploy/sql/canonical_selection.sql || log "Warning: apply of canonical_selection.sql failed (non-fatal)"
fi

# Create global env file for services (idempotent, will overwrite)
log "Writing ${GLOBAL_ENV_PATH} (overwrite) - note: writing MARIADB_* keys for migrated deployments"
mkdir -p "$(dirname ${GLOBAL_ENV_PATH})"
cat > "${GLOBAL_ENV_PATH}" <<EOF
# NOTE: This file was written by the deprecated Postgres setup script.
# The current recommended vars use MARIADB_* names for MariaDB deployments.
MARIADB_HOST=localhost
MARIADB_DB=${DB_NAME}
MARIADB_USER=${DB_USER}
MARIADB_PASSWORD=${DB_PASSWORD}
db_pool_min_connections=2
db_pool_max_connections=10
EOF
chmod 640 "${GLOBAL_ENV_PATH}"
chown root:root "${GLOBAL_ENV_PATH}"

log "Setup complete. You can verify connectivity using:"
log "  PGPASSWORD='<password>' psql -h localhost -U ${DB_USER} -d ${DB_NAME} -c '\\dt'"
log "Or run the repo init script as the application environment user (see scripts/init_database.py)"

exit 0
