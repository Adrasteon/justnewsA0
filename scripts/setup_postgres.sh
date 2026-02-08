#!/usr/bin/env bash
set -euo pipefail

# scripts/setup_postgres.sh
# DEPRECATED and REMOVED: Postgres is no longer supported by JustNews.
#
# This script previously bootstrapped a local PostgreSQL installation and
# applied schema/migrations. The project has migrated to MariaDB and an
# alternative Docker-based PoC and DB-init workflows are available:
#   - scripts/dev/docker-compose.e2e.yml (MariaDB + Redis)
#   - scripts/dev/db-seed/justnews_init.sql (seed SQL for tests)
#   - scripts/init_database.py (application DB initialization for MariaDB)
#
# Keep this file as a stub so calling the script is a harmless no-op that
# informs developers/operators about the migration and alternative tooling.

echo "ERROR: 'setup_postgres.sh' is deprecated and removed — Postgres is no longer the primary DB for JustNews."
echo "JustNews now uses MariaDB as the supported primary database. In production and most developer setups MariaDB runs on the host (outside Docker) — the project assumes a system-level MariaDB service or managed DB instance."
echo "A Docker Compose-based MariaDB image is provided for lightweight testing/CI only: scripts/dev/docker-compose.e2e.yml (MariaDB + Redis)."
echo "To initialize the database schema for your environment, use scripts/init_database.py (works against host MariaDB)."
echo "If you are migrating an old deployment, export MARIADB_* environment variables and run scripts/init_database.py to set up schema for MariaDB."

exit 0
