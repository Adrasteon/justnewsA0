
import os
import sys
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from database.utils.migrated_database_utils import create_database_service

def check_latest_arrival():
    try:
        db_service = create_database_service()
        db_service.ensure_conn()
        cursor = db_service.mb_conn.cursor()
        
        # Get the absolute newest article created_at
        query = "SELECT MAX(created_at) FROM articles"
        cursor.execute(query)
        latest = cursor.fetchone()[0]
        
        print(f"Latest Article Timestamp: {latest}")
        
        if latest:
             now = datetime.now()
             # If aware/naive mismatch, handle it strictly if needed, but for print we assume naive or compatible
             print(f"Current System Time:    {now}")
             
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_latest_arrival()
