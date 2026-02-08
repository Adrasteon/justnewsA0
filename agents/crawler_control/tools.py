"""
Tools and utilities for the Crawler Control Agent.
"""

from database.utils.migrated_database_utils import create_database_service


def get_sources_with_limit(limit: int = None) -> list[str]:
    """Get active sources from database, optionally limited"""
    try:
        db_service = create_database_service()

        query = """
            SELECT domain
            FROM sources
            WHERE last_verified IS NOT NULL
            AND last_verified > DATE_SUB(NOW(), INTERVAL 30 DAY)
            ORDER BY last_verified DESC, name ASC
        """
        if limit:
            query += f" LIMIT {limit}"

        cursor = db_service.mb_conn.cursor(dictionary=True)
        cursor.execute(query)
        sources = cursor.fetchall()
        cursor.close()
        db_service.close()

        domains = [source["domain"] for source in sources]
        return domains

    except Exception as e:
        from common.observability import get_logger

        logger = get_logger(__name__)
        logger.error(f"❌ Failed to query sources from database: {e}")
        return []
