
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from database.utils.migrated_database_utils import create_database_service

def check_status():
    try:
        db = create_database_service()
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Total
        cursor.execute("SELECT count(*) FROM articles")
        total = cursor.fetchone()[0]
        print(f"Total articles: {total}")
        
        # Analyzed
        cursor.execute("SELECT count(*) FROM articles WHERE analyzed = 1")
        analyzed = cursor.fetchone()[0]
        print(f"Analyzed articles: {analyzed}")
        
        # Summarized
        cursor.execute("SELECT count(*) FROM articles WHERE summary IS NOT NULL AND summary != ''")
        summarized = cursor.fetchone()[0]
        print(f"Summarized articles: {summarized}")
        
        # Fact Checked
        cursor.execute("SELECT count(*) FROM articles WHERE fact_check_status IS NOT NULL AND fact_check_status != '' AND fact_check_status != 'pending'")
        fact_checked = cursor.fetchone()[0]
        print(f"Fact Checked articles: {fact_checked}")
        
        # Fact Check Status breakdown
        cursor.execute("SELECT fact_check_status, count(*) FROM articles GROUP BY fact_check_status")
        fc_stats = cursor.fetchall()
        print(f"Fact Check Breakdown: {fc_stats}")

        # Synthesized
        cursor.execute("SELECT count(*) FROM articles WHERE is_synthesized = 1")
        synthesized_sources = cursor.fetchone()[0]
        print(f"Synthesized source articles: {synthesized_sources}")

        cursor.execute("SELECT count(*) FROM synthesized_articles")
        stories = cursor.fetchone()[0]
        print(f"Generated Stories: {stories}")
        
        # Critiqued
        try:
             cursor.execute("SELECT count(*) FROM synthesized_articles WHERE critique_status = 'completed'")
             critiqued = cursor.fetchone()[0]
             print(f"Critiqued Stories: {critiqued}")
        except Exception as e:
             print(f"Critiqued Stories Check Failed: {e}")

        # Published
        cursor.execute("SELECT count(*) FROM synthesized_articles WHERE is_published = 1")
        published = cursor.fetchone()[0]
        print(f"Published Stories: {published}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_status()
