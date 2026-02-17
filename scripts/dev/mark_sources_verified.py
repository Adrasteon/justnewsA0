#!/usr/bin/env python3
"""Mark a selection of database sources as verified by setting last_verified = NOW().

Usage: scripts/dev/mark_sources_verified.py [--limit N]

This script uses the repository's `database.utils.migrated_database_utils` service
so it will respect `/etc/justnews/global.env` or repo `global.env` configuration.
"""

import argparse

from database.utils.migrated_database_utils import (
    create_database_service,
    execute_mariadb_query,
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of sources to mark as verified (default 100)",
    )
    args = p.parse_args()

    svc = create_database_service()
    query = f"UPDATE sources SET last_verified = NOW() WHERE last_verified IS NULL LIMIT {args.limit};"
    print(f"Running: {query}")
    _ = execute_mariadb_query(svc, query, fetch=False)

    # Report how many rows are now verified (approximation)
    rows = execute_mariadb_query(
        svc, "SELECT COUNT(*) FROM sources WHERE last_verified IS NOT NULL"
    )
    count = rows[0][0] if rows else 0
    print(f"Sources with last_verified NOT NULL: {count}")


if __name__ == "__main__":
    main()
