"""
Async database operations for JustNews
Provides async database operations using asyncpg for non-blocking operations
"""

from common.observability import get_logger
from database.utils.migrated_database_utils import (
    create_database_service,
    execute_query_async,
)

logger = get_logger(__name__)

# Use migrated database utils for async work by delegating to their executor-based
# helpers rather than relying on asyncpg/postgres.


async def execute_async_query(query: str, *args, fetch: bool = True):
    """Execute a MariaDB query asynchronously using the migrated DB service."""
    service = create_database_service()
    # migrated utils expects params as tuple; convert *args accordingly
    params = tuple(args) if args else None
    return await execute_query_async(service, query, params, fetch)


async def execute_async_query_single(query: str, *args):
    """Execute a query and return a single row asynchronously."""
    rows = await execute_async_query(query, *args, fetch=True)
    if not rows:
        return None
    return rows[0]


async def async_health_check() -> bool:
    """Perform an async health check against the migrated MariaDB service."""
    try:
        r = await execute_async_query_single("SELECT 1")
        if isinstance(r, dict):
            # dict-like row
            return any(v == 1 for v in r.values())
        if isinstance(r, (list, tuple)):
            return r[0] == 1
        return False
    except Exception as e:
        logger.error(f"Async database health check failed: {e}")
        return False


async def close_async_pool():
    # No-op: migrated service lifecycle is managed by the service instance
    pass
