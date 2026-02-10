#!/usr/bin/env python3
"""
Comprehensive crawler and pipeline monitoring script.
Tracks data flow from source -> crawler -> articles -> embeddings -> processing.
"""
import os
import sys
import json
import time
import requests
from datetime import datetime
from collections import defaultdict

sys.path.append(os.getcwd())
os.environ["JUSTNEWS_DISABLE_TEST_DB_FALLBACK"] = "1"

from database.utils.migrated_database_utils import create_database_service


class PipelineMonitor:
    def __init__(self, check_interval=5, max_duration=3600):
        self.db = create_database_service()
        self.db.ensure_conn()
        self.check_interval = check_interval
        self.max_duration = max_duration
        self.start_time = time.time()
        self.metrics = defaultdict(list)
        self.errors = []
        
    def get_connection(self):
        return self.db.get_connection()
    
    def query_metric(self, query_name, query):
        """Execute query and return result"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query)
            result = cursor.fetchall()
            cursor.close()
            conn.close()
            return result
        except Exception as e:
            self.errors.append(f"[{query_name}] {str(e)}")
            return None
    
    def check_pipeline_status(self):
        """Monitor all pipeline tables"""
        status = {
            'timestamp': datetime.now().isoformat(),
            'elapsed': time.time() - self.start_time,
        }
        
        # Crawl metrics
        result = self.query_metric("crawl_tasks", "SELECT COUNT(*) FROM crawler_tasks")
        status['crawl_tasks'] = result[0][0] if result else 0
        
        result = self.query_metric("crawl_articles", "SELECT COUNT(*) FROM crawler_task_articles")
        status['crawl_articles'] = result[0][0] if result else 0
        
        # Articles in main pipeline
        result = self.query_metric("articles_count", "SELECT COUNT(*) FROM articles")
        status['articles_ingested'] = result[0][0] if result else 0
        
        # Embeddings status
        result = self.query_metric("embeddings", "SELECT COUNT(*) FROM embeddings_document WHERE document_id IS NOT NULL")
        status['embeddings_completed'] = result[0][0] if result else 0
        
        result = self.query_metric("embeddings_total", "SELECT COUNT(*) FROM embeddings_document")
        status['embeddings_total'] = result[0][0] if result else 0
        
        # Processing status
        result = self.query_metric("nltk_models", "SELECT COUNT(*) FROM nltk_model_results")
        status['nlp_processed'] = result[0][0] if result else 0
        
        result = self.query_metric("clustering", "SELECT COUNT(*) FROM article_clusters")
        status['clustered'] = result[0][0] if result else 0
        
        result = self.query_metric("canonical_status", "SELECT COUNT(*) FROM canonical_status_check")
        status['canonical_checked'] = result[0][0] if result else 0
        
        # API health check
        status['crawler_health'] = self.check_agent_health(8022)
        status['mcp_bus_health'] = self.check_agent_health(8000)
        
        self.metrics['status'].append(status)
        return status
    
    def check_agent_health(self, port):
        """Check if agent is responding"""
        try:
            resp = requests.get(f"http://localhost:{port}/health", timeout=2)
            return "✓" if resp.status_code == 200 else f"✗({resp.status_code})"
        except:
            return "✗(unreachable)"
    
    def print_status(self, status):
        """Pretty print pipeline status"""
        elapsed = int(status['elapsed'])
        mins, secs = divmod(elapsed, 60)
        
        print(f"\n{'='*80}")
        print(f"PIPELINE STATUS @ {status['timestamp']} (+{mins}m {secs}s)")
        print(f"{'='*80}")
        
        print(f"\n📊 CRAWLING:")
        print(f"   Crawl Tasks:        {status['crawl_tasks']:6d}")
        print(f"   Articles Discovered: {status['crawl_articles']:6d}")
        
        print(f"\n📰 INGESTION:")
        print(f"   Articles Ingested:  {status['articles_ingested']:6d}")
        
        print(f"\n🔍 EMBEDDINGS:")
        print(f"   Total:              {status['embeddings_total']:6d}")
        print(f"   With embeddings:    {status['embeddings_completed']:6d}")
        
        print(f"\n💬 NLP PROCESSING:")
        print(f"   Processed:          {status['nlp_processed']:6d}")
        
        print(f"\n🎯 CLUSTERING:")
        print(f"   Clustered:          {status['clustered']:6d}")
        print(f"   Canonical Checked:  {status['canonical_checked']:6d}")
        
        print(f"\n🏥 SERVICE HEALTH:")
        print(f"   Crawler (8022):     {status['crawler_health']}")
        print(f"   MCP Bus (8000):     {status['mcp_bus_health']}")
    
    def print_errors(self):
        """Print any errors encountered"""
        if self.errors:
            print(f"\n⚠️  ERRORS ENCOUNTERED ({len(self.errors)}):")
            for error in self.errors[-10:]:  # Show last 10
                print(f"   • {error}")
    
    def run_crawl(self, domains, max_articles=10, concurrent_sites=3):
        """Trigger the crawl"""
        print(f"\n🚀 STARTING CRAWL")
        print(f"   Domains:           {len(domains)}")
        print(f"   Max articles/site: {max_articles}")
        print(f"   Concurrent sites:  {concurrent_sites}")
        
        payload = {
            "name": "unified_production_crawl",
            "args": [],
            "kwargs": {
                "domains": domains,
                "max_articles_per_site": max_articles,
                "concurrent_sites": concurrent_sites
            }
        }
        
        try:
            resp = requests.post(
                "http://localhost:8022/unified_production_crawl",
                json=payload,
                timeout=30
            )
            
            if resp.status_code == 202:
                job_info = resp.json()
                print(f"   ✓ Job started: {job_info.get('job_id', 'N/A')}")
                print(f"   Status: {job_info.get('status', 'pending')}")
                return True
            else:
                print(f"   ✗ Failed: {resp.status_code}")
                print(f"   Response: {resp.text[:200]}")
                return False
        except Exception as e:
            print(f"   ✗ Exception: {e}")
            return False
    
    def monitor_pipeline(self):
        """Main monitoring loop"""
        print("\n" + "="*80)
        print("JUSTNEWS PIPELINE MONITORING")
        print("="*80)
        
        # Fetch domains
        print("\n📍 Fetching source domains...")
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT domain FROM sources")
        domains = [r[0] for r in cursor.fetchall()]
        cursor.close()
        conn.close()
        print(f"   ✓ Found {len(domains)} domains")
        
        # Start crawl
        if not self.run_crawl(domains):
            print("✗ Failed to start crawl")
            return False
        
        # Monitor loop
        print("\n⏳ MONITORING PIPELINE (Ctrl+C to stop)")
        print("   Checking every {} seconds...".format(self.check_interval))
        
        last_status = {}
        check_count = 0
        
        try:
            while time.time() - self.start_time < self.max_duration:
                check_count += 1
                status = self.check_pipeline_status()
                
                # Print if there's change in key metrics
                changed = False
                for key in ['crawl_tasks', 'crawl_articles', 'articles_ingested', 
                           'embeddings_completed', 'nlp_processed', 'clustered']:
                    if key not in last_status or last_status[key] != status[key]:
                        changed = True
                        break
                
                if changed or check_count == 1:
                    self.print_status(status)
                    last_status = status.copy()
                
                # Print errors if any
                if len(self.errors) > last_status.get('_last_error_count', 0):
                    self.print_errors()
                    last_status['_last_error_count'] = len(self.errors)
                
                # Wait before next check
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            print("\n\n⏹️  Monitoring stopped by user")
        
        # Final status
        print("\n" + "="*80)
        print("FINAL PIPELINE STATUS")
        print("="*80)
        final_status = self.check_pipeline_status()
        self.print_status(final_status)
        self.print_errors()
        
        return True


def main():
    # Start monitoring (1 hour max)
    monitor = PipelineMonitor(check_interval=5, max_duration=3600)
    monitor.monitor_pipeline()


if __name__ == "__main__":
    main()
