
import requests
import sys
import os
import time

# Add project root to path
sys.path.append(os.getcwd())
from database.utils.migrated_database_utils import create_database_service

ANALYST_URL = "http://localhost:8004"

def get_unanalyzed_ids():
    db = create_database_service()
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM articles WHERE analyzed = 0 OR analyzed IS NULL LIMIT 50") # Limit to 50 for test
    return [row[0] for row in cursor.fetchall()]

def trigger_analysis(article_id):
    url = f"{ANALYST_URL}/analyze_article"
    payload = {
        "name": "analyze_article",
        "args": [],
        "kwargs": {"article_id": article_id}
    }
    try:
        print(f"Triggering analysis for article {article_id}...")
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            print(f"Success: {resp.json()}")
            return True
        else:
            print(f"Failed ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        print(f"Error triggering {article_id}: {e}")
        return False

def main():
    print("Fetching unanalyzed articles...")
    ids = get_unanalyzed_ids()
    print(f"Found {len(ids)} unanalyzed articles (capped at 50).")
    
    success_count = 0
    for aid in ids:
        if trigger_analysis(aid):
            success_count += 1
        time.sleep(0.5) # Gentle spacing
        
    print(f"Completed backfill. Successfully triggered: {success_count}/{len(ids)}")

if __name__ == "__main__":
    main()
