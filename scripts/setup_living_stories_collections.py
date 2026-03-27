import os
import sys

# Ensure repo root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from chromadb.config import Settings

import chromadb

try:
    from common.observability import get_logger
    logger = get_logger("setup_living_stories")
except ImportError as e:
    print(f"Warning: Could not import logger ({e}), falling back to print.")
    class Logger:
        def info(self, msg): print(f"[INFO] {msg}")
        def error(self, msg): print(f"[ERROR] {msg}")
    logger = Logger()

def setup_chroma():
    host = os.environ.get("CHROMADB_HOST", "localhost")
    port = int(os.environ.get("CHROMADB_PORT", "8000"))

    logger.info(f"Connecting to Chroma at {host}:{port}")

    try:
        client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=Settings(allow_reset=True, anonymized_telemetry=False)
        )
    except Exception as e:
        logger.error(f"Failed to create HttpClient: {e}")
        return

    collection_name = "active_living_stories"

    try:
        # Check if exists
        try:
            client.get_collection(collection_name)
            logger.info(f"Collection '{collection_name}' already exists.")
        except Exception:
            # Create it
            # We use cosine similarity as per plan
            client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"Created collection '{collection_name}'.")

    except Exception as e:
        logger.error(f"Error managing collection: {e}")

if __name__ == "__main__":
    setup_chroma()
