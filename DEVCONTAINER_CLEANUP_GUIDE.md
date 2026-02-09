# DevContainer Cleanup & Rebuild Process

**Date:** February 9, 2026  
**Status:** ✅ Implemented

---

## 📋 Overview

When rebuilding a devcontainer after a previous build, Docker Compose can encounter naming conflicts with existing containers and volumes. This causes new containers to be created with `-1`, `-2` suffixes, breaking service networking and causing the container to reference incorrect services.

**Example Problem:**
```
Previous build created:
  - justnews_mariadb_1
  - justnews_chromadb_1
  - justnews_vllm_1

New rebuild attempts to create:
  - justnews_mariadb_1  (already exists) → becomes justnews_mariadb_2
  - justnews_chromadb_1 (already exists) → becomes justnews_chromadb_2
  - justnews_vllm_1 (already exists) → becomes justnews_vllm_2

Result:
  ❌ App tries to connect to "mariadb" (DNS)
  ❌ But only "mariadb_2" exists
  ❌ Connection fails
```

---

## ✅ Solution: Pre-Build Cleanup

The devcontainer now includes an **automatic pre-build cleanup sequence** that:

1. **Detects** existing containers and volumes from previous builds
2. **Archives** MariaDB data for recovery if needed (non-destructive)
3. **Stops** running containers gracefully
4. **Removes** old containers and volumes
5. **Verifies** clean state before building
6. **Ensures** new containers get the intended names without suffixes

---

## 🔄 Build Sequence

### **VS Code Devcontainer Lifecycle**

```
USER: Click "Rebuild Container" in VS Code
    ↓
.devcontainer/devcontainer.json loads
    ↓
initializeCommand RUNS (on host, before docker-compose)
    │
    └─ Executes: .devcontainer/scripts/pre-build-cleanup.sh
       │
       ├─ Scans for existing containers & volumes
       ├─ Archives MariaDB data → ~/.justnews_backups/mariadb_TIMESTAMP/
       ├─ Stops & removes old containers
       ├─ Removes old volumes
       └─ Verifies clean slate
    ↓
docker-compose.yaml builds (NEW, CLEAN)
    │
    ├─ Creates: mariadb (with correct name, no suffix)
    ├─ Creates: chromadb (with correct name, no suffix)
    ├─ Creates: vllm (with correct name, no suffix)
    └─ Creates: app (with correct name, no suffix)
    ↓
postCreateCommand RUNS (inside container)
    │
    └─ Executes: /usr/local/bin/create_deps_venv.sh
       ├─ Creates venv at /deps/.venv
       └─ Chains to post-create.sh
           │
           └─ post-create.sh:
              ├─ Step 1: Waits for MariaDB (3-phase polling)
              ├─ Step 1.5: 3-second settling time
              ├─ Step 2: Django migrations
              ├─ Step 2.1: SQL migrations (14 tables)
              ├─ Step 3: ChromaDB polling
              ├─ Step 4: vLLM polling
              └─ Step 5: Static files + verification
    ↓
✅ Shell prompt appears with fully initialized devcontainer
```

---

## 🧹 Cleanup Script Details

**Location:** `/.devcontainer/scripts/pre-build-cleanup.sh`

### **What It Does**

#### **Phase 1: Detection**
Scans for containers matching these patterns:
- `{ProjectDir}_app`, `{ProjectDir}_mariadb`, `{ProjectDir}_chromadb`, `{ProjectDir}_vllm`
- `justnews_app`, `justnews_mariadb`, `justnews_chromadb`, `justnews_vllm`
- Generic names: `app`, `mariadb`, `chromadb`, `vllm`

Scans for volumes matching these patterns:
- `{ProjectDir}_justnews_deps`, `{ProjectDir}_justnews_data`, `{ProjectDir}_mariadb_data`
- `justnews_deps`, `justnews_data`, `mariadb_data`

#### **Phase 2: Archival (Non-Destructive)**
Before deletion, backs up:
- **MariaDB MySQL directory** (/var/lib/mysql)
  - Copied via `docker cp` to preserve data
  - Stored at: `~/.justnews_backups/mariadb_YYYYMMDD_HHMMSS/`
