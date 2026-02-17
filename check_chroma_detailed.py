import chromadb
import os

def check_chroma():
    host = 'chromadb'
    port = 8000
    tenant = 'default_tenant'
    
    client = chromadb.HttpClient(host=host, port=port, tenant=tenant)
    
    print(f"Checking tenant: {tenant}")
    collections = client.list_collections()
    for c in collections:
        print(f"Collection: {c.name}")
        print(f"  Count: {c.count()}")
        print(f"  Metadata: {c.metadata}")

    # Explicitly check for names mentioned in docs
    targets = [
        "articles__all-MiniLM-L6-v2__384",
        "articles__BAAI_bge-large-en-v1_5__1024",
        "fact_checks_vector"
    ]
    
    for target in targets:
        try:
            col = client.get_collection(target)
            print(f"✅ Found {target}: {col.count()} items")
        except Exception:
            print(f"❌ {target} not found in this tenant")

if __name__ == "__main__":
    check_chroma()
