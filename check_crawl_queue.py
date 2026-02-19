import os
import sys
import json

sys.path.append(os.getcwd())
try:
    from database.utils.migrated_database_utils import create_database_service
except ImportError:
    print("Could not import create_database_service")
    sys.exit(1)

def check_queue():
    print("=== Checking Crawl Queue Status ===")
    try:
        db = create_database_service()
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SHOW TABLES LIKE 'crawler_jobs'")
        if not cursor.fetchone():
            print("Table 'crawler_jobs' does not exist.")
            return

        cursor.execute("DESCRIBE crawler_jobs")
        columns = [c[0] for c in cursor.fetchall()]

        # Columns to select
        cols_to_select = ["job_id" if "job_id" in columns else "id", 
                          "status", 
                          "sources_processed", 
                          "articles_collected", 
                          "created_at", 
                          "job_metadata" if "job_metadata" in columns else "metadata"]
        
        valid_cols = [c for c in cols_to_select if c in columns]
        
        # Add special columns
        special_cols = []
        if 'result' in columns: special_cols.append('result')
        if 'options' in columns: special_cols.append('options')
        if 'source_url' in columns: special_cols.append('source_url')
        
        final_cols = valid_cols + [c for c in special_cols if c not in valid_cols]

        query = f"SELECT {', '.join(final_cols)} FROM crawler_jobs ORDER BY created_at DESC LIMIT 5"
        print(f"Executing: {query}")
        
        cursor.execute(query)
        jobs = cursor.fetchall()
        
        print(f"\n[Latest 5 Crawler Jobs]")
        print(f"{' | '.join([f'{c:<20}' for c in final_cols])}")
        print("-" * 150)
        
        for job in jobs:
            row_items = []
            for val in job:
                val_str = str(val)
                if len(val_str) > 500:
                    val_str = val_str[:497] + "..."
                row_items.append(val_str)
            print(" | ".join([f"{item}" for item in row_items]))
            print("-" * 150)

        # Check total article count
        print("\n[Current DB Stats]")
        cursor.execute("SELECT COUNT(*) FROM articles")
        count = cursor.fetchone()[0]
        print(f"Total Articles in DB: {count}")

        cursor.execute("SELECT COUNT(*) FROM sources")
        sources_total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM sources WHERE last_crawl_at IS NOT NULL")
        sources_crawled = cursor.fetchone()[0]
        print(f"Sources Crawled: {sources_crawled}/{sources_total}")

        sources_with_articles = 0
        cursor.execute("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME='articles'
              AND COLUMN_NAME='source_id'
        """)
        if cursor.fetchone()[0] > 0:
            cursor.execute("SELECT COUNT(DISTINCT source_id) FROM articles WHERE source_id IS NOT NULL")
            sources_with_articles = cursor.fetchone()[0]
        print(f"Sources With Articles: {sources_with_articles}/{sources_total}")

        # Check pending/running jobs
        print("\n[Active Jobs]")
        cursor.execute("SELECT count(*) FROM crawler_jobs WHERE status IN ('pending', 'running')")
        active = cursor.fetchone()[0]
        print(f"Active Jobs count: {active}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_queue()
