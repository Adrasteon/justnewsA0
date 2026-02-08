#!/usr/bin/env python3
"""
JustNews Service Diagnostic Tool

Quick health check for MariaDB, ChromaDB, and vLLM services
Run from /app: python .devcontainer/diagnostic.py
"""

import socket
import json
import sys
import os

def check_service(host, port, service_name, http_endpoint=None):
    """Check service availability via socket and optionally HTTP"""
    result = {
        "service": service_name,
        "host": host,
        "port": port,
        "socket": "unknown",
        "http": None,
        "status": "unknown"
    }
    
    # Socket connectivity check
    try:
        sock = socket.create_connection((host, port), timeout=2)
        sock.close()
        result["socket"] = "✓ connected"
        result["status"] = "partial"
    except socket.timeout:
        result["socket"] = "✗ timeout"
        return result
    except ConnectionRefusedError:
        result["socket"] = "✗ refused"
        return result
    except Exception as e:
        result["socket"] = f"✗ error: {str(e)[:40]}"
        return result
    
    # HTTP health check if endpoint provided
    if http_endpoint:
        try:
            import urllib.request
            url = f"http://{host}:{port}{http_endpoint}"
            request = urllib.request.Request(url, method="GET")
            response = urllib.request.urlopen(request, timeout=3)
            result["http"] = f"✓ {response.status}"
            result["status"] = "healthy"
        except urllib.error.HTTPError as e:
            result["http"] = f"✗ HTTP {e.code}"
        except Exception as e:
            result["http"] = f"✗ {str(e)[:40]}"
    
    return result

def main():
    """Run diagnostics"""
    print("╔════════════════════════════════════════════════════╗")
    print("║   JustNews Service Diagnostic                      ║")
    print("╚════════════════════════════════════════════════════╝\n")
    
    # Services to check
    services = [
        ("mariadb", 3306, "MariaDB", None),
        ("chromadb", 3307, "ChromaDB", "/api/v1/heartbeat"),
        ("vllm", 8001, "vLLM", "/v1/models"),
    ]
    
    print("Service Status:")
    print("─" * 70)
    
    results = []
    all_healthy = True
    
    for host, port, name, http_endpoint in services:
        result = check_service(host, port, name, http_endpoint)
        results.append(result)
        
        socket_status = result["socket"]
        http_status = result["http"] if result["http"] else "—"
        service_status = result["status"]
        
        if service_status == "healthy":
            indicator = "✓"
        elif service_status == "partial":
            indicator = "⚠"
            all_healthy = False
        else:
            indicator = "✗"
            all_healthy = False
        
        print(f"{indicator} {name:12} → {socket_status:20} {http_status:15}")
    
    print("─" * 70)
    
    # Summary
    print("\nSummary:")
    if all_healthy:
        print("✓ All services healthy")
        exit_code = 0
    else:
        partial = sum(1 for r in results if r["status"] == "partial")
        unhealthy = sum(1 for r in results if r["status"] == "unknown")
        
        if unhealthy > 0:
            print(f"✗ {unhealthy} service(s) not responding")
            if "vllm" in [r["service"] for r in results if r["status"] == "unknown"]:
                print("  → vLLM may still be downloading model (first run: 2-5 min)")
            exit_code = 1
        else:
            print(f"⚠ {partial} service(s) responding but health checks pending")
            exit_code = 0
    
    # Environment check
    print("\nEnvironment:")
    env_vars = ["MARIADB_HOST", "CHROMADB_PORT", "VLLM_HOST", "HF_TOKEN"]
    for var in env_vars:
        val = os.environ.get(var, "—")
        if val == "—":
            status = "✗"
        elif var == "HF_TOKEN" and len(val) < 10:
            status = "✗"
        else:
            status = "✓"
        
        display_val = val if var != "HF_TOKEN" else f"{val[:15]}..." if len(val) > 15 else val
        print(f"  {status} {var}: {display_val}")
    
    # Troubleshooting hints
    print("\nTroubleshooting:")
    if not all_healthy:
        mariadb_result = next(r for r in results if r["service"] == "MariaDB")
        if mariadb_result["status"] == "unknown":
            print("  1. MariaDB not responding → docker-compose restart mariadb")
        
        chromadb_result = next(r for r in results if r["service"] == "ChromaDB")
        if chromadb_result["status"] == "unknown":
            print("  2. ChromaDB not responding → docker-compose restart chromadb")
        
        vllm_result = next(r for r in results if r["service"] == "vLLM")
        if vllm_result["status"] == "unknown":
            print("  3. vLLM not responding:")
            print("     - First start: Wait 2-5 min for model download")
            print("     - Check logs: docker-compose logs vllm -f")
            print("     - If stuck: docker-compose restart vllm")
    
    print(f"\nExit code: {exit_code}")
    return exit_code

if __name__ == "__main__":
    sys.exit(main())
