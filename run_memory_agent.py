import os
import sys

# Ensure root is in path
sys.path.insert(0, os.getcwd())

# Set env vars
os.environ["JUSTNEWS_DISABLE_TEST_DB_FALLBACK"] = "1"
os.environ["FORCE_CPU"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # Force torch to see no GPUs
os.environ["MEMORY_HOST"] = "0.0.0.0"
os.environ["MEMORY_PORT"] = "8007"

print("Starting Memory Agent via wrapper...")
import uvicorn

from agents.memory.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8007)
