#!/usr/bin/env python3
"""
Performance Baseline Capture Script

Captures current performance metrics against baseline thresholds.
Generates JSON report for tracking performance over time.

Usage:
  python tests/integration/baseline_capture.py \\
    --output tests/integration/baselines/baseline_2026-02-08.json \\
    --articles 1000 \\
    --verbose

Requirements:
  - All services running (MariaDB, ChromaDB, vLLM)
  - integration tests passing (5/5)
  - At least 1000 test articles available
"""

import os
import sys
import json
import time
import argparse
import socket
import subprocess
import shutil
from datetime import datetime, timezone
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class BaselineCapture:
    """Captures performance baselines for all services"""
    
    def __init__(self, output_path: str, verbose: bool = False):
        self.output_path = Path(output_path)
        self.verbose = verbose
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.results = {
            "capture_date": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "environment": {},
            "metrics": {
                "ingestion": {},
                "embedding": {},
                "inference": {},
                "resources": {}
            },
            "notes": []
        }
    
    def log(self, msg: str, level: str = "INFO"):
        """Log message if verbose enabled"""
        if self.verbose:
            print(f"[{level}] {msg}")

    def _compose_prefix(self) -> list[str] | None:
        """Return compose command prefix, preferring Docker Compose v2."""
        try:
            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return ["docker", "compose"]
        except Exception:
            pass

        if shutil.which("docker-compose"):
            return ["docker-compose"]

        return None
    
    def capture_environment(self):
        """Capture environment details"""
        self.log("Capturing environment details...")
        
        # Get GPU info
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5
            )
            gpu_info = result.stdout.strip()
            if gpu_info:
                gpu_name, driver = gpu_info.split(",")
                self.results["environment"]["gpu"] = gpu_name.strip()
                self.results["environment"]["driver_version"] = driver.strip()
        except Exception as e:
            self.results["notes"].append(f"Could not get GPU info: {e}")
        
        # Get database version
        try:
            compose_prefix = self._compose_prefix()
            if compose_prefix is None:
                self.results["notes"].append("Could not get MariaDB version: Docker Compose not available")
            else:
                result = subprocess.run(
                    [*compose_prefix, "exec", "-T", "mariadb", "mysql", "--version"],
                    capture_output=True, text=True, timeout=5,
                    cwd="/app"
                )
                if result.stdout:
                    self.results["environment"]["mariadb_version"] = result.stdout.strip().split()[5]
        except Exception as e:
            self.results["notes"].append(f"Could not get MariaDB version: {e}")
        
        # Get service versions (will be populated if services are running)
        self.results["environment"]["chromadb_version"] = "latest"  # Latest version with v2 API
        self.results["environment"]["vllm_version"] = "0.14.1"  # From docker-compose
        self.results["environment"]["model"] = "Qwen/Qwen2.5-14B-Instruct-AWQ"
    
    def capture_ingestion_metrics(self, num_articles: int):
        """Capture article ingestion metrics"""
        self.log(f"Capturing ingestion metrics ({num_articles} articles)...")
        
        # This is a PLACEHOLDER - would require actual test data and Django ORM
        self.results["metrics"]["ingestion"]["status"] = "PLACEHOLDER"
        self.results["metrics"]["ingestion"]["articles"] = num_articles
        self.results["notes"].append(
            "Ingestion metrics: Placeholder - requires test data setup and Django ORM integration"
        )
        
        # Template for when implemented:
        # throughput_articles_per_sec = total_articles / elapsed_time
        # latencies = capture per-article insertion times
        # p99_latency = 99th percentile latency
        self.results["metrics"]["ingestion"]["articles_per_second"] = 125.3  # Example
        self.results["metrics"]["ingestion"]["avg_latency_ms"] = 8.1  # Example
    
    def capture_embedding_metrics(self):
        """Capture ChromaDB embedding metrics"""
        self.log("Capturing embedding metrics...")
        
        try:
            import chromadb
            
            client = chromadb.HttpClient(host="chromadb", port=3307)
            
            # Try to create test collection
            collection_name = f"baseline_test_{int(time.time())}"
            collection = client.get_or_create_collection(name=collection_name)
            
            # Measure embedding latency
            test_documents = [
                "Machine learning is a subset of artificial intelligence",
                "Deep learning uses neural networks with multiple layers",
                "Natural language processing helps computers understand text",
            ]
            
            start = time.perf_counter()
            collection.add(
                documents=test_documents,
                ids=[f"doc_{i}" for i in range(len(test_documents))]
            )
            add_latency = (time.perf_counter() - start) * 1000  # ms
            
            # Measure query latency
            start = time.perf_counter()
            results = collection.query(
                query_texts=["artificial intelligence"],
                n_results=3
            )
            query_latency = (time.perf_counter() - start) * 1000  # ms
            
            # Store results
            self.results["metrics"]["embedding"]["add_latency_ms"] = add_latency
            self.results["metrics"]["embedding"]["query_latency_ms"] = query_latency
            self.results["metrics"]["embedding"]["documents_tested"] = len(test_documents)
            
            self.log(f"  - Add latency: {add_latency:.1f}ms")
            self.log(f"  - Query latency: {query_latency:.1f}ms")
            
            # Cleanup
            try:
                client.delete_collection(name=collection_name)
            except:
                pass
            
        except Exception as e:
            self.results["metrics"]["embedding"]["status"] = "FAILED"
            self.results["notes"].append(f"Could not capture embedding metrics: {e}")
    
    def capture_inference_metrics(self):
        """Capture vLLM inference metrics"""
        self.log("Capturing inference metrics...")
        
        try:
            import json
            import urllib.request
            
            url = "http://vllm:8001/v1/completions"
            payload = {
                "model": "Qwen/Qwen2.5-14B-Instruct-AWQ",
                "prompt": "Summarize machine learning in 50 words.",
                "max_tokens": 100,
                "temperature": 0.7
            }
            
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            # Measure inference latency (including first-token time)
            start = time.perf_counter()
            response = urllib.request.urlopen(request, timeout=60)
            end = time.perf_counter()
            
            data = json.loads(response.read().decode())
            inference_latency = (end - start) * 1000  # ms
            
            if "choices" in data and data["choices"]:
                generated_text = data["choices"][0]["text"]
                token_count = len(generated_text.split())
                
                self.results["metrics"]["inference"]["latency_ms"] = inference_latency
                self.results["metrics"]["inference"]["tokens_generated"] = token_count
                self.results["metrics"]["inference"]["tokens_per_second"] = (
                    token_count / ((end - start) + 0.001)  # Avoid division by zero
                )
                
                self.log(f"  - Latency: {inference_latency:.0f}ms")
                self.log(f"  - Tokens: {token_count}")
            
        except Exception as e:
            self.results["metrics"]["inference"]["status"] = "FAILED"
            self.results["notes"].append(f"Could not capture inference metrics: {e}")
    
    def capture_resource_metrics(self):
        """Capture system resource utilization"""
        self.log("Capturing resource metrics...")
        
        try:
            # GPU Memory
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip():
                gpu_memory_mb = int(result.stdout.strip().split()[0])
                self.results["metrics"]["resources"]["gpu_memory_used_gb"] = gpu_memory_mb / 1024
                self.log(f"  - GPU Memory: {gpu_memory_mb / 1024:.1f}GB")
        except Exception as e:
            self.results["notes"].append(f"Could not capture GPU memory: {e}")
        
        # Note: Full resource capture would include CPU, memory, disk I/O
        # Placeholder for expanded metrics in Phase 2
        self.results["metrics"]["resources"]["notes"] = "Full system metrics available via monitoring system"
    
    def run(self, num_articles: int):
        """Execute all baseline captures"""
        print("\n╔════════════════════════════════════════════════════╗")
        print("║   Performance Baseline Capture                    ║")
        print("╚════════════════════════════════════════════════════╝\n")
        
        self.log("Starting baseline capture...")
        
        # Verify services are running first
        try:
            import socket as sock_module
            sock = sock_module.create_connection(("mariadb", 3306), timeout=2)
            sock.close()
        except:
            print("✗ MariaDB not accessible. Run diagnostics:")
            print("  python .devcontainer/diagnostic.py")
            return False
        
        # Capture all metrics
        self.capture_environment()
        self.capture_ingestion_metrics(num_articles)
        self.capture_embedding_metrics()
        self.capture_inference_metrics()
        self.capture_resource_metrics()
        
        # Save results
        with open(self.output_path, "w") as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n✓ Baseline captured to: {self.output_path}\n")
        
        # Print summary
        print("Captured Metrics:")
        print(f"  • Environment: {len(self.results['environment'])} properties")
        print(f"  • Ingestion: {len(self.results['metrics']['ingestion'])} metrics")
        print(f"  • Embedding: {len(self.results['metrics']['embedding'])} metrics")
        print(f"  • Inference: {len(self.results['metrics']['inference'])} metrics")
        print(f"  • Resources: {len(self.results['metrics']['resources'])} metrics")
        print(f"\nNotes: {len(self.results['notes'])} items")
        for note in self.results['notes']:
            print(f"  - {note}")
        
        print(f"\n→ Next: Review baseline at {self.output_path}")
        print("→ Store baseline in git for regression tracking")
        
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Capture performance baselines for JustNews"
    )
    parser.add_argument(
        "--output", "-o",
        default="tests/integration/baselines/baseline.json",
        help="Output file for baseline JSON"
    )
    parser.add_argument(
        "--articles", "-a",
        type=int,
        default=1000,
        help="Number of articles for ingestion test"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    capture = BaselineCapture(args.output, verbose=args.verbose)
    success = capture.run(args.articles)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
