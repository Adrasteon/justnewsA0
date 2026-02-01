#!/bin/bash
set -e

echo "=== JustNews Reset & Reset Protocol ==="

# 1. Stop Services
echo ">>> Stopping Services..."
systemctl --user stop vllm-qwen-14b.service || echo "vllm already stopped"
# Kill all agent python processes (excluding this script)
pkill -f "agents\..*\.main" || echo "No agents running"
pkill -f "uvicorn" || echo "No uvicorn running"
pkill -f "start_services_daemon.sh" || echo "Daemon not running"

# 2. Filesystem Cleanup
echo ">>> Cleaning Filesystem..."
rm -f db.sqlite3 dump.rdb
# Clear directories but keep the dir itself
find logs/ -type f -delete
find archive_storage/raw_html/ -type f -delete
find archive_storage/transparency/ -type f -delete
find output/ -type f -delete
find agents -name "__pycache__" -type d -exec rm -rf {} +

# 3. Database Cleanup
echo ">>> Resetting MariaDB..."
# Load env vars
set -a
source global.env
set +a

mariadb -u $MARIADB_USER -p"$MARIADB_PASSWORD" -e "DROP DATABASE IF EXISTS $MARIADB_DB; CREATE DATABASE $MARIADB_DB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 4. Redis Cleanup
echo ">>> Flushing Redis..."
redis-cli FLUSHALL || echo "Redis flush failed (maybe not running?)"

# 5. Re-Initialize Database
echo ">>> Applying Schema..."
# Activate conda
source /home/adra/miniconda3/etc/profile.d/conda.sh
conda activate justnews-py312
python apply_migrations_script.py
# rm apply_migrations_script.py

# 6. Restart Services
echo ">>> Restarting Services..."
systemctl --user start vllm-qwen-14b.service

echo "Waiting for vLLM to warm up (10s)..."
# sleep 10

echo "Starting Agents..."
nohup scripts/ops/start_services_daemon.sh > logs/orchestrator.log 2>&1 &

# Explicitly start Crawler (missing from manifest?)
echo "Starting Crawler Agent..."
# Assuming port 8015 from global.env
source global.env
nohup python -m agents.crawler.main --port $CRAWLER_AGENT_PORT > logs/crawler.log 2>&1 &
nohup python -m agents.journalist.main --port $JOURNALIST_PORT > logs/journalist.log 2>&1 &

echo "Waiting for agents to stabilize (15s)..."
sleep 15

# 7. Initiate Crawl
echo ">>> Initiating Full Crawl..."
python run_full_crawl.py

echo "=== Reset Complete ==="
