"""
Database connection utilities for JustNews
Provides connection pooling and async database operations
"""

import os
from contextlib import contextmanager

from common.dev_db_fallback import apply_test_db_env_fallback
from common.env_loader import load_global_env

# psycopg2 removed: use migrated MariaDB utilities instead
from common.observability import get_logger
from database.utils.migrated_database_utils import (
    create_database_service,
    execute_mariadb_query,
)

# Configure centralized logging
logger = get_logger(__name__)


# Environment variables (read at runtime, not import time)
def get_db_config():
    """Get database configuration from environment variables"""
    # Load global.env file first (development environments often rely on the repo-local copy)
    load_global_env(logger=logger)

    # Apply development fallback credentials if required
    applied = apply_test_db_env_fallback(logger)
    if applied:
        logger.warning(
            "Development DB fallback variables applied: %s", ",".join(applied)
        )

    # Use MariaDB-style environment variables for the migrated storage backend.
    config = {
        "host": os.environ.get("MARIADB_HOST"),
        "database": os.environ.get("MARIADB_DB"),
        "user": os.environ.get("MARIADB_USER"),
        "password": os.environ.get("MARIADB_PASSWORD"),
    }

    # If any are missing, try to parse DATABASE_URL
    if not all(config.values()):
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            logger.info("Parsing database configuration from DATABASE_URL")
            try:
                from urllib.parse import urlparse

                parsed = urlparse(database_url)
                config["host"] = parsed.hostname or config["host"]
                config["database"] = parsed.path.lstrip("/") or config["database"]
                config["user"] = parsed.username or config["user"]
                config["password"] = parsed.password or config["password"]
                if parsed.port:
                    config["port"] = parsed.port
            except Exception as e:
                logger.warning(f"Failed to parse DATABASE_URL: {e}")

    return config


# Global migrated DB service instance
_db_service = None


def initialize_database_service():
    """Initialize and return the migrated MariaDB/Chroma database service.

    This replaces the old Postgres-specific connection pool. It is idempotent.
    """
    global _db_service
    if _db_service is not None:
        return _db_service

    # Ensure environment variables from global.env are loaded when present
    try:
        load_global_env(logger=logger)
    except Exception:
        # Non-fatal if the env file is missing
        pass

    _db_service = create_database_service()
    logger.info("Migrated DatabaseService initialized (MariaDB + Chroma)")
    return _db_service


def initialize_connection_pool():
    """Compatibility shim for older callers that expect initialize_connection_pool.

    Returns the migrated DatabaseService (MariaDB + Chroma).
    """
    return initialize_database_service()


@contextmanager
def get_db_connection():
    """Context manager yielding a low-level MariaDB connection object.

    Yields the mysql.connector connection (service.mb_conn) so callers that
    previously used a psycopg2 connection can operate with a DB-agnostic API.
    """
    service = initialize_database_service()
    conn = service.mb_conn
    try:
        yield conn
    finally:
        # Do not close pooled connection here; the service manages lifecycle
        pass


@contextmanager
def get_db_cursor(commit: bool = False, dictionary: bool = True):
    """Context manager for getting a cursor from the migrated DB service.

    Args:
        commit: whether to commit on exit
        dictionary: return rows as dicts when supported
    """
    service = initialize_database_service()
    # Prefer a per-call connection + cursor to avoid sharing resultsets across
    # concurrent callers which may lead to 'Unread result found' in mysql-connector.
    cursor, conn = service.get_safe_cursor(
        per_call=True, dictionary=dictionary, buffered=True
    )
    try:
        yield conn, cursor
        if commit:
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def execute_query(query: str, params: tuple = None, fetch: bool = True):
    """Execute a MariaDB query via the migrated database service.

    Returns fetched rows when fetch=True, otherwise returns None.
    """
    service = initialize_database_service()
    results = execute_mariadb_query(service, query, params, fetch)
    return results


def execute_query_single(query: str, params: tuple = None):
    """Execute a query and return a single result row as dict or tuple."""
    rows = execute_query(query, params, fetch=True)
    if not rows:
        return None
    # mysql.connector with dictionary=True returns dicts; fallback to tuple
    first = rows[0]
    return first


def health_check() -> bool:
    """Perform a basic MariaDB health check using the migrated service."""
    try:
        service = initialize_database_service()
        cursor, conn = service.get_safe_cursor(per_call=True, buffered=True)
        try:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
        return bool(result and result[0] == 1)
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


def close_connection_pool():
    """Close the migrated database service (if present)."""
    global _db_service
    if _db_service:
        try:
            _db_service.close()
        except Exception:
            pass
        _db_service = None
