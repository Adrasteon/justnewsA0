import mysql.connector
import os

def fix_verdict_schema():
    host = os.getenv("MARIADB_HOST", "mariadb")
    port = int(os.getenv("MARIADB_PORT", 3306))
    user = os.getenv("MARIADB_USER", "justnews")
    password = os.getenv("MARIADB_PASSWORD", "dev_justnews_password")
    database = os.getenv("MARIADB_DB", "justnews")
    
    conn = mysql.connector.connect(host=host, port=port, user=user, password=password, database=database)
    cursor = conn.cursor()
    
    print("Altering fact_checks table: Modify 'verdict' to VARCHAR(50)...")
    try:
        # Change ENUM to VARCHAR to support new 5-point scale "Likely True" etc.
        cursor.execute("ALTER TABLE fact_checks MODIFY verdict VARCHAR(50)")
        conn.commit()
        print("Success.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_verdict_schema()
