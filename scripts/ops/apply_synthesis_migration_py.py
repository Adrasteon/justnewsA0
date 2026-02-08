#!/usr/bin/env python3
"""Apply synthesis migration SQL files using Python DB connector.

This is used as a fallback when the system mysql/mariadb client can't be
used (for example plugin/auth issues). It reads migrations paths and applies
them sequentially against the configured MariaDB instance.

Usage: source global.env; python3 scripts/ops/apply_synthesis_migration_py.py
"""

import logging
import os
import sys
import time
from pathlib import Path

# Prefer mysql.connector if available (C-extension) because it supports multi-statement execution
MYSQL_CONNECTOR_AVAILABLE = True
try:
    import mysql.connector
except Exception:
    MYSQL_CONNECTOR_AVAILABLE = False

# Fallback to pure-Python pymysql if mysql.connector isn't available or fails
PYMYSQL_AVAILABLE = True
try:
    import pymysql
except Exception:
    PYMYSQL_AVAILABLE = False


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = [
    REPO_ROOT / "database" / "migrations" / "004_add_synthesis_fields.sql",
    REPO_ROOT / "database" / "migrations" / "005_create_synthesized_articles_table.sql",
    REPO_ROOT / "database" / "migrations" / "006_create_synthesizer_jobs_table.sql",
]

LOG_DIR = REPO_ROOT / "logs" / "operations" / "migrations"
LOG_DIR.mkdir(parents=True, exist_ok=True)

timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
log_file = LOG_DIR / f"migration_{timestamp}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
)


def get_conn_cfg():
    # prefer JUSTNEWS_DB_URL if provided
    db_url = os.environ.get("JUSTNEWS_DB_URL") or os.environ.get("DB_URL")
    if db_url:
        # attempt simplistic parsing assuming mysql://user:pass@host:port/db
        if db_url.startswith("mysql://") or db_url.startswith("mariadb://"):
            parsed = db_url.split("://", 1)[1]
            userpass, hostpath = parsed.split("@", 1) if "@" in parsed else ("", parsed)
            user, password = (
                (userpass.split(":", 1) + [""])[:2] if userpass else ("", "")
            )
            hostport, dbname = (hostpath.split("/", 1) + [""])[:2]
            host, port = (hostport.split(":", 1) + ["3306"])[:2]
            return {
                "user": user or os.environ.get("MARIADB_USER", ""),
                "password": password or os.environ.get("MARIADB_PASSWORD", ""),
                "host": host or os.environ.get("MARIADB_HOST", "127.0.0.1"),
                "port": int(port or os.environ.get("MARIADB_PORT", 3306)),
                "database": dbname or os.environ.get("MARIADB_DB", "justnews"),
            }

    # fallback to MARIADB_* env vars in global.env
    return {
        "user": os.environ.get("MARIADB_USER", "justnews"),
        "password": os.environ.get("MARIADB_PASSWORD", ""),
        "host": os.environ.get("MARIADB_HOST", "127.0.0.1"),
        "port": int(os.environ.get("MARIADB_PORT", 3306)),
        "database": os.environ.get("MARIADB_DB", "justnews"),
    }


def run():
    cfg = get_conn_cfg()

    logging.info(
        "Using DB host=%s port=%s db=%s user=%s",
        cfg["host"],
        cfg["port"],
        cfg["database"],
        cfg["user"],
    )

    conn = None
    cursor = None
    used_connector = None
    # Try mysql.connector first
    if MYSQL_CONNECTOR_AVAILABLE:
        try:
            conn = mysql.connector.connect(
                host=cfg["host"],
                port=cfg["port"],
                user=cfg["user"],
                password=cfg["password"],
                database=cfg["database"],
            )
            conn.autocommit = False
            cursor = conn.cursor()
            logging.info("Connected via mysql.connector")
            used_connector = "mysql_connector"
        except Exception:
            logging.exception(
                "mysql.connector failed to connect; will try pymysql fallback"
            )

    # Try pymysql as fallback (pure Python, usually avoids local client plugin issues)
    if conn is None and PYMYSQL_AVAILABLE:
        try:
            conn = pymysql.connect(
                host=cfg["host"],
                port=cfg["port"],
                user=cfg["user"],
                password=cfg["password"],
                database=cfg["database"],
                autocommit=False,
            )
            cursor = conn.cursor()
            logging.info("Connected via pymysql")
            used_connector = "pymysql"
        except Exception:
            logging.exception("pymysql failed to connect as well")

    if conn is None:
        logging.error(
            "Could not connect to MariaDB via mysql.connector or pymysql. Aborting."
        )
        sys.exit(2)

    # If we connected via mysql.connector earlier we already have a cursor
    if cursor is None:
        cursor = conn.cursor()

    try:
        use_mysql_connector = used_connector == "mysql_connector" or (
            MYSQL_CONNECTOR_AVAILABLE and conn.__class__.__module__.startswith("mysql")
        )
        use_pymysql = used_connector == "pymysql" or (
            PYMYSQL_AVAILABLE and conn.__class__.__module__.startswith("pymysql")
        )

        for migration in MIGRATIONS:
            migration = Path(migration)
            if not migration.exists():
                logging.error("Migration file not found: %s", migration)
                continue
            logging.info("Applying %s", migration)
            sql = migration.read_text(encoding="utf-8")
            try:
                if use_mysql_connector:
                    for _result in cursor.execute(sql, multi=True):
                        # consume results
                        pass
                    conn.commit()
                elif use_pymysql:
                    # PyMySQL cursor doesn't support multi=True; execute statements sequentially.
                    # Strip SQL comments and split on semicolons safely for our migrations.
                    statements = []
                    cleaned = []
                    for line in sql.splitlines():
                        # remove SQL line comments starting with --
                        if line.strip().startswith("--"):
                            continue
                        cleaned.append(line)
                    joined = "\n".join(cleaned)
                    # naively split on semicolons; migrations here are safe for this.
                    for stmt in joined.split(";"):
                        stmt = stmt.strip()
                        if not stmt:
                            continue
                        statements.append(stmt)

                    for stmt in statements:
                        cursor.execute(stmt)
                    conn.commit()
                else:
                    logging.error("No supported DB client available to execute SQL")
                    raise RuntimeError("No DB client")

                logging.info("Applied %s", migration)
            except Exception:
                logging.exception("Failed to apply %s", migration)
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise

    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    run()
