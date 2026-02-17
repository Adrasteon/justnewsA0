#!/usr/bin/env bash
# Apply Stage B migration 003 with safety checks and optional evidence capture
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
MIGRATION_FILE="$REPO_ROOT/database/migrations/003_stage_b_ingestion.sql"
EVIDENCE_LOG="$REPO_ROOT/docs/operations/stage_b_validation_evidence_log.md"
LOG_DIR="$REPO_ROOT/logs/operations/migrations"

print_usage() {
  cat <<'USAGE'
Usage: apply_stage_b_migration.sh [DB_URL] [--record]

Arguments:
  DB_URL    Optional Postgres connection string. Falls back to JUSTNEWS_DB_URL.
  --record  Append a timestamped note to the Stage B evidence log on success.

Environment:
  JUSTNEWS_DB_URL  Default connection string if DB_URL not provided.
USAGE
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  print_usage
  exit 0
fi

DB_URL="${1:-}"
RECORD_FLAG="${2:-}"

if [[ -z "$DB_URL" ]]; then
  DB_URL="${JUSTNEWS_DB_URL:-}"
fi

# If still not set, prefer MariaDB env vars from global.env to avoid falling back
# to deprecated postgres-only defaults.
if [[ -z "$DB_URL" ]]; then
  M_HOST="${MARIADB_HOST:-127.0.0.1}"
  M_PORT="${MARIADB_PORT:-3306}"
  M_DB="${MARIADB_DB:-justnews}"
  M_USER="${MARIADB_USER:-justnews}"
  M_PASS="${MARIADB_PASSWORD:-}"

  if [[ -n "$M_USER" && -n "$M_PASS" ]]; then
    DB_URL="mysql://${M_USER}:${M_PASS}@${M_HOST}:${M_PORT}/${M_DB}"
  else
    DB_URL="mysql://${M_HOST}:${M_PORT}/${M_DB}"
  fi
fi

if [[ -z "$DB_URL" ]]; then
  echo "Error: database URL not provided. Set JUSTNEWS_DB_URL or pass it as the first argument." >&2
  exit 1
fi

if [[ ! -f "$MIGRATION_FILE" ]]; then
  echo "Error: migration file not found at $MIGRATION_FILE" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
timestamp="$(date -u +'%Y%m%dT%H%M%SZ')"
log_file="$LOG_DIR/migration_003_${timestamp}.log"

echo "Applying migration 003_stage_b_ingestion using $MIGRATION_FILE"
echo "Logging output to $log_file"

# Detect DB scheme to choose client. If DB_URL starts with 'postgres' use psql,
# if it starts with 'mysql' or 'mariadb' use mysql. When using mysql, the
# migration SQL may not be compatible with MariaDB; the script will warn.
case "$DB_URL" in
  postgres:*|postgresql:*)
    echo "Detected PostgreSQL URL; using psql to run migration (postgreSQL-only SQL may be present)."
    PAGER=cat psql "$DB_URL" -v ON_ERROR_STOP=1 -1 -f "$MIGRATION_FILE" | tee "$log_file"
    ;;
  mysql:*|mariadb:*)
    echo "Detected MySQL/MariaDB URL; using mysql to run migration. Ensure SQL is compatible with MariaDB."
    # Extract user/password/host/port/dbname from URL like: mysql://user:pass@host:3306/dbname
    MYSQL_USER=$(echo "$DB_URL" | sed -E 's#.*//([^:]+):.*@.*#\1#' )
    MYSQL_PASS=$(echo "$DB_URL" | sed -E 's#.*//[^:]+:([^@]+)@.*#\1#' )
    MYSQL_HOST=$(echo "$DB_URL" | sed -E 's#.*@([^:/]+).*#\1#' )
    MYSQL_PORT=$(echo "$DB_URL" | sed -E 's#.*:([0-9]+)/.*#\1#' )
    MYSQL_DBNAME=$(echo "$DB_URL" | sed -E 's#.*/([^/]+)$#\1#' )
    MYSQL_PORT=${MYSQL_PORT:-3306}
    # Run via mysql client; ensure password handling is secure
    MYSQL_PWD="$MYSQL_PASS" mysql --user="$MYSQL_USER" --host="$MYSQL_HOST" --port="$MYSQL_PORT" "$MYSQL_DBNAME" < "$MIGRATION_FILE" 2>&1 | tee "$log_file"
    ;;
  *)
    echo "No recognizable DB URL scheme; defaulting to psql for backward compatibility"
    PAGER=cat psql "$DB_URL" -v ON_ERROR_STOP=1 -1 -f "$MIGRATION_FILE" | tee "$log_file"
    ;;
esac

echo "Migration applied successfully."

if [[ "$RECORD_FLAG" == "--record" ]]; then
  if [[ ! -f "$EVIDENCE_LOG" ]]; then
    echo "Warning: evidence log not found at $EVIDENCE_LOG" >&2
    exit 0
  fi
  timestamp="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  {
    echo "- ${timestamp} — Migration 003 applied via scripts/ops/apply_stage_b_migration.sh"
  } >> "$EVIDENCE_LOG"
  echo "Recorded migration evidence entry in $EVIDENCE_LOG"
fi
