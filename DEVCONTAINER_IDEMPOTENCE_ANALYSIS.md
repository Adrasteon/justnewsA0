## CRITICAL ANALYSIS: Non-Idempotent DevContainer Data Loss Issue

**Issue Date:** 2026-02-10  
**Severity:** 🔴 CRITICAL  
**Impact:** Complete data loss on every devcontainer rebuild

---

## THE PROBLEM

### Current Flow (Data-Destructive):
```
DevContainer Rebuild Triggered
    ↓
initializeCommand: pre-build-cleanup.sh (HOST)
    ↓
✗ FINDS existing containers and volumes
    ↓
✗ ARCHIVES data (best-effort, may fail)
    ↓
✗ **REMOVES ALL CONTAINERS** (aggressive)
    ↓
✗ **DELETES ALL VOLUMES** (DATA LOSS!)
    │
    │ Lines 385-389:
    │ log_info "Step 3: Removing volumes..."
    │ remove_volumes "${volumes[@]}"
    │
    ↓
postCreateCommand: post-create.sh (CONTAINER)
    ↓
Creates FRESH empty MariaDB
    ↓
Creates FRESH empty ChromaDB
    ↓
Creates FRESH vLLM container
    ↓
✗ All previous workflow data is gone!
```

### Files Causing Data Loss:

1. **`.devcontainer/scripts/pre-build-cleanup.sh` (Lines 385-389)**
   - Unconditionally removes volumes with `docker volume rm`
   - No option to preserve data
   - No idempotence check

2. **`.devcontainer/docker-compose.yaml`**
   - Always recreates services from scratch
   - No volume existence checks before recreation
   - Services always start with `image: latest` (may pull new versions)

3. **`.devcontainer/scripts/post-create.sh`**
   - Runs migrations on every container start (includes DROP TABLE IF EXISTS)
   - No check to detect if volumes already contain valid data
   - Assumes fresh start

---

## WHAT SHOULD HAPPEN (Idempotent Behavior):

### Desired Flow (Data-Preserving):
```
DevContainer Rebuild Triggered
    ↓
initializeCommand: pre-build-cleanup.sh (HOST)
    ↓
✓ CHECK if volumes exist
    ├─ YES → Preserve volumes, only stop/remove containers
    └─ NO → Create fresh infrastructure
    ↓
✓ STOP running containers (graceful)
    ↓
✓ REMOVE ONLY CONTAINERS (volumes untouched)
    ↓
postCreateCommand: post-create.sh (CONTAINER)
    ↓
✓ Check if DB schema exists (query schema_migrations table)
    ├─ YES → Skip migrations, start services
    └─ NO → Run migrations as normal
    ↓
✓ Check if vLLM model is cached
    ├─ YES → Use cached model
    └─ NO → Download and cache
    ↓
✓ Start all services with existing data intact
    ↓
✓ Previous workflow data is preserved!
```

---

## ROOT CAUSES

### 1. Pre-Build Cleanup (Host-Side)
- **Issue**: Removes volumes without checking if they should be preserved
- **Line**: `pre-build-cleanup.sh:385-389`
- **Code**:
  ```bash
  log_info "Step 3: Removing volumes..."
  remove_volumes "${volumes[@]}"  # ← DELETES ALL DATA!
  ```

### 2. Post-Create Script (Container-Side)
- **Issue**: Assumes fresh start, no detection of existing database state
- **Line**: `post-create.sh:196` (line numbers approximate)
- **Code**:
  ```bash
  # Unconditionally runs migrations
  python /app/apply_migrations_script.py
  ```
- **Problem**: `DROP TABLE IF EXISTS` statements in migrations can cause data loss if they inadvertently drop with data still being accessed

### 3. Docker-Compose Service Definition
- **Issue**: No restart policy checks for existing volumes
- **Code**:
  ```yaml
  mariadb:
    container_name: mariadb
    image: mariadb:latest  # ← Each rebuild pulls latest (could be different)
    volumes:
      - mariadb_data:/var/lib/mysql
    # No health checks, no conditional startup logic
  ```

