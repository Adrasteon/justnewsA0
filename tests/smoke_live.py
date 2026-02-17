"""
Live Smoke Test for "Heavy Lifters" (DB & LLM)
Usage: python tests/smoke_live.py

This script verifies:
1. Real connection to the configured MariaDB.
2. Ability to load the Mistral-7B model into VRAM via vLLM.
"""

import multiprocessing
import os
import sys

import pymysql

# Set start method to 'spawn' for CUDA compatibility in vLLM/PyTorch
# This must be done before any other modules (like torch) are imported/used
try:
    multiprocessing.set_start_method('spawn', force=True)
except RuntimeError:
    pass

# Ensure we can import system modules if needed
sys.path.append(os.getcwd())

def load_env_file(path):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                if key not in os.environ:
                    os.environ[key] = val

# Load env vars
load_env_file("global.env")
load_env_file("secrets.env")

def test_database_connection():
    print("\n[DB] Testing MariaDB connection...")
    host = os.environ.get("MARIADB_HOST", "127.0.0.1")
    port = int(os.environ.get("MARIADB_PORT", 3306))
    user = os.environ.get("MARIADB_USER", "justnews")
    password = os.environ.get("MARIADB_PASSWORD", "")
    database = os.environ.get("MARIADB_DB", "justnews")

    try:
        conn = pymysql.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port,
            connect_timeout=5
        )
        print(f"[SUCCESS] Connected to {database}@{host}")
        conn.close()
        return True
    except pymysql.MySQLError as err:
        print(f"[FAIL] Database connection failed: {err}")
        return False
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        return False
    return False

def test_vllm_load():
    print("\n[LLM] Testing vLLM Model Loading (Qwen 2.5 14B AWQ)...")

    model_name = os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ")
    print(f"Target Model: {model_name}")

    try:
        # NOTE: We avoid 'import torch; torch.cuda.is_available()' here because
        # initializing CUDA in the main process before vLLM forks/spawns workers
        # can cause "Cannot re-initialize CUDA in forked subprocess" errors.
        # We rely on vLLM to detect the GPU or fail.
        from vllm import LLM
        # Initialize LLM with conservative memory settings to avoid OOM if other things are running
        # but enough to prove it works.
        llm = LLM(
            model=model_name,
            dtype="auto",
            gpu_memory_utilization=0.75, # Use 75% to ensure model fits (13.5GB+) + KV Cache
            max_model_len=2048 # Restrict context handling for startup speed
        )
        print("[SUCCESS] vLLM initialized successfully")

        # Optional: Run a tiny inference?
        # output = llm.generate(["Hello, are you working?"])
        # print(f"Output: {output[0].outputs[0].text}")

        # For now, just initialization is enough to prove VRAM fit
        return True
    except Exception as e:
        print(f"[FAIL] vLLM crashed: {e}")
        return False

def main():
    print("=== LIVE SMOKE TEST ===")

    db_ok = test_database_connection()
    llm_ok = test_vllm_load()

    if db_ok and llm_ok:
        print("\n>>> ALL SYSTEMS GO <<<")
        sys.exit(0)
    else:
        print("\n>>> SMOKE TEST FAILED <<<")
        sys.exit(1)

if __name__ == "__main__":
    main()
