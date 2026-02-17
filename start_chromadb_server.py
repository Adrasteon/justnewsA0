#!/usr/bin/env python3
"""
Start ChromaDB server for embeddings storage.

ChromaDB runs as an HTTP API on port 3307 (as per canonical port mapping).
"""

import os
import sys
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("chromadb-server")

try:
    import chromadb
    from chromadb.server.fastapi import app
    import uvicorn
    
    logger.info("🚀 Starting ChromaDB server...")
    
    # Start ChromaDB HTTP server on port 3307
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=3307,
        log_level="info"
    )
    
except ImportError as e:
    logger.error(f"❌ Failed to import ChromaDB: {e}")
    sys.exit(1)
except Exception as e:
    logger.error(f"❌ Failed to start ChromaDB server: {e}")
    sys.exit(1)
