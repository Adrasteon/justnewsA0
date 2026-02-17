
import sys

import chromadb


def check_chroma():
    print(f"ChromaDB Library Version: {chromadb.__version__}")
    try:
        # Assuming http client based on port 3307 being open
        client = chromadb.HttpClient(host='localhost', port=3307)
        print("Attempting heartbeat...")
        print(f"Heartbeat: {client.heartbeat()}")
        print("Attempting to list collections...")
        cols = client.list_collections()
        print(f"Collections: {cols}")
        print("SUCCESS: Connected via library")
    except Exception as e:
        print(f"FAILURE: {e}")
        sys.exit(1)

if __name__ == "__main__":
    check_chroma()
