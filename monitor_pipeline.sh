#!/bin/bash
# Pipeline Dataflow Monitor - Shell-based monitoring
# Queries database via Django shell and captures output

LOGFILE="/tmp/pipeline_dataflow.log"

{
    echo "=========================================="
    echo "PIPELINE DATAFLOW MONITORING STARTED"
    echo "Time: $(date)"
    echo "=========================================="
    echo ""
    
    cd /app
    source /app/.venv/bin/activate
    
    # Initial snapshot
    echo "[BASELINE - T+0s]"
    python3 manage.py shell << 'DJANGO_SHELL'
from django.db import connection

cursor = connection.cursor()

queries = {
    'sources': 'SELECT COUNT(*) FROM sources',
    'articles': 'SELECT COUNT(*) FROM articles',
    'embedded_articles': 'SELECT COUNT(*) FROM articles WHERE embedded=1',
    'clustered_articles': 'SELECT COUNT(*) FROM articles WHERE cluster_id IS NOT NULL',
    'embeddings': 'SELECT COUNT(*) FROM embeddings_document',
    'clusters': 'SELECT COUNT(DISTINCT cluster_id) FROM articles WHERE cluster_id IS NOT NULL',
    'living_stories': 'SELECT COUNT(*) FROM living_stories',
    'synthesized': 'SELECT COUNT(*) FROM synthesized_articles',
    'pending_critique': 'SELECT COUNT(*) FROM synthesized_articles WHERE critique_status="pending"',
}

for key, query in queries.items():
    try:
        cursor.execute(query)
        result = cursor.fetchone()[0]
        print(f"{key:20s}: {result}")
    except Exception as e:
        print(f"{key:20s}: ERROR - {e}")
DJANGO_SHELL
    
    echo ""
    echo "[WAITING 30 SECONDS...]"
    sleep 30
    
    echo ""
    echo "[UPDATE - T+30s]"
    python3 manage.py shell << 'DJANGO_SHELL'
from django.db import connection

cursor = connection.cursor()

queries = {
    'sources': 'SELECT COUNT(*) FROM sources',
    'articles': 'SELECT COUNT(*) FROM articles',
    'embedded_articles': 'SELECT COUNT(*) FROM articles WHERE embedded=1',
    'clustered_articles': 'SELECT COUNT(*) FROM articles WHERE cluster_id IS NOT NULL',
    'embeddings': 'SELECT COUNT(*) FROM embeddings_document',
    'clusters': 'SELECT COUNT(DISTINCT cluster_id) FROM articles WHERE cluster_id IS NOT NULL',
    'living_stories': 'SELECT COUNT(*) FROM living_stories',
    'synthesized': 'SELECT COUNT(*) FROM synthesized_articles',
    'pending_critique': 'SELECT COUNT(*) FROM synthesized_articles WHERE critique_status="pending"',
}

for key, query in queries.items():
    try:
        cursor.execute(query)
        result = cursor.fetchone()[0]
        print(f"{key:20s}: {result}")
    except Exception as e:
        print(f"{key:20s}: ERROR - {e}")
DJANGO_SHELL
    
    echo ""
    echo "[WAITING 30 SECONDS...]"
    sleep 30
    
    echo ""
    echo "[UPDATE - T+60s]"
    python3 manage.py shell << 'DJANGO_SHELL'
from django.db import connection

cursor = connection.cursor()

queries = {
    'sources': 'SELECT COUNT(*) FROM sources',
    'articles': 'SELECT COUNT(*) FROM articles',
    'embedded_articles': 'SELECT COUNT(*) FROM articles WHERE embedded=1',
    'clustered_articles': 'SELECT COUNT(*) FROM articles WHERE cluster_id IS NOT NULL',
    'embeddings': 'SELECT COUNT(*) FROM embeddings_document',
    'clusters': 'SELECT COUNT(DISTINCT cluster_id) FROM articles WHERE cluster_id IS NOT NULL',
    'living_stories': 'SELECT COUNT(*) FROM living_stories',
    'synthesized': 'SELECT COUNT(*) FROM synthesized_articles',
    'pending_critique': 'SELECT COUNT(*) FROM synthesized_articles WHERE critique_status="pending"',
}

for key, query in queries.items():
    try:
        cursor.execute(query)
        result = cursor.fetchone()[0]
        print(f"{key:20s}: {result}")
    except Exception as e:
        print(f"{key:20s}: ERROR - {e}")
DJANGO_SHELL
    
    echo ""
    echo "=========================================="
    echo "MONITORING COMPLETE"
    echo "=========================================="

} | tee "$LOGFILE"

echo "Log saved to: $LOGFILE"