### 4. Migration Script
- **Issue**: `apply_migrations_script.py` has no idempotence safeguards
- **Line**: `apply_migrations_script.py:170+`
- **Problem**: SQL statements like `CREATE TABLE IF NOT EXISTS` are safe, but the script runs unconditionally

---

## DETAILED IMPACT

### What Data is Lost:
1. **MariaDB Data** (`mariadb_data` volume):
   - ✗ All articles ingested with crawlerbbb
   - ✗ All embeddings vector metadata
   - ✗ All entities extracted
   - ✗ All sentiment/bias analyses
   - ✗ All living stories and story updates
   - ✗ All 100 sources configuration (gets reseeded, but workflow state lost)

2. **ChromaDB Data** (`chromadb_data` volume):
   - ✗ All vector embeddings
   - ✗ All collection metadata
   - ✗ Search indexes

3. **vLLM Cache** (in container volumes):
   - ✓ Model cache is separate (usually in ~/.cache, preserved)
   - But startup time increases significantly

### When Data Loss Occurs:
- ✓ Every time you run: `devcontainer: Rebuild and Reopen in Container`
- ✓ Every time VSCode auto-restarts the devcontainer
- ✓ Every time you rebuild the docker image locally
- ✓ CI/CD pipelines that rebuild the container

---

## SOLUTION: IMPLEMENT IDEMPOTENCE

### Phase 1: Fix Pre-Build Cleanup Script
**File**: `.devcontainer/scripts/pre-build-cleanup.sh`

Changes needed:
1. Check if volumes are in-use (attached to running containers)
2. If volumes are attached, preserve them:
   - Stop containers (gracefully, -t 30)
   - Remove containers only
   - **DO NOT DELETE VOLUMES**
3. If volumes are orphaned (not attached to any running container):
   - Optionally archive them
   - Then remove them
4. Add `--preserve-data` flag option for users who want old behavior

**Key Addition**:
```bash
# IDEMPOTENT: Check if volumes have active containers
if volume_is_in_use "$volume"; then
    log_info "Volume $volume is in use. Preserving it."
    continue  # Skip removal
else
    # Only remove orphaned volumes (after archiving)
    log_info "Volume $volume is orphaned. Archiving and removing..."
    archive_volume "$volume"
    remove_volume "$volume"
fi
```

### Phase 2: Fix Post-Create Script
**File**: `.devcontainer/scripts/post-create.sh`

Changes needed:
1. Check if `schema_migrations` table exists
2. If it does, skip running migrations
3. Only run migrations if table doesn't exist (first run)
4. Add detection for existing ChromaDB collections
5. Gracefully handle partial migration state

**Key Addition**:
```bash
# IDEMPOTENT: Check if database already initialized
if is_database_initialized; then
    log_success "Database already initialized, skipping migrations"
    log_info "Existing data will be preserved"
else
    log_info "Fresh database detected, running migrations"
    python /app/apply_migrations_script.py
fi
```

### Phase 3: Improve Migration Script
**File**: `apply_migrations_script.py`

Changes needed:
1. Add idempotent check for table existence before creating
2. Log when skipping already-applied migrations (currently does this)
3. Add safeguard against running migrations twice in same transaction
4. Verify database state consistency

**Key Addition**:
```python
# IDEMPOTENT: Check if table already exists before creating
cursor.execute("SHOW TABLES LIKE %s", (table_name,))
if cursor.fetchone():
    print(f"Table {table_name} already exists, skipping creation")
    continue
```

### Phase 4: Update Docker-Compose
**File**: `.devcontainer/docker-compose.yaml`

