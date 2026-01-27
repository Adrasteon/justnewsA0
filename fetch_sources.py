import os
import sys

# Hardcoded fallback since env loading is flaky or complicated
# Taking values from logs/previous context if visible, or relying on correct env
# The logs showed Access Denied for justnews_user@localhost but also "Connected to MariaDB" when env var was set.
# I will use the MigrateDatabaseService via python.

sys.path.append(os.getcwd())
os.environ["JUSTNEWS_DISABLE_TEST_DB_FALLBACK"] = "1"

from database.utils.migrated_database_utils import create_database_service


def get_domains():
    print("Connecting...")
    db = create_database_service()
    db.ensure_conn()
    conn = db.get_connection()
    cursor = conn.cursor()

    # Try to find table name. It might be 'sources' or something else
    cursor.execute("SHOW TABLES")
    tables = [t[0] for t in cursor.fetchall()]
    print(f"Tables: {tables}")

    if 'sources' in tables:
        # Check columns of articles
        cursor.execute("DESCRIBE articles")
        columns = [(c[0], c[1]) for c in cursor.fetchall()]
        print(f"Articles columns: {columns}")

        # Try to select just domains without filter first
        cursor.execute("SELECT domain FROM sources LIMIT 10")
        domains = [r[0] for r in cursor.fetchall()]
        print(f"Found {len(domains)} active domains: {domains}")
        return domains
    else:
        print("Table 'sources' not found.")
        return []

if __name__ == "__main__":
    get_domains()
