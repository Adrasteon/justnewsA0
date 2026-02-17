#!/usr/bin/env python3
"""Quick Docker diagnostic - check container status."""

import docker
import sys

try:
    client = docker.from_env()
    containers = client.containers.list(all=True)
    
    print("\n🐳 All Containers:")
    print("=" * 80)
    
    for container in containers:
        status = "🟢" if container.status == "running" else "🔴"
        print(f"{status} {container.name:40} {container.status:20} Image: {container.image.tags[0] if container.image.tags else 'unknown'}")
    
    print("\n📡 JustNews Relevant Containers:")
    print("=" * 80)
    
    justnews_containers = [c for c in containers if any(x in c.name for x in ['app', 'chromadb', 'mariadb', 'vllm'])]
    
    if not justnews_containers:
        print("❌ No JustNews containers found!")
    else:
        for container in justnews_containers:
            status = "🟢 RUNNING" if container.status == "running" else "🔴 STOPPED"
            print(f"{status:15} {container.name:35} ports: {container.ports}")
            
            if container.status != "running":
                # Show last few log lines for stopped containers
                logs = container.logs().decode()[-200:] if container.logs() else "No logs"
                print(f"  └─ Last logs: {logs}")
    
    print("\n")
    sys.exit(0)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
