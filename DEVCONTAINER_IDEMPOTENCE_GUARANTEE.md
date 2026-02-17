# DevContainer Idempotence Guarantee

**Status:** ✅ IMPLEMENTED  
**Version:** 2.0 (Data-Preserving)  
**Date:** 2026-02-10 

> **Key Guarantee**: Your workflow data is preserved when you rebuild the DevContainer. No more data loss on rebuild!

---

## 🎯 What This Means

### Before (Data-Destructive):
```
Rebuild DevContainer
    ↓
All containers deleted
All volumes deleted
    ↓
Complete data loss (10-100+ articles, embeddings, all analysis)
    ↓
Fresh start (painful!)
```

### After (Data-Preserving):
```
Rebuild DevContainer
    ↓
Volumes checked for existing data
    ↓
Containers restarted (volumes untouched)
    ↓
Existing database detected, migrations skipped
    ↓
All articles, embeddings, analysis preserved
    ↓
Continue where you left off!
```

---

## 📋 Idempotence Implementation

### Part 1: Container Startup (Host-Side)
**File**: `.devcontainer/scripts/pre-build-cleanup.sh`

**Behavior**:
- ✅ Checks if volumes contain existing data
- ✅ Stops running containers gracefully
- ✅ **Preserves volumes by default** (data NOT deleted)
- ✅ Only removes orphaned volumes (no containers using them)
- ✅ Archives backups for manual recovery

**For Users**:
```bash
# Normal rebuild (preserves data)
VSCode: Cmd/Ctrl + Shift + P → "Remote-Containers: Rebuild and Reopen"

# Force clean rebuild if needed
bash .devcontainer/scripts/pre-build-cleanup.sh --force-clean
# Then: VSCode rebuild
```

### Part 2: Database Initialization (Container-Side)
**File**: `.devcontainer/scripts/post-create.sh`

**Behavior**:
- ✅ Checks if `schema_migrations` table exists
- ✅ If exists: Skips migrations (existing database detected)
- ✅ If missing: Runs migrations (first-time setup)
- ✅ Database integrity verified before starting services
- ✅ Logs clearly what was done

**Example Output**:
```
[INFO] Step 2: Checking if database schema is already initialized...
[✓ SUCCESS] Database schema already initialized (schema_migrations table found)
[INFO] Skipping migrations - existing data will be preserved
[INFO] Database integrity verified - migrations skipped for idempotence
```

### Part 3: Vector Store Initialization (ChromaDB)
**File**: `.devcontainer/scripts/post-create.sh`

**Behavior**:
- ✅ Connects to ChromaDB service
- ✅ Checks if collections already exist
- ✅ If collections exist: No action (data preserved)
- ✅ If fresh: Collections auto-create on first use
- ✅ No data loss, no recreation

**Example Output**:
```
[✓ SUCCESS] ChromaDB is fully operational (with existing collections)
[INFO] → Existing collections detected - data preserved
```

---

## 🔄 The Rebuild Workflow

### Scenario 1: First DevContainer Rebuild (Fresh Start)
```
1. pre-build-cleanup.sh runs
   - No containers found
   - No volumes found
   - → Clean slate confirmed

2. Docker builds fresh image
   - MariaDB, ChromaDB, vLLM initialized
   - Pulls latest images

3. post-create.sh runs
   - schema_migrations table MISSING
   - → Runs migrations (creates tables)
   - → Runs seeds (inserts 100 sources)
   
4. Ready to use
   - Empty but initialized database
   - No workflow data (fresh start)
```

### Scenario 2: Rebuild After Workflow (Data-Preserving)
```
1. You've ingested 50 articles
2. Generated embeddings for all articles
3. Decided to rebuild (update VSCode, install extension, etc.)

4. pre-build-cleanup.sh runs
   - Finds mariadb_data volume (in use)
   - Finds chromadb_data volume (in use)
   - → PRESERVES both volumes
   - Stops containers (graceful, -t 30 seconds)
   
5. Docker starts services
   - Mounts existing mariadb_data volume
   - Mounts existing chromadb_data volume
   - Starts MariaDB with existing data
   - Starts ChromaDB with existing collections

6. post-create.sh runs
   - schema_migrations table EXISTS (migrations already applied)
   - → SKIPS migrations
   - Database integrity verified
   
7. Ready to use
   - Same 50 articles present
   - Same embeddings in ChromaDB
   - All analysis data intact
```

### Scenario 3: Force Clean Rebuild (Intentional Data Wipe)
```
1. You want to start completely fresh
2. Run: bash .devcontainer/scripts/pre-build-cleanup.sh --force-clean

3. pre-build-cleanup.sh runs
   - Found flag: FORCE_CLEAN_REBUILD=true
   - Archives data to ~/.justnews_backups/mariadb_YYYYMMDD_HHMMSS/
   - Archives data to ~/.justnews_backups/chromadb_YYYYMMDD_HHMMSS/
   - REMOVES all volumes (backup first)
   - Logs: "FORCE CLEAN: Removing all volumes (DATA WILL BE LOST)"

4. Docker starts fresh services
   - No volumes found
   - Creates new empty volumes
   - Fresh database

5. post-create.sh runs
   - schema_migrations table MISSING
   - → Runs migrations
   
6. Ready to use
   - Completely fresh database
   - Data available in ~/.justnews_backups/ if needed
```

