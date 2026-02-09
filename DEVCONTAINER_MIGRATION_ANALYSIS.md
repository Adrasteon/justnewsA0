# DevContainer Initialization - Migration Execution Analysis

**Date:** February 9, 2026  
**Status:** ⚠️ **CRITICAL DISCOVERY**

---

## ❌ SHORT ANSWER: **NO - Not automatically during devcontainer build**

The `.sql` migration files in `/app/database/migrations/` are **NOT** executed during the devcontainer build cycle. Only Django ORM migrations run in post-create.sh.

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
    post-create.sh STEP 2: "Run Django migrations"
    │
    └─ Executes: python manage.py migrate --fake-initial --noinput
       │
       └─ What it actually runs:
           • Only Django migrations from: /app/justnews_publisher/news/migrations/
           • Creates: Article, PublishAudit tables (Publisher app only)
           • SKIPS: /app/database/migrations/*.sql files entirely
           
           ❌ Does NOT run: apply_migrations_script.py
           ❌ Does NOT create: sources, entities, synthesized_articles, etc.
           ❌ Does NOT create: crawler_jobs, synthesizer_jobs tables
```

---

## 📂 The Two Different Migration Systems

### **System 1: Django ORM Migrations** ✅ (Runs in DevContainer)

**Location:** `/app/justnews_publisher/news/migrations/`

```python
# 0001_initial.py - Creates Article and PublishAudit tables
# 0002_article_category.py - Adds category field
# 0003_publish_audit.py - Creates PublishAudit table
# 0004_backendarticle_livingstory_pendingarticle_and_more.py
```

**Executed By:** `post-create.sh` line 157
```bash
python manage.py migrate --fake-initial --noinput
```

**Tables Created:**
- `news_article` (Django ORM)
- `news_publishaudit` (Django ORM)

**Status in DevContainer:** ✅ **CURRENTLY RUNS**

---

### **System 2: Application/SQL Migrations** ❌ (Does NOT run in DevContainer)

**Location:** `/app/database/migrations/*.sql`

```
001_create_initial_tables.sql          ← articles, entities, training_examples
002_add_sentiment_analysis.sql         ← sentiment_analysis, bias_analysis
003_stage_b_ingestion.sql              ← Extended columns
004_add_synthesis_fields.sql           ← synthesis_status, etc.
005_add_embedded_column.sql            ← embedded flag
005_create_synthesized_articles_table.sql  ← synthesized_articles
006_create_synthesizer_jobs_table.sql  ← synthesizer_jobs
007_add_entities_and_training_examples.sql ← entities tables
008_add_kg_audit_and_entity_columns.sql    ← kg_audit
009_b_create_crawler_jobs.sql          ← crawler_jobs
009_create_sources_table.sql           ← sources
010_canonical_schema_fix.sql           ← Schema corrections
011_ensure_sources_last_verified.sql   ← Verification
```

**Executed By:** `start_all_services.sh` line 524-527 (NOT post-create.sh)

```bash
python apply_migrations_script.py
```

**Executor Script:** `/app/apply_migrations_script.py`

**Tables Created:**
- articles (with 50+ columns for full pipeline)
- sources
- entities
- synthesized_articles
- crawler_jobs
- synthesizer_jobs
- sentiment_analysis
- bias_analysis
- kg_audit
- ... (10+ tables total)

**Status in DevContainer:** ❌ **DOES NOT RUN**

---

## 🚨 This Creates a Schema Conflict

### **What Post-Create.sh Creates**
```sql
-- Django migrations ONLY create:
news_article              -- Publisher app
news_publishaudit         -- Publisher app

-- via: python manage.py migrate
```

### **What's MISSING (Not Created)**
```sql
-- These tables needed by the pipeline are NOT created:
articles                  -- Core JustNews articles
sources                   -- News source registry
entities                  -- Named entities
sentiment_analysis        -- Sentiment scores
synthesized_articles      -- Generated articles
crawler_jobs              -- Crawl tracking
synthesizer_jobs          -- Synthesis tracking
... (+ 7 more tables)
```

### **Result**
✅ Publisher web app works (has Article, PublishAudit)  
❌ Pipeline infrastructure tables missing (articles, sources, entities, etc.)  
❌ Any code importing from `migrated_models.py` expecting pipeline tables will fail

---

## 🔧 How This is Supposed to Work

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