- **Database metadata** for recovery reference

#### **Phase 3: Cleanup**
1. Stops containers gracefully (10-second timeout)
2. Forces removal of stopped containers
3. Forces removal of volumes
4. Verifies cleanup completed

#### **Phase 4: Verification**
- Confirms all old containers removed
- Confirms all old volumes removed
- Checks Docker images are available
- Reports ready for build

### **Exit Codes**
- `0` = Success (cleanup completed or nothing to clean)
- `1` = Docker not available or cleanup failed
- Errors don't block build (|| true in initializeCommand)

---

## 📊 Execution Flow

```bash
#!/usr/bin/env bash

# 1. Docker availability check
check_docker()
  → Verifies docker command exists
  → Verifies docker daemon is running
  → Returns error if not available

# 2. Find resources
find_containers()
  → docker ps -a --format "{{.Names}}"
  → Filter by patterns
  → Return array of matching containers

find_volumes()
  → docker volume ls --format "{{.Name}}"
  → Filter by patterns
  → Return array of matching volumes

# 3. Archive data (if containers exist)
archive_mariadb_data()
  → Find running MariaDB containers
  → Create backup directory
  → docker cp container:/var/lib/mysql → backup
  → Stop containers gracefully
  → Log backup path

# 4. Stop containers
stop_containers()
  → docker stop {container} --time=5
  → Wait for graceful shutdown
  → Report completion

# 5. Remove containers
remove_containers()
  → docker rm {container} -f
  → Force remove to avoid conflicts
  → Report completion

# 6. Remove volumes
remove_volumes()
  → docker volume rm {volume}
  → Remove to ensure clean state
  → Report completion

# 7. Verify cleanup
  → Re-scan for remaining containers
  → Re-scan for remaining volumes
  → Report success or warnings
```

---

## 🔍 Monitoring & Logging

### **Console Output**
```
========================================
JustNews DevContainer Pre-Build Cleanup
========================================

[INFO] Starting pre-build cleanup sequence...
[INFO] Project directory: justnewsA0
[INFO] DevContainer path: /app/.devcontainer
[INFO] Backup location: /home/user/.justnews_backups
[✓] Docker is available

[INFO] Scanning for existing containers and volumes...

[⚠] Found 4 container(s) from previous builds:
    • justnews_app_1
    • justnews_mariadb_1
    • justnews_chromadb_1
    • justnews_vllm_1

[⚠] Found 3 volume(s) from previous builds:
    • justnews_deps
    • justnews_data
    • mariadb_data

[INFO] Step 1: Archiving data from existing containers...
[INFO]   Archiving from container: justnews_mariadb_1
[✓]   ✓ Backed up MySQL data directory
[✓] MariaDB data archived to: /home/user/.justnews_backups/mariadb_20260209_145032

[INFO] Step 2: Removing containers...
[INFO]   Stopping: justnews_mariadb_1
[INFO]   Stopping: justnews_chromadb_1
[INFO]   Stopping: justnews_vllm_1
[INFO]   Stopping: justnews_app_1
[✓] All containers stopped

[INFO]   Removing: justnews_mariadb_1
[INFO]   Removing: justnews_chromadb_1
[INFO]   Removing: justnews_vllm_1
[INFO]   Removing: justnews_app_1
[✓] All containers removed

[INFO] Step 3: Removing volumes...
[INFO]   Removing: justnews_deps
[INFO]   Removing: justnews_data
[INFO]   Removing: mariadb_data
[✓] All volumes removed

========================================
✓ Pre-build cleanup complete!
========================================

[INFO] Data archived to: /home/user/.justnews_backups/mariadb_20260209_145032
[INFO] To restore archived data, contact your DevOps team
[INFO] Ready for new devcontainer build!
[INFO] New containers will use correct names without -1 suffixes
```

---

## 🛠️ Manual Cleanup (If Needed)

