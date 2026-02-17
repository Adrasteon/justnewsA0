#!/bin/bash
source /app/.venv/bin/activate
date > /app/schema_log.txt
python3 -u /app/apply_factual_schema_lite.py >> /app/schema_log.txt 2>&1
echo "Done with update" >> /app/schema_log.txt
python3 -u /app/verify_factual_schema.py >> /app/schema_log.txt 2>&1
