import os
import sys

import mysql.connector

# Add project root to path
sys.path.insert(0, os.getcwd())

from database.utils.migrated_database_utils import get_db_config


def describe_schema():
    config = get_db_config()
    mb_config = config['mariadb']

    conn = mysql.connector.connect(
        host=mb_config['host'],
        port=mb_config['port'],
        user=mb_config['user'],
        database=mb_config['database'],
        password=mb_config['password'],
        use_pure=True
    )

    cursor = conn.cursor(dictionary=True)

    # 1. List all tables
    print("=== Tables in Database ===")
    cursor.execute("SHOW TABLES")
    tables = [list(r.values())[0] for r in cursor.fetchall()]
    print(tables)
    print("\n")

    # 2. Describe SOURCES table
    print("=== Describe SOURCES ===")
    try:
        cursor.execute("DESCRIBE sources")
        for col in cursor.fetchall():
           print(col)
    except Exception as e:
        print(f"Error describing sources: {e}")

    print("\n")

    # 3. Check for specific sources columns issues (e.g. if domain is unique, types)
    print("=== Sources Create Statement ===")
    try:
        cursor.execute("SHOW CREATE TABLE sources")
        res = cursor.fetchone()
        if res:
            print(res['Create Table'])
    except Exception as e:
        print(f"Error getting create table: {e}")

    print("\n")

    # 4. Same for ARTICLES table just in case
    print("=== Describe ARTICLES ===")
    try:
        cursor.execute("DESCRIBE articles")
        for col in cursor.fetchall():
           print(col)
    except Exception as e:
        print(f"Error describing articles: {e}")

    conn.close()

if __name__ == "__main__":
    describe_schema()
