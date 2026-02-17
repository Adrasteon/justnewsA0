import os
import sys
import mysql.connector
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv("/app/global.env")

def inspect_schema():
    host = os.getenv("MARIADB_HOST", "mariadb")
    port = int(os.getenv("MARIADB_PORT", 3306))
    user = os.getenv("MARIADB_USER", "justnews")
    password = os.getenv("MARIADB_PASSWORD", "dev_justnews_password")
    database = os.getenv("MARIADB_DB", "justnews")
    
    try:
        conn = mysql.connector.connect(host=host, port=port, user=user, password=password, database=database)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("DESCRIBE articles")
        rows = cursor.fetchall()
        print(f"{'Field':<30} {'Type':<20} {'Null':<5} {'Key':<5} {'Default':<10}")
        print("-" * 80)
        for row in rows:
            print(f"{row['Field']:<30} {row['Type']:<20} {row['Null']:<5} {row['Key']:<5} {str(row['Default']):<10}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_schema()
