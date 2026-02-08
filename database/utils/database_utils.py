"""
Database Utilities - Advanced Implementation
Utility functions for database operations and configuration management

Features:
- Configuration Management: Database configuration loading and validation
- Async Operations: Asynchronous database operations support
- Transaction Management: Database transaction handling utilities
- Connection Utilities: Connection testing and health checking
"""

import asyncio
import os
from importlib import import_module
from typing import Any

from common.env_loader import load_global_env
from common.observability import get_logger

from ..core.connection_pool import DatabaseConnectionPool

logger = get_logger(__name__)


def _get_compat_attr(name: str, default):
    """Retrieve an attribute from the compatibility shim if available."""

    try:
        compat_module = import_module("database.refactor.utils.database_utils")
    except Exception:
        return default

    return getattr(compat_module, name, default)


def get_db_config() -> dict[str, Any]:
    """
    Get database configuration from environment variables

    Returns:
        Database configuration dictionary
    """
    # Load any global.env files while preserving process environment variables
    # so tests can inject an early override via JUSTNEWS_GLOBAL_ENV.
    try:
        load_global_env(logger=logger)
    except Exception:
        # Defensive: continue even if env loading failed for unexpected reasons
        logger.debug(
            "Failed to load global env via load_global_env(); will rely on current environment"
        )

    # Get database configuration
    config = {
        # Prefer MariaDB environment variables by default; if Postgres vars are present
        # (for backward compatibility) they can still be used as a fallback.
        "host": os.environ.get(
            "MARIADB_HOST", os.environ.get("POSTGRES_HOST", "localhost")
        ),
        "port": int(
            os.environ.get("MARIADB_PORT", os.environ.get("POSTGRES_PORT", "3306"))
        ),
        "database": os.environ.get(
            "MARIADB_DB", os.environ.get("POSTGRES_DB", "justnews")
        ),
        "user": os.environ.get(
            "MARIADB_USER", os.environ.get("POSTGRES_USER", "justnews")
        ),
        "password": os.environ.get(
            "MARIADB_PASSWORD", os.environ.get("POSTGRES_PASSWORD", "")
        ),
        "min_connections": int(os.environ.get("DB_MIN_CONNECTIONS", "1")),
        "max_connections": int(os.environ.get("DB_MAX_CONNECTIONS", "20")),
        "health_check_interval": int(os.environ.get("DB_HEALTH_CHECK_INTERVAL", "30")),
        "max_retries": int(os.environ.get("DB_MAX_RETRIES", "3")),
        "retry_delay": float(os.environ.get("DB_RETRY_DELAY", "1.0")),
    }

    # Parse DATABASE_URL if provided (overrides individual settings)
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        logger.info("Parsing database configuration from DATABASE_URL")
        try:
            from urllib.parse import urlparse

            parsed = urlparse(database_url)

            config.update(
                {
                    "host": parsed.hostname or config["host"],
                    "port": parsed.port or config["port"],
                    "database": parsed.path.lstrip("/") or config["database"],
                    "user": parsed.username or config["user"],
                    "password": parsed.password or config["password"],
                }
            )
        except Exception as e:
            logger.warning(f"Failed to parse DATABASE_URL: {e}")

    # Validate required fields
    required_fields = ["host", "database", "user", "password"]
    missing_fields = [field for field in required_fields if not config.get(field)]

    if missing_fields:
        raise ValueError(
            f"Missing required database configuration fields: {missing_fields}"
        )

    return config


def create_connection_pool(
    config: dict[str, Any] | None = None,
) -> DatabaseConnectionPool:
    """
    Create and initialize database connection pool

    Args:
        config: Database configuration (uses get_db_config() if not provided)

    Returns:
        Initialized DatabaseConnectionPool instance
    """
    if config is None:
        config = get_db_config()

    pool_class = _get_compat_attr("DatabaseConnectionPool", DatabaseConnectionPool)
    connection_checker = _get_compat_attr("check_connection", check_connection)

    pool = pool_class(config)

    # Test connection
    connection_checker(pool)

    return pool


def check_connection(pool: DatabaseConnectionPool) -> bool:
    """
    Check database connection

    Args:
        pool: Database connection pool to check

    Returns:
        True if connection successful
    """
    try:
        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 as test")
            result = cursor.fetchone()
            cursor.close()

            if result and result[0] == 1:
                logger.info("Database connection test successful")
                return True
            else:
                logger.error("Database connection test failed - unexpected result")
                return False

    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False


