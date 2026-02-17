import mysql.connector
import os
import json
import textwrap

def get_db_conn():
    host = os.getenv("MARIADB_HOST", "mariadb")
    port = int(os.getenv("MARIADB_PORT", 3306))
    user = os.getenv("MARIADB_USER", "justnews")
    password = os.getenv("MARIADB_PASSWORD", "dev_justnews_password")
    database = os.getenv("MARIADB_DB", "justnews")
    return mysql.connector.connect(host=host, port=port, user=user, password=password, database=database)

def inspect_fact_checks():
    conn = get_db_conn()
    cursor = conn.cursor(dictionary=True)
    
    # Get recent analyzed articles with scores
    print("Fetching recent fact checks...\n")
    cursor.execute("""
        SELECT id, title, source_url, factual_accuracy_score, fact_check_details
        FROM articles
        WHERE analyzed = 1 AND fact_check_details IS NOT NULL
        ORDER BY updated_at DESC
        LIMIT 5
    """)
    
    rows = cursor.fetchall()
    
    for row in rows:
        print(f"=== Article {row['id']}: {row['title']} ===")
        print(f"URL: {row['source_url']}")
        print(f"Score: {row['factual_accuracy_score']}")
        
        details = row['fact_check_details']
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except:
                print("Error parsing JSON details")
                continue
        
        if not details:
            print("No details JSON.")
            continue
            
        print("\n--- Verdict Breakdown ---")
        # Handle "fact_check_details" structure from Analyst/Tools
        # structure: { "score": ..., "details": ..., "verdicts": [...] }
        verdicts = details.get("verdicts", [])
        
        for i, v in enumerate(verdicts):
            # v contains 'claim', 'fact_check' -> which contains 'verdict', 'explanation'
            claim = v.get("claim", "N/A")
            fc = v.get("fact_check", {})
            verdict = fc.get("verdict", "Unknown")
            confidence = fc.get("confidence", 0.0)
            explanation = fc.get("explanation", "No explanation")
            
            print(f"\nClaim {i+1}: {textwrap.shorten(claim, width=150)}")
            print(f"Verdict: {verdict} (Conf: {confidence})")
            print(f"Explanation: {textwrap.shorten(explanation, width=300)}")
            
        print("\n" + "="*80 + "\n")

    conn.close()

if __name__ == "__main__":
    inspect_fact_checks()
