#!/usr/bin/env bash
# Apply synthesis migrations 004 and 005 with basic safety checks
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
MIGRATIONS=("$REPO_ROOT/database/migrations/004_add_synthesis_fields.sql" "$REPO_ROOT/database/migrations/005_create_synthesized_articles_table.sql" "$REPO_ROOT/database/migrations/006_create_synthesizer_jobs_table.sql")
LOG_DIR="$REPO_ROOT/logs/operations/migrations"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "Usage: apply_synthesis_migration.sh [DB_URL]"
  exit 0
fi

DB_URL="${1:-${JUSTNEWS_DB_URL:-}}"

# If no DB URL provided, prefer MariaDB variables from global.env (MARIADB_*) to
# avoid falling back to old/deprecated Postgres credentials. Construct a
# mysql:// URL so the rest of the script can parse it.
if [[ -z "$DB_URL" ]]; then
  M_HOST="${MARIADB_HOST:-${MARIADB_HOST:-127.0.0.1}}"
  M_PORT="${MARIADB_PORT:-3306}"
  M_DB="${MARIADB_DB:-justnews}"
  M_USER="${MARIADB_USER:-justnews}"
  M_PASS="${MARIADB_PASSWORD:-}"

  if [[ -n "$M_USER" && -n "$M_PASS" ]]; then
    DB_URL="mysql://${M_USER}:${M_PASS}@${M_HOST}:${M_PORT}/${M_DB}"
  else
    # if password is not available in env, build an url without credentials
    DB_URL="mysql://${M_HOST}:${M_PORT}/${M_DB}"
  fi
fi
if [[ -z "$DB_URL" ]]; then
  echo "Error: DB URL not provided. Set JUSTNEWS_DB_URL or pass it as first arg." >&2
  exit 1
fi

mkdir -p "$LOG_DIR"

for MIGRATION in "${MIGRATIONS[@]}"; do
  if [[ ! -f "$MIGRATION" ]]; then
    echo "Migration not found: $MIGRATION" >&2
    exit 1
  fi
  timestamp=$(date -u +"%Y%m%dT%H%M%SZ")
  echo "Applying $MIGRATION"
  if [[ "$DB_URL" =~ ^mysql:|^mariadb: ]]; then
    MYSQL_USER=$(echo "$DB_URL" | sed -E 's#.*//([^:]+):.*@.*#\1#')
    MYSQL_PASS=$(echo "$DB_URL" | sed -E 's#.*//[^:]+:([^@]+)@.*#\1#')
    MYSQL_HOST=$(echo "$DB_URL" | sed -E 's#.*@([^:/]+).*#\1#')
    MYSQL_PORT=$(echo "$DB_URL" | sed -E 's#.*:([0-9]+)/.*#\1#' )
    MYSQL_DBNAME=$(echo "$DB_URL" | sed -E 's#.*/([^/]+)$#\1#' )
    MYSQL_PORT=${MYSQL_PORT:-3306}
  else
    PAGER=cat psql "$DB_URL" -v ON_ERROR_STOP=1 -1 -f "$MIGRATION" | tee "$LOG_DIR/migration_${timestamp}.log"
  fi
  
    # Try applying using the local mysql client; if that fails attempt
    # fallbacks: use --protocol=TCP and/or the mariadb client if available.
    apply_ok=false
    if [[ -z "${MYSQL_PASS}" ]]; then
      if mysql --user="$MYSQL_USER" --host="$MYSQL_HOST" --port="$MYSQL_PORT" "$MYSQL_DBNAME" < "$MIGRATION" 2>&1 | tee "$LOG_DIR/migration_${timestamp}.log"; then
        apply_ok=true
      fi
    else
      if MYSQL_PWD="$MYSQL_PASS" mysql --user="$MYSQL_USER" --host="$MYSQL_HOST" --port="$MYSQL_PORT" "$MYSQL_DBNAME" < "$MIGRATION" 2>&1 | tee "$LOG_DIR/migration_${timestamp}.log"; then
        apply_ok=true
      fi
    fi

    if ! $apply_ok; then
      echo "Primary mysql client failed, trying fallback with --protocol=TCP" | tee -a "$LOG_DIR/migration_${timestamp}.log"
      if [[ -z "${MYSQL_PASS}" ]]; then
        if mysql --protocol=TCP --user="$MYSQL_USER" --host="$MYSQL_HOST" --port="$MYSQL_PORT" "$MYSQL_DBNAME" < "$MIGRATION" 2>&1 | tee -a "$LOG_DIR/migration_${timestamp}.log"; then
          apply_ok=true
        fi
      else
        if MYSQL_PWD="$MYSQL_PASS" mysql --protocol=TCP --user="$MYSQL_USER" --host="$MYSQL_HOST" --port="$MYSQL_PORT" "$MYSQL_DBNAME" < "$MIGRATION" 2>&1 | tee -a "$LOG_DIR/migration_${timestamp}.log"; then
          apply_ok=true
        fi
      fi
    fi

    if ! $apply_ok; then
      echo "Attempting mariadb client if available" | tee -a "$LOG_DIR/migration_${timestamp}.log"
      if command -v mariadb >/dev/null 2>&1; then
        if [[ -z "${MYSQL_PASS}" ]]; then
          if mariadb --user="$MYSQL_USER" --host="$MYSQL_HOST" --port="$MYSQL_PORT" "$MYSQL_DBNAME" < "$MIGRATION" 2>&1 | tee -a "$LOG_DIR/migration_${timestamp}.log"; then
            apply_ok=true
          fi
        else
          if mariadb --user="$MYSQL_USER" --password="$MYSQL_PASS" --host="$MYSQL_HOST" --port="$MYSQL_PORT" "$MYSQL_DBNAME" < "$MIGRATION" 2>&1 | tee -a "$LOG_DIR/migration_${timestamp}.log"; then
            apply_ok=true
          fi
        fi
      fi
    fi

    if ! $apply_ok; then
      echo "All migration attempts failed for $MIGRATION — check $LOG_DIR/migration_${timestamp}.log" | tee -a "$LOG_DIR/migration_${timestamp}.log"
      exit 1
    fi
done

echo "All migrations applied."