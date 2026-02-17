# DevContainer Initialization - Migration Execution Analysis

**Date:** February 9, 2026 (Updated February 10, 2026)  
**Status:** ✅ **CORRECTED - SQL migrations DO run**

---

## ✅ SHORT ANSWER: **YES - SQL migrations automatically run during devcontainer build**

The `.sql` migration files in `/app/database/migrations/` **ARE** executed during the devcontainer build cycle via `apply_migrations_script.py` called from `post-create.sh`.

---

## 📊 What Actually Happens During DevContainer Build

### **Step-by-Step Timeline:**

```
DevContainer Build Starts
  ↓
Dockerfile executes
  ├─ Installs Python, UV, dependencies
  ├─ Copies scripts (entrypoint.sh, create_deps_venv.sh, post-create.sh)
  └─ Sets entrypoint to /usr/local/bin/entrypoint.sh
  ↓
docker-compose.yaml starts containers (mariadb, chromadb, vllm)
  ↓
postCreateCommand runs: create_deps_venv.sh
  ├─ Creates virtual environment at /deps/.venv
  └─ Chains to post-create.sh
    ↓
    Step 1: Wait for MariaDB to be ready
    ↓
    Step 2: Run SQL schema migrations ✅
    │ 
    └─ Executes: python apply_migrations_script.py
       │
       ├─ Reads: /app/database/migrations/*.sql (in alphabetical order)
       ├─ Transforms: PostgreSQL → MariaDB syntax
       ├─ Applies: Migrations 001-015 sequentially
       │
       ├─ Creates: sources, articles, entities, synthesized_articles, etc.
       ├─ Creates: crawler_jobs, synthesizer_jobs, embeddings tables
       // NEW - Session 2 Continuation:
       └─ Creates: All columns including last_crawl_at (Migration 015) ✅
    ↓
    Step 2.1: Run Django migrations (Publisher app)
    │
    └─ Executes: python manage.py migrate --fake-initial --noinput
       └─ Creates: news_article, news_publishaudit (Django tables)
    ↓
    Step 3: Wait for ChromaDB and vLLM
    ↓
    Initialization complete
```

---

## 📂 The Two Different Migration Systems

### **System 1: SQL Pipeline Migrations** ✅ (Runs in DevContainer - Step 2)

**Location:** `/app/database/migrations/*.sql`

**Examples:**
```
001_create_initial_tables.sql          ← articles, entities, training_examples
009_create_sources_table.sql           ← sources (core table)
010_canonical_schema_fix.sql           ← Schema corrections
011_ensure_sources_last_verified.sql   ← Verification timestamps
012_create_crawler_tables.sql          ← crawler_jobs, crawler_tasks
013_create_publisher_tables.sql        ← Extended publisher support
014_create_embeddings_tables.sql       ← embeddings_collection, embeddings_document
015_add_last_crawl_at_to_sources.sql   ← NEW: Crawler source tracking ✅ (2026-02-10)
```

**Executed By:** `post-create.sh` (Step 2)
```bash
python /app/apply_migrations_script.py 2>&1 | tee /tmp/sql_migrations.log
```

**Migration Runner:** `/app/apply_migrations_script.py`
- Discovers ALL `.sql` files automatically
- Applies in alphabetical order (001-015)
- Checks `schema_migrations` table to skip already-applied
- Transform PostgreSQL → MariaDB syntax
- Idempotent: Safe to run multiple times

**Tables Created:**
- articles (50+ columns for full pipeline)
- sources ✅ (includes last_crawl_at from Migration 015)
- entities
- synthesized_articles
- crawler_jobs, crawler_tasks, crawler_crawl_results
- synthesizer_jobs
- embeddings_collection, embeddings_document
- sentiment_analysis, bias_analysis
- kg_audit
- ... (15+ tables total)

**Status in DevContainer:** ✅ **RUNS - Step 2 of post-create.sh**

---

### **System 2: Django ORM Migrations** ✅ (Runs in DevContainer - Step 2.1)

**Location:** `/app/justnews_publisher/news/migrations/`

```python
# 0001_initial.py - Creates Article and PublishAudit tables
# 0002_article_category.py - Adds category field
# 0003_publish_audit.py - Creates PublishAudit table
# 0004_backendarticle_livingstory_pendingarticle_and_more.py
```

**Executed By:** `post-create.sh` (Step 2.1)
```bash
python manage.py migrate --fake-initial --noinput
```

**Tables Created:**
- `news_article` (Django ORM - Publisher app)
- `news_publishaudit` (Django ORM - Publisher app)

**Status in DevContainer:** ✅ **RUNS - Step 2.1 of post-create.sh**

---

## ✅ Schema is Complete - Both Systems Work

### **What Post-Create.sh Creates**
```sql
-- SQL Migrations (Step 2):
articles                  -- Core JustNews articles ✅
sources                   -- News source registry ✅ (includes last_crawl_at)
entities                  -- Named entities ✅
sentiment_analysis        -- Sentiment scores ✅
synthesized_articles      -- Generated articles ✅
crawler_jobs              -- Crawl tracking ✅
synthesizer_jobs          -- Synthesis tracking ✅
embeddings_*              -- Vector store tracking ✅
... (+ 7 more tables)

-- Django Migrations (Step 2.1):
news_article              -- Publisher app ✅
news_publishaudit         -- Publisher app ✅
```

### **Result**
✅ Pipeline infrastructure tables present  
✅ Crawler can track source crawl frequency (last_crawl_at)  
✅ Publisher web app works  
✅ Full pipeline operational  

---

## 🔧 Persistence Across Container Rebuilds

### **Migration 015 Example: last_crawl_at Column**

**File:** `/app/database/migrations/015_add_last_crawl_at_to_sources.sql`

```sql
-- UP: Add last_crawl_at column
ALTER TABLE sources
    ADD COLUMN IF NOT EXISTS last_crawl_at TIMESTAMP NULL DEFAULT NULL;

-- Create index for efficient queries
CREATE INDEX IF NOT EXISTS idx_sources_last_crawl_at ON sources(last_crawl_at);

-- Mark migration as applied
INSERT IGNORE INTO schema_migrations (version, applied_at) 
VALUES ('015_add_last_crawl_at_to_sources', NOW());
```

**Why It Persists:**
1. File is in git repository
2. `apply_migrations_script.py` discovers it automatically
3. Runs on EVERY container initialization
4. Idempotent: `IF NOT EXISTS` prevents duplicates
5. Survives volume deletion, container rebuild, fresh clones

**When It Runs:**
- Container is built/rebuilt
- Database volumes are deleted and recreated
- Fresh devcontainer is cloned and built
- Post-create.sh executes for ANY new container

---

## 📊 Verification

To verify migrations are running, check the logs:
```bash
tail -50 /tmp/sql_migrations.log
# Should show:
# "Applying 015_add_last_crawl_at_to_sources.sql..."
# "Applied 015_add_last_crawl_at_to_sources"
```

To verify schema is complete:
```bash
python -c "
import mysql.connector, os
from pathlib import Path
for line in Path('/app/global.env').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k,v = line.split('=',1)
        os.environ[k] = v
conn = mysql.connector.connect(
    host=os.environ.get('MARIADB_HOST'),
    user=os.environ.get('MARIADB_USER'),
    password=os.environ.get('MARIADB_PASSWORD'),
    database=os.environ.get('MARIADB_DB'),
    autocommit=True
)
cursor = conn.cursor()
cursor.execute('SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=\"sources\" AND COLUMN_NAME=\"last_crawl_at\"')
if cursor.fetchone():
    print('✅ Migration 015 verified: last_crawl_at column exists')
conn.close()
```

---

### **Production/Full Deployment Flow:**

```
1. start_all_services.sh (manual execution)
   ├─ Starts MariaDB, ChromaDB, Redis
   ├─ Runs: python manage.py migrate (DJANGO migrations)
   └─ Runs: python apply_migrations_script.py (SQL migrations)
       └─ Creates all 14 tables with full schema
```

### **DevContainer Current Flow:**

```
1. .devcontainer build (automatic)
   ├─ Starts docker-compose
   └─ Runs post-create.sh
       ├─ Waits for MariaDB ✓
       └─ Runs: python manage.py migrate (DJANGO only)
           └─ Creates only Publisher tables (2 tables)
```

---

## 🎯 The Canonical Migration Files ARE the Source

**But they need to be explicitly executed** via either:

### **Option 1: Manual Execution**
```bash
# In devcontainer shell:
python apply_migrations_script.py
```

### **Option 2: During Service Startup**
```bash
# Outside devcontainer:
./start_all_services.sh
```

### **Option 3: Should be Added to post-create.sh** (RECOMMENDATION)
```bash
# Currently NOT here but SHOULD be:
python apply_migrations_script.py
```

---

## 🔴 CRITICAL FINDING

The `.sql` migration files in `/app/database/migrations/` are:

✅ **The canonical source of truth** for schema  
✅ **Version controlled** and comprehensive  
✅ **Properly formatted** for MariaDB  
✅ **Complete** (14 tables, 150+ columns)

**BUT:**

❌ **Not automatically executed** in devcontainer build  
❌ **Only run via start_all_services.sh** (manual script)  
❌ **Requires explicit call** to `apply_migrations_script.py`  
❌ **May cause pipeline failures** if expected tables don't exist

---

## 📋 Current DevContainer Schema Status

After `post-create.sh` completes:

```sql
✅ TABLES CREATED (Django Migrations):
   - news_article
   - news_publishaudit
   - django_migrations (metadata)
   - schema_migrations (metadata - from first apply_migrations if run)

❌ TABLES MISSING (SQL Migrations Not Applied):
   - articles (pipeline core)
   - sources
   - entities
   - article_entities
   - sentiment_analysis
   - article_sentiment_summary
   - bias_analysis
   - training_examples
   - model_metrics
   - synthesized_articles
   - synthesizer_jobs
   - crawler_jobs
   - kg_audit
```

---

## ✅ RECOMMENDATION

Add to `.devcontainer/scripts/post-create.sh` after Django migrations:

```bash
# Step 2.1: Run SQL schema migrations for pipeline infrastructure
log_info ""
log_info "Step 2.1: Running SQL schema migrations for pipeline tables..."
if python apply_migrations_script.py 2>&1 | tee /tmp/sql_migrations.log; then
    log_success "SQL migrations completed (14 tables created)"
else
    log_warning "SQL migrations failed or skipped (check /tmp/sql_migrations.log)"
    log_info "  → Run manually: python apply_migrations_script.py"
fi
```

This would ensure that:
1. All 14 pipeline tables are created automatically
2. The `.sql` migration files are used as intended
3. DevContainer has a complete, consistent schema
4. No surprises when pipeline services try to access tables

---

## Summary

| Aspect | Status | Details |
|--------|--------|---------|
| Are SQL migrations canonical? | ✅ YES | Version-controlled, comprehensive, authoritative |
| Are they in devcontainer build? | ❌ NO | Only Django migrations run, not SQL migrations |
| Would schema be complete? | ❌ NO | Only 2 tables (Publisher); 12 pipeline tables missing |
| Can be manually applied? | ✅ YES | Via `python apply_migrations_script.py` |
| Should be automatic? | ✅ YES | Recommend adding to post-create.sh |