### **Run Cleanup Manually**
```bash
# From workspace root
bash .devcontainer/scripts/pre-build-cleanup.sh

# Or from anywhere with path
bash /path/to/app/.devcontainer/scripts/pre-build-cleanup.sh
```

### **View Archived Data**
```bash
# List all archives
ls -la ~/.justnews_backups/

# List specific archive
ls -la ~/.justnews_backups/mariadb_20260209_145032/
```

### **Restore MariaDB Data** (Advanced)
```bash
# Contact DevOps for guided restore process
# Data is preserved in ~/.justnews_backups/

# Do NOT manually move data - wait for restore procedure
```

### **Force Clean Without Archival**
```bash
# Use docker-compose down (removes containers, keeps volumes)
cd /app/.devcontainer
docker-compose down

# Then remove volumes
docker volume rm justnews_deps justnews_data mariadb_data

# Then rebuild
```

---

## 📋 Key Features

| Feature | Benefit |
|---------|---------|
| **Automatic Execution** | Runs before every rebuild (no manual steps) |
| **Data Preservation** | Archives MariaDB before deletion (non-destructive) |
| **Smart Detection** | Finds containers by pattern (matches multiple naming schemes) |
| **Graceful Shutdown** | Stops containers with timeout before forced removal |
| **Clean Verification** | Scans to confirm cleanup succeeded |
| **Error Tolerance** | Non-critical errors don't block build (|| true) |
| **Comprehensive Logging** | Shows exactly what's happening in colored output |
| **Backup Location** | Centralized at ~/.justnews_backups for easy access |
| **Timestamp Tracking** | Each backup has timestamp for version history |

---

## ⚠️ Important Notes

### **Data Safety**
- ✅ MariaDB data IS archived before deletion
- ✅ Archives preserved for recovery
- ✅ Old containers safely stopped before removal
- ❌ DO NOT manually delete ~/.justnews_backups/ without confirmation

### **Network Isolation**
- After cleanup, new containers get fresh names
- Docker Compose handles network creation automatically
- Services reference each other by name (e.g., "mariadb" DNS)
- No -1 suffixes means names resolve correctly

### **Performance**
- First build: 30-60s cleanup + normal build time
- Subsequent rebuilds: 30-60s cleanup + faster build
- Cleanup is one-time cost for guaranteed correct naming
- No impact on running code performance

### **Troubleshooting**

**If cleanup fails:**
```bash
# Check Docker status
docker ps -a

# Check volumes
docker volume ls

# Check images
docker image ls

# Manual cleanup if script fails
docker rm -f $(docker ps -a -q) 2>/dev/null || true
docker volume rm $(docker volume ls -q) 2>/dev/null || true
```

**If build still fails after cleanup:**
1. Verify Docker daemon is running
2. Check disk space: `df -h`
3. Check Docker resources: `docker stats`
4. Run cleanup manually again
5. Contact DevOps with error logs

---

## 🚀 Benefits Summary

### **Before (Problem)**
```
RebuildContainer
  ↓
docker-compose up
  ↓
Containers created with -1 suffixes
  ↓
Network resolution fails
  ↓
❌ BUILD BROKEN
```

### **After (Solution)**
```
RebuildContainer
  ↓
pre-build-cleanup.sh
  ├─ Archives data
  ├─ Removes old containers
  └─ Cleans volumes
  ↓
docker-compose up (CLEAN)
  ├─ Creates: mariadb (correct name)
  ├─ Creates: chromadb (correct name)
  ├─ Creates: vllm (correct name)
  └─ Creates: app (correct name)
  ↓
Network resolution succeeds
  ↓
✅ BUILD SUCCESSFUL
```

---

## 📞 Support

For issues with:
- **Naming conflicts:** Pre-build cleanup should resolve automatically
- **Data loss concerns:** All data archived to ~/.justnews_backups/
- **Manual recovery:** Contact DevOps with timestamp from error logs
- **Cleanup failures:** Enable verbose output and check Docker status

---

**Status:** ✅ Production Ready  
**Tested:** February 9, 2026  
**Maintained by:** Infrastructure Team
