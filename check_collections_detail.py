import chromadb
import os

client = chromadb.HttpClient(host='chromadb', port=8000)
try:
    collections = client.list_collections()
    for col in collections:
        print(f"Collection: {col.name}")
        try:
            print(f"  Count: {col.count()}")
            # To get dimensions, we might need to look at an item or metadata
            print(f"  Metadata: {col.metadata}")
        except Exception as e:
            print(f"  Error getting count/metadata: {e}")
except Exception as e:
    print(f"Error listing collections: {e}")