async def execute_query_async(
    pool: DatabaseConnectionPool, query: str, params: tuple = None, fetch: bool = True
) -> list:
    """
    Execute database query asynchronously

    Args:
        pool: Database connection pool
        query: SQL query string
        params: Query parameters
        fetch: Whether to fetch results

    Returns:
        Query results or empty list
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, pool.execute_query, query, params, fetch)


def execute_transaction(
    pool: DatabaseConnectionPool, queries: list, params_list: list | None = None
) -> bool:
    """
    Execute multiple queries in a database transaction

    Args:
        pool: Database connection pool
        queries: List of SQL queries
        params_list: List of parameter tuples (optional)

    Returns:
        True if transaction successful
    """
    if params_list is None:
        params_list = [None] * len(queries)

    if len(queries) != len(params_list):
        raise ValueError("queries and params_list must have the same length")

    try:
        with pool.get_connection() as conn:
            cursor = conn.cursor()

            # Use strict zip to ensure both lists have the same length (defensive)
            for query, params in zip(queries, params_list, strict=True):
                cursor.execute(query, params or ())

            conn.commit()
            cursor.close()

            logger.info(
                f"Transaction executed successfully with {len(queries)} queries"
            )
            return True

    except Exception as e:
        logger.error(f"Transaction failed: {e}")
        return False


def get_database_stats(pool: DatabaseConnectionPool) -> dict[str, Any]:
    """
    Get comprehensive database statistics

    Args:
        pool: Database connection pool

    Returns:
        Database statistics dictionary
    """
    stats = {
        "connection_pool": pool.get_metrics(),
        "tables": {},
        "total_size": 0,
        "total_rows": 0,
    }

    try:
        # Get table information
        table_query = """
        SELECT
            schemaname,
            tablename,
            n_tup_ins as inserts,
            n_tup_upd as updates,
            n_tup_del as deletes,
            n_live_tup as live_rows,
            n_dead_tup as dead_rows,
            pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
        FROM pg_stat_user_tables
        ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
        """

        table_results = pool.execute_query(table_query)

        for table in table_results:
            table_name = table["tablename"]
            stats["tables"][table_name] = {
                "inserts": table["inserts"],
                "updates": table["updates"],
                "deletes": table["deletes"],
                "live_rows": table["live_rows"],
                "dead_rows": table["dead_rows"],
                "size": table["size"],
            }

            stats["total_rows"] += table["live_rows"]

        # Get database size
        size_query = (
            "SELECT pg_size_pretty(pg_database_size(current_database())) as db_size"
        )
        size_result = pool.execute_query(size_query)
        if size_result:
            stats["total_size"] = size_result[0]["db_size"]

    except Exception as e:
        logger.warning(f"Failed to get database stats: {e}")

    return stats


def vacuum_analyze_table(pool: DatabaseConnectionPool, table_name: str) -> bool:
    """
    Perform VACUUM ANALYZE on a table to update statistics and reclaim space

    Args:
        pool: Database connection pool
        table_name: Name of table to vacuum

    Returns:
        True if successful
    """
    try:
        query = f"VACUUM ANALYZE {table_name}"
        pool.execute_query(query, fetch=False)
        logger.info(f"VACUUM ANALYZE completed for table {table_name}")
        return True
    except Exception as e:
        logger.error(f"VACUUM ANALYZE failed for table {table_name}: {e}")
        return False


def reindex_table(pool: DatabaseConnectionPool, table_name: str) -> bool:
    """
    Reindex a table to rebuild indexes

    Args:
        pool: Database connection pool
        table_name: Name of table to reindex

    Returns:
        True if successful
    """
    try:
        query = f"REINDEX TABLE {table_name}"
        pool.execute_query(query, fetch=False)
        logger.info(f"REINDEX completed for table {table_name}")
        return True
    except Exception as e:
        logger.error(f"REINDEX failed for table {table_name}: {e}")
        return False


def get_slow_queries(
    pool: DatabaseConnectionPool, limit: int = 10, min_duration: float = 1.0
) -> list:
    """
    Get slow running queries from pg_stat_activity

    Args:
        pool: Database connection pool
        limit: Maximum number of queries to return
        min_duration: Minimum query duration in seconds

    Returns:
        List of slow queries
    """
    try:
        query = """
        SELECT
            pid,
            usename,
            client_addr,
            query_start,
            state_change,
            EXTRACT(epoch FROM (now() - query_start)) as duration,
            substring(query, 1, 100) as query_preview
        FROM pg_stat_activity
        WHERE state = 'active'
        AND query NOT LIKE '%pg_stat_activity%'
        AND EXTRACT(epoch FROM (now() - query_start)) > %s
        ORDER BY duration DESC
        LIMIT %s
        """

        results = pool.execute_query(query, (min_duration, limit))
        return results

    except Exception as e:
        logger.warning(f"Failed to get slow queries: {e}")
        return []


def kill_query(pool: DatabaseConnectionPool, pid: int) -> bool:
    """
    Terminate a running query by PID

    Args:
        pool: Database connection pool
        pid: Process ID of the query to terminate

    Returns:
        True if successful
    """
    try:
        query = "SELECT pg_terminate_backend(%s)"
        result = pool.execute_query(query, (pid,))
        success = result and result[0]["pg_terminate_backend"]
        if success:
            logger.info(f"Terminated query with PID {pid}")
        else:
            logger.warning(f"Failed to terminate query with PID {pid}")
        return success
    except Exception as e:
        logger.error(f"Failed to terminate query {pid}: {e}")
        return False