---

## 🛡️ Data Safety Guarantees

### What's Preserved:
- ✅ All articles ingested via crawlers
- ✅ All embeddings in ChromaDB
- ✅ All entities extracted
- ✅ All sentiment/bias analyses
- ✅ Living stories and story updates
- ✅ All task metadata and status
- ✅ ChromaDB collection structure

### What's NOT Affected:
- ✅ Your source code (`/app` volume - bind mount, always preserved)
- ✅ Dependencies (`justnews_deps` volume - only recreated if missing)
- ✅ Backup archives (`~/.justnews_backups/` - never auto-deleted)

### Backup Strategy:
- `.devcontainer/scripts/pre-build-cleanup.sh` automatically archives data:
  ```
  ~/.justnews_backups/
    mariadb_20260210_132800/
      mysql_data_mariadb/  (full database dump)
    chromadb_20260210_132801/
      chroma_data/  (embeddings and metadata)
  ```

---

## 🔧 Troubleshooting

### Issue: "Data Loss After Rebuild"

**Solution 1**: Check if volume was preserved
```bash
# List existing volumes
docker volume ls | grep justnews

# Expected output:
# justnews_deps            local
# justnews_data            local
# mariadb_data             local      ← Should exist
# chromadb_data            local      ← Should exist
```

**Solution 2**: Verify database state
```bash
# Connect to database
mysql -h mariadb -u justnews -pdev_justnews_password justnews

# Check article count
SELECT COUNT(*) FROM articles;
```

**Solution 3**: Restore from backup if needed
```bash
# Find recent backup
ls -ltr ~/.justnews_backups/

# Contact DevOps for restore procedure
```

### Issue: "Migrations Running When They Shouldn't"

**Root Cause**: `schema_migrations` table got corrupted or deleted

**Solution**:
```bash
# Check migration table
mysql -h mariadb -u justnews -pdev_justnews_password justnews \
  -e "SHOW TABLES LIKE 'schema_migrations';"

# If missing, manual recovery needed
# Contact backend team for DB restoration
```

### Issue: "Container Keeps Recreating Database"

**Root Cause**: Volumes being deleted despite preservation logic

**Check**:
```bash
# Monitor cleanup script in verbose mode
bash -x .devcontainer/scripts/pre-build-cleanup.sh 2>&1 | grep -i "volume\|preserve"

# Should see:
# + is_volume_in_use mariadb_data
#   Preserving: mariadb_data (still in use by container)
```

---

## 📚 Documentation Updates

### Updated Documents:
1. ✅ `.devcontainer/README.md` - Added "Data Persistence" section
2. ✅ `DEVCONTAINER_ARCHITECTURE.md` - Added idempotence requirements
3. ✅ `JUSTNEWS_STARTUP_GUIDE.md` - Added rebuild preservation note
4. ✅ This document - Complete idempotence guarantee

### Key Updates:
- All documentation now states: "Workflow data is preserved on rebuild"
- Clear instructions for force-clean rebuild if needed
- Backup archive locations documented
- Recovery procedures documented

---

## 🚀 For DevOps / Infrastructure

### Monitoring Volumes:

```bash
# Check volume status
docker volume inspect mariadb_data
docker volume inspect chromadb_data

# Monitor space usage
docker system df -v | grep justnews

# Backup volumes manually
docker run --rm -v mariadb_data:/data -v /backup:/backup \
  alpine tar czf /backup/mariadb_data_backup.tar.gz -C /data .
```

### Backup Retention Policy:

Default: Keep last 7 days of backups
```bash
# Cleanup old backups (older than 7 days)
find ~/.justnews_backups -type d -mtime +7 -exec rm -rf {} \;
```

### Emergency Recovery:

If volume is corrupted:
```bash
# Force clean rebuild (will ask for confirmation)
bash .devcontainer/scripts/pre-build-cleanup.sh --force-clean

# Restore from backup manually
cd ~/.justnews_backups/mariadb_LATEST/
# Follow restore guide
```

---

## ✅ Implementation Checklist

- [x] Pre-build cleanup script modified for idempotence
- [x] Post-create script checks for existing database
- [x] ChromaDB collection detection implemented
- [x] Volume preservation logic added
- [x] Force-clean flag implemented
- [x] Backup archive creation maintained
- [x] Documentation updated comprehensively
- [x] Test scenarios verified
- [x] Logging improved for transparency
- [x] Recovery procedures documented

---

## 📞 Support

**Need help?**
- Check `.devcontainer/` directory for startup scripts
- Review DevContainer logs in Output panel
- Check temporary logs: `/tmp/sql_migrations.log`, `/tmp/migrate.log`
- Contact infrastructure team for volume/backup issues

**Want to force a clean rebuild?**
```bash
bash .devcontainer/scripts/pre-build-cleanup.sh --force-clean
```

**Data recovery questions?**
- Backups are stored in: `~/.justnews_backups/`
- Keep archives for at least 7 days
- Document any manual restore procedures

---

## 📖 Version History

- **v2.0** (2026-02-10): ✅ IDEMPOTENT - Data preserved on rebuild
- **v1.0** (Before): ❌ Data-destructive - All data lost on rebuild

"**Upgrade to v2.0 immediately to preserve your workflow data!**"
