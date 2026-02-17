#!/usr/bin/env python3
"""
JustNews Docker Cleanup - Remove containers with naming conflicts (-1 suffixes)
Uses Docker Python SDK instead of CLI
"""

import docker
import sys
import time
from pathlib import Path

def cleanup_containers():
    """Clean up containers with -1, -2 suffixes and old containers."""
    try:
        client = docker.from_env()
    except Exception as e:
        print(f"❌ Cannot connect to Docker daemon: {e}")
        print("   Make sure Docker is running")
        return False
    
    print("\n" + "=" * 60)
    print("JustNews Docker Cleanup")
    print("=" * 60 + "\n")
    
    # Find containers to remove
    all_containers = client.containers.list(all=True)
    
    print(f"Found {len(all_containers)} total containers\n")
    
    # Containers to clean up
    cleanup_patterns = [
        'chromadb_1', 'chromadb_2', 'chromadb_3',
        'mariadb_1', 'mariadb_2', 'mariadb_3',
        'vllm_1', 'vllm_2', 'vllm_3',
        'app_1', 'app_2', 'app_3',
    ]
    
    containers_to_remove = []
    for container in all_containers:
        if any(pattern in container.name for pattern in cleanup_patterns):
            containers_to_remove.append(container)
    
    if not containers_to_remove:
        print("✓ No containers with naming conflicts found!")
        print("  Checking volumes...\n")
    else:
        print(f"Found {len(containers_to_remove)} container(s) to clean up:\n")
        
        for container in containers_to_remove:
            status = "running" if container.status == "running" else "stopped"
            print(f"  • {container.name} ({status})")
        
        print()
        
        # Stop running containers
        running = [c for c in containers_to_remove if c.status == "running"]
        if running:
            print(f"Stopping {len(running)} running container(s)...")
            for container in running:
                try:
                    container.stop(timeout=10)
                    print(f"  ✓ Stopped: {container.name}")
                except Exception as e:
                    print(f"  ⚠ Error stopping {container.name}: {e}")
        
        print()
        
        # Remove containers
        print(f"Removing {len(containers_to_remove)} container(s)...")
        for container in containers_to_remove:
            try:
                container.remove(force=True)
                print(f"  ✓ Removed: {container.name}")
            except Exception as e:
                print(f"  ⚠ Error removing {container.name}: {e}")
    
    print()
    
    # Clean up volumes
    print("Checking volumes...\n")
    
    volume_patterns = [
        'justnews_deps',
        'justnews_data', 
        'mariadb_data',
        'chromadb_data',
    ]
    
    try:
        all_volumes = client.volumes.list()
        volumes_to_remove = []
        
        for volume in all_volumes:
            if any(pattern in volume.name for pattern in volume_patterns):
                volumes_to_remove.append(volume)
        
        if volumes_to_remove:
            print(f"Found {len(volumes_to_remove)} volume(s) to remove:\n")
            
            for volume in volumes_to_remove:
                print(f"  • {volume.name}")
            
            print()
            print("Removing volumes...")
            
            for volume in volumes_to_remove:
                try:
                    volume.remove(force=True)
                    print(f"  ✓ Removed: {volume.name}")
                except Exception as e:
                    print(f"  ⚠ Error removing {volume.name}: {e}")
        else:
            print("✓ No volumes with naming conflicts found!")
    
    except Exception as e:
        print(f"⚠ Error managing volumes: {e}")
    
    print()
    
    # Summary
    print("=" * 60)
    print("Cleanup Complete!")
    print("=" * 60 + "\n")
    print("Next steps:")
    print("  1. Start containers with: docker compose -f .devcontainer/docker-compose.yaml up -d")
    print("  2. Verify with: docker ps")
    print("  3. Run status check: python3 canonical_status_check.py\n")
    
    return True

if __name__ == "__main__":
    success = cleanup_containers()
    sys.exit(0 if success else 1)
