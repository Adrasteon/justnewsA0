
import os
import sys
import chromadb

# Add root to python path to use any local helpers if needed
sys.path.append('/app')

def list_chroma_details():
    host = os.environ.get('CHROMADB_HOST', 'chromadb')
    port = int(os.environ.get('CHROMADB_PORT', 8000))
    
    print(f"Connecting to ChromaDB at {host}:{port}...")
    try:
        # Use HttpClient which is standard in recent Chroma versions
        client = chromadb.HttpClient(host=host, port=port)
        collections = client.list_collections()
        
        print(f"\nFound {len(collections)} collections:")
        for coll in collections:
            count = coll.count()
            print(f" - Collection: {coll.name}")
            print(f"   Items: {count}")
            print(f"   Metadata: {coll.metadata}")
            
            # Sample one item if count > 0 to see dimensions
            if count > 0:
                peek = coll.peek(limit=1)
                if peek and peek['embeddings'] and len(peek['embeddings']) > 0:
                    print(f"   Embedding Dimension: {len(peek['embeddings'][0])}")
            print("-" * 30)
            
    except Exception as e:
        print(f"Error connecting to ChromaDB: {e}")

if __name__ == "__main__":
    list_chroma_details()
