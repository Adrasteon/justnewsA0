#!/usr/bin/env python3
"""
Pipeline Dataflow Monitor - Comprehensive monitoring across all pipeline stages
Monitors: Crawler → Ingestion → Embedding → Clustering → Synthesis → Critique
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime

# Add app to path
sys.path.insert(0, '/app')

# Load environment
for line in Path('/app/global.env').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1)
        os.environ[k] = v

def get_db_connection():
    """Create and return database connection"""
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host=os.environ.get('MARIADB_HOST'),
            user=os.environ.get('MARIADB_USER'),
            password=os.environ.get('MARIADB_PASSWORD'),
            database=os.environ.get('MARIADB_DB'),
            autocommit=True
        )
        return conn
    except Exception as e:
        print(f"❌ DB Connection failed: {e}")
        return None

def check_pipeline_metrics():
    """Check all pipeline stage metrics"""
    conn = get_db_connection()
    if not conn:
        return None
    
    cursor = conn.cursor()
    metrics = {}
    
    try:
        # Stage 1: Source coverage
        cursor.execute("SELECT COUNT(*) FROM sources")
        metrics['sources_total'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM sources WHERE last_crawl_at IS NOT NULL")
        metrics['sources_crawled'] = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME='articles'
              AND COLUMN_NAME='source_id'
        """)
        has_source_id = cursor.fetchone()[0] > 0
        if has_source_id:
            cursor.execute("SELECT COUNT(DISTINCT source_id) FROM articles WHERE source_id IS NOT NULL")
            metrics['sources_with_articles'] = cursor.fetchone()[0]
        else:
            metrics['sources_with_articles'] = 0
        
        # Stage 2: Articles ingested
        cursor.execute("SELECT COUNT(*) FROM articles")
        metrics['articles_total'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM articles WHERE embedded=1")
        metrics['articles_embedded'] = cursor.fetchone()[0]
        
        # In this schema, clustering info is in story_updates and living_stories
        metrics['articles_clustered'] = 0 # Placeholder if not directly in articles table
        
        # Stage 3: Embeddings
        cursor.execute("SELECT COUNT(*) FROM embeddings_document")
        metrics['embeddings_recorded'] = cursor.fetchone()[0]
        
        # Stage 4: Clusters (represented by living_stories/story_updates)
        cursor.execute("SELECT COUNT(*) FROM living_stories")
        metrics['clusters_created'] = cursor.fetchone()[0]
        
        # Stage 5: Living stories
        metrics['living_stories'] = metrics['clusters_created']
        
        # Stage 6: Synthesized articles
        cursor.execute("SELECT COUNT(*) FROM synthesized_articles")
        metrics['synthesized_articles'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM synthesized_articles WHERE critique_status='pending'")
        metrics['pending_critique'] = cursor.fetchone()[0]
        
        # Migration status
        cursor.execute("SELECT COUNT(*) FROM schema_migrations WHERE version LIKE '015%' OR version LIKE '016%'")
        metrics['migrations_applied'] = cursor.fetchone()[0]
        
        # Recently added articles (last 5 minutes)
        cursor.execute("SELECT COUNT(*) FROM articles WHERE created_at > DATE_SUB(NOW(), INTERVAL 5 MINUTE)")
        metrics['recent_articles'] = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        return metrics
        
    except Exception as e:
        print(f"❌ Query error: {e}")
        cursor.close()
        conn.close()
        return None

def check_agent_status():
    """Check if key agents are running"""
    import subprocess
    
    agents = {
        'crawler': 8022,
        'memory': 8007,
        'workflow_orchestrator': 8023,
        'analyst': 8004,
        'synthesizer': 8005,
        'critic': 8006
    }
    
    status = {}
    
    for agent_name, port in agents.items():
        try:
            result = subprocess.run(
                ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', f'http://localhost:{port}/health'],
                timeout=2,
                capture_output=True
            )
            status[agent_name] = result.returncode == 0
        except:
            status[agent_name] = False
    
    return status

def print_pipeline_report(metrics, iteration=1):
    """Print formatted pipeline status report"""
    if not metrics:
        print("❌ Unable to retrieve metrics")
        return
    
    print(f"\n{'='*70}")
    print(f"PIPELINE DATAFLOW REPORT - Iteration {iteration}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    print("📊 STAGE METRICS:")
    sources_total = metrics.get('sources_total', 0)
    sources_crawled = metrics.get('sources_crawled', 0)
    sources_with_articles = metrics.get('sources_with_articles', 0)
    print(f"  Sources crawled:              {sources_crawled:>5}/{sources_total}")
    print(f"  Sources with articles:        {sources_with_articles:>5}/{sources_total}")
    print(f"  Articles ingested:            {metrics.get('articles_total', 0):>5}")
    print(f"    - Embedded:                 {metrics.get('articles_embedded', 0):>5}")
    print(f"    - Clustered:                {metrics.get('articles_clustered', 0):>5}")
    print(f"  Embeddings recorded:          {metrics.get('embeddings_recorded', 0):>5}")
    print(f"  Clusters created:             {metrics.get('clusters_created', 0):>5}")
    print(f"  Living stories:               {metrics.get('living_stories', 0):>5}")
    print(f"  Synthesized articles:         {metrics.get('synthesized_articles', 0):>5}")
    print(f"    - Pending critique:         {metrics.get('pending_critique', 0):>5}")
    print(f"  Recent articles (5m):         {metrics.get('recent_articles', 0):>5}")
    
    print(f"\n🔧 SYSTEM STATUS:")
    print(f"  Migrations (015, 016):        {metrics.get('migrations_applied', 0)}/2")
    
    # Determine pipeline flow status
    print(f"\n🔄 PIPELINE FLOW:")
    stages = [
        ("Crawler",     metrics.get('sources_crawled', 0) > 0),
        ("Ingestion",   metrics.get('articles_total', 0) > 0),
        ("Embedding",   metrics.get('articles_embedded', 0) > 0),
        ("Clustering",  metrics.get('articles_clustered', 0) > 0),
        ("Synthesis",   metrics.get('living_stories', 0) > 0),
        ("Critique",    metrics.get('synthesized_articles', 0) > 0)
    ]
    
    for stage_name, is_active in stages:
        status_icon = "✅" if is_active else "⏳"
        print(f"  {status_icon} {stage_name}")

def main():
    """Main monitoring loop"""
    print("🚀 Pipeline Dataflow Monitor Started")
    print(f"Starting at: {datetime.now()}")
    print("Monitoring in 10-second intervals...\n")
    
    iteration = 0
    prev_metrics = None
    
    try:
        while True:
            iteration += 1
            metrics = check_pipeline_metrics()
            
            if metrics:
                print_pipeline_report(metrics, iteration)
                
                # Check for changes
                if prev_metrics:
                    changes = []
                    for key in metrics:
                        if metrics[key] != prev_metrics.get(key, 0):
                            changes.append(f"{key}: {prev_metrics.get(key, 0)} → {metrics[key]}")
                    
                    if changes:
                        print(f"\n📈 CHANGES DETECTED:")
                        for change in changes:
                            print(f"  • {change}")
                
                prev_metrics = metrics
            
            # Wait before next check
            time.sleep(10)
            
    except KeyboardInterrupt:
        print(f"\n\n⏹️ Monitoring stopped at {datetime.now()}")
        sys.exit(0)

if __name__ == '__main__':
    main()
