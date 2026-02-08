import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from database.utils.migrated_database_utils import create_database_service

def check_status():
    print("=== Checking Database Status ===")
    
    try:
        db = create_database_service()
        
        # 1. Check MariaDB
        print("\n[MariaDB]")
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SHOW TABLES")
        tables = [t[0] for t in cursor.fetchall()]
        print(f"Tables found ({len(tables)}): {', '.join(tables)}")
        
        if 'sources' in tables:
            cursor.execute("SELECT COUNT(*) FROM sources")
            count = cursor.fetchone()[0]
            print(f"Sources count: {count}")
            
        if 'articles' in tables:
            cursor.execute("SELECT COUNT(*) FROM articles")
            count = cursor.fetchone()[0]
            print(f"Articles count: {count}")

        # 2. Check ChromaDB
        print("\n[ChromaDB]")
        # The service exposes chroma_client
        chroma = db.chroma_client
        if chroma:
            try:
                heartbeat = chroma.heartbeat()
                print(f"Heartbeat: {heartbeat} (Connection OK)")
                
                collections = chroma.list_collections()
                print(f"Collections found ({len(collections)}): {[c.name for c in collections]}")
                
                for c in collections:
                    print(f" - Collection '{c.name}' count: {c.count()}")
            except Exception as e:
                print(f"Error communicating with ChromaDB: {e}")
        else:
            print("ChromaDB client not initialized.")
            
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_status()
