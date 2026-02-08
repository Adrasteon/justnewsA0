import os
import sys

sys.path.insert(0, os.getcwd())
from database.utils.migrated_database_utils import create_database_service


def debug_tools():
    try:
        db_service = create_database_service()
        print(f"Connected to DB: {db_service.config['database']['mariadb']['database']}")

        query = """
            SELECT domain, last_verified
            FROM sources
            WHERE last_verified IS NOT NULL
            AND last_verified > DATE_SUB(NOW(), INTERVAL 30 DAY)
            ORDER BY last_verified DESC, name ASC
        """
        limit = 10
        if limit:
            query += f" LIMIT {limit}"

        print(f"Executing query: {query}")

        cursor = db_service.mb_conn.cursor(dictionary=True)
        cursor.execute(query)
        sources = cursor.fetchall()
        print(f"Found {len(sources)} sources.")
        for s in sources:
             print(f"- {s['domain']} ({s['last_verified']})")

        cursor.close()
        db_service.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_tools()