Changes needed:
1. Pin image versions (don't use `latest`)
2. Add explicit restart policies
3. Add health checks
4. Document volume persistence strategy

**Key Addition**:
```yaml
mariadb:
  image: mariadb:11.2  # Pin version instead of 'latest'
  restart_policy:
    condition: on-failure
    delay: 5s
    max_attempts: 3
  healthcheck:
    test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
    interval: 10s
    timeout: 5s
    retries: 5
```

---

## IMPLEMENTATION CHECKLIST

- [ ] **Phase 1**: Modify `pre-build-cleanup.sh` to preserve volumes
  - [ ] Add volume attachment detection
  - [ ] Skip volume removal if in-use
  - [ ] Archive orphaned volumes before removal only
  - [ ] Test with existing devcontainer instance
  - [ ] Test with fresh devcontainer
  
- [ ] **Phase 2**: Modify `post-create.sh` to detect existing DB
  - [ ] Add `is_database_initialized()` function
  - [ ] Add `is_chromadb_initialized()` function
  - [ ] Skip migrations if database exists
  - [ ] Log detection results clearly
  
- [ ] **Phase 3**: Improve `apply_migrations_script.py`
  - [ ] Add table existence checks
  - [ ] Add consistency verification
  - [ ] Log migration skips clearly
  
- [ ] **Phase 4**: Update `docker-compose.yaml`
  - [ ] Pin all image versions
  - [ ] Add health checks to all services
  - [ ] Add restart policies
  
- [ ] **Phase 5**: Documentation
  - [ ] Create IDEMPOTENCE_GUARANTEE.md
  - [ ] Update README.md with data preservation note
  - [ ] Document the rebuild process
  - [ ] Create recovery guide if data loss occurs anyway
  - [ ] Document manual data recovery from backups

---

## DOCUMENTATION TO CREATE/UPDATE

### New Documents:
1. **DEVCONTAINER_IDEMPOTENCE_GUARANTEE.md**
   - Explains data is preserved on rebuild
   - Shows the idempotent flow
   - Troubleshooting guide
   - How to force a clean rebuild if needed

2. **DATA_LOSS_RECOVERY_GUIDE.md**
   - Where backups are stored
   - How to restore from backup
   - Timeline of backups kept

### Updated Documents:
1. **.devcontainer/README.md**
   - Add section: "Data Persistence on Rebuild"
   - Clarify that workflows data is preserved
   - Explain backup locations

2. **DEVCONTAINER_ARCHITECTURE.md**
   - Add idempotence requirements
   - Document volume preservation strategy
   - Add flow diagrams

3. **JUSTNEWS_STARTUP_GUIDE.md**
   - Add warning about previous versions WITHOUT idempotence
   - Explain current version preserves data

---

## BACKUP ARCHIVE LOCATIONS

Backups are created by `pre-build-cleanup.sh` in:
```
~/.justnews_backups/mariadb_YYYYMMDD_HHMMSS/
~/.justnews_backups/chromadb_YYYYMMDD_HHMMSS/
```

These should NOT be deleted automatically. Users need ability to restore.

---

## TESTING STRATEGY

### Test 1: First-Run (Clean Slate)
- [ ] New devcontainer on clean system
- [ ] Verify all migrations run
- [ ] Verify databases created
- [ ] Verify 100 sources seeded
- [ ] Verify vLLM initializes

### Test 2: Rebuild with Data (Preserve)
- [ ] Start devcontainer (fresh)
- [ ] Ingest some articles (10-20)
- [ ] Generate embeddings for articles
- [ ] Rebuild devcontainer
- [ ] Verify articles still exist
- [ ] Verify embeddings still exist
- [ ] Verify embedding count unchanged

### Test 3: Clean Rebuild (Optional)
- [ ] Start devcontainer with data
- [ ] Run `/app/.devcontainer/scripts/pre-build-cleanup.sh --force-clean`
- [ ] Verify volumes deleted (intentionally)
- [ ] Rebuild devcontainer
- [ ] Verify fresh installation

### Test 4: Partial Failure Recovery
- [ ] Start devcontainer
- [ ] Manually stop MariaDB container only
- [ ] Rebuild
- [ ] Verify MariaDB restarts
- [ ] Verify data intact

---

## DEPLOYMENT NOTES

### Breaking Changes: NONE
- Existing behavior preserved for first-time users
- Only adds preservation for subsequent rebuilds

### Migration Path:
- Users with existing backups: Data preserved automatically
- Fresh installs: Works exactly as before
- Opt-in `--force-clean` flag for users who want old behavior

### Rollback:
- If idempotence breaks something, `--force-clean` flag allows clean rebuild
- Backups are always preserved for recovery

---
