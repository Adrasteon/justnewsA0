import os
import sys

sys.path.insert(0, os.getcwd())
from database.utils.migrated_database_utils import create_database_service


def check():
    db = create_database_service()
    conn = db.mb_conn
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT count(*) as c FROM sources")
    count = cursor.fetchone()['c']
    print(f"Total sources: {count}")

    cursor.execute("SELECT * FROM sources LIMIT 5")
    rows = cursor.fetchall()
    for r in rows:
        print(r)

    # Check the query logic
    print("Checking query logic...")
    query = """
        SELECT domain, last_verified
        FROM sources
        WHERE last_verified IS NOT NULL
        AND last_verified > DATE_SUB(NOW(), INTERVAL 30 DAY)
        ORDER BY last_verified DESC, name ASC
        LIMIT 10
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    print(f"Query returned {len(rows)} rows.")
    for r in rows:
        print(r)

    db.close()

if __name__ == "__main__":
    check()
