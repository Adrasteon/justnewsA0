
import mysql.connector
import time

config = {
    'user': 'justnews',
    'password': 'justnews_password',
    'host': '127.0.0.1',
    'database': 'justnews',
    'port': 3306
}

def check():
    try:
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        
        cursor.execute("SELECT count(*) FROM articles WHERE is_synthesized = 1")
        synth_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT count(*) FROM orchestrator_jobs WHERE status='processing'")
        active_jobs = cursor.fetchone()[0]
        
        print(f"Synthesized: {synth_count} | Active Jobs: {active_jobs}")
        conn.close()
    except Exception as e:
        print(e)

if __name__ == "__main__":
    for i in range(3):
        print(f"--- T={i*5}s ---")
        check()
        if i < 2:
            time.sleep(5)
