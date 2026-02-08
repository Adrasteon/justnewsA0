# End-to-End Deployment Simulation Workflow

**Objective:** Simulate production environment by loading real news sources and running full crawl pipeline

**Duration:** 30-60 minutes  
**Status:** Ready to Execute

---

## Overview

```
Step 1: Fix Environment Vars (5 min)
   ↓
Step 2: Load 100 Real News Sources (5 min)
   ↓
Step 3: Verify Sources in Database (2 min)
   ↓
Step 4: Start JustNews System (5 min)
   ↓
Step 5: Run Full Crawl Pipeline (15-30 min)
   ↓
Step 6: Verify Data Population (5 min)
   ↓
Step 7: Analyze Results & Metrics (5 min)
```

---

## Step 1: Fix Environment Configuration

**Problem:** Django subprocess doesn't inherit global.env variables

**Solution:** Create standalone environment file

```bash
# Copy environment to location that Django and scripts can find
cp /app/global.env /app/.env

# Verify these values are present:
grep -E "MARIADB|CHROMADB|VLLM" /app/.env
```

**Expected Output:**
```
MARIADB_HOST=mariadb
MARIADB_PORT=3306
MARIADB_USER=justnews
MARIADB_PASSWORD=dev_justnews_password
MARIADB_DB=justnews
CHROMADB_HOST=chromadb
CHROMADB_PORT=3307
VLLM_HOST=vllm
VLLM_PORT=8001
```

**Verify Django Sees It:**
```bash
cd /app && python3 << 'EOF'
import os
from pathlib import Path
env_file = Path('.env')
for line in env_file.read_text().strip().split('\n'):
    if line and not line.startswith('#'):
        key, _, value = line.partition('=')
        os.environ[key] = value

print(f"MARIADB_HOST: {os.environ.get('MARIADB_HOST')}")
print(f"MARIADB_DB: {os.environ.get('MARIADB_DB')}")
EOF
```

**Expected Output:**
```
MARIADB_HOST: mariadb
MARIADB_DB: justnews
```

---

## Step 2: Load Real News Sources

**Purpose:** Insert 100 real news sources into the database

**Command:**
```bash
cd /app && python load_sources.py
```

**What It Does:**
1. Parses `/app/top_100_sources.md` (100 real news sources)
2. Creates `sources` table if needed
3. Inserts sources into MariaDB
4. Handles duplicates gracefully
5. Provides verification

**Expected Output:**
```
Parsing sources markdown...
✓ Parsed 100 sources from markdown

Checking sources table schema...
✓ Sources table created

Loading 100 sources into database...
  ✓ Loaded 10/100 sources...
  ✓ Loaded 20/100 sources...
  ... (continues to 100)

======================================================================
SOURCES LOADED SUCCESSFULLY
======================================================================
✓ Inserted: 100
⚠ Skipped (already exist): 0
✓ Total in database: 100

VERIFICATION
----------------------------------------------------------------------
✓ Total sources in database: 100
✓ Active sources: 100
✓ Countries: 50
✓ Languages: 2

✓ Sample sources:
    - BBC News (bbc.co.uk)
    - CNN (cnn.com)
    - The New York Times (nytimes.com)
    ...

✓ Sources table size: 45.50 KB

======================================================================
✅ SOURCES READY FOR CRAWLING
======================================================================
```

---

## Step 3: Verify Sources in Database

**Quick Verification:**
```bash
mysql -h mariadb -u justnews -pdev_justnews_password justnews << 'EOF'
-- Check total sources
SELECT COUNT(*) as 'Total Sources' FROM sources;

-- Check active sources by country
SELECT country, COUNT(*) as count FROM sources WHERE is_active=TRUE GROUP BY country ORDER BY count DESC LIMIT 10;

-- Sample sources
SELECT name, domain, country FROM sources WHERE is_active=TRUE LIMIT 10;

-- Database stats
SELECT TABLE_NAME, ROUND(((DATA_LENGTH + INDEX_LENGTH) / 1024), 2) as 'Size KB' 
FROM INFORMATION_SCHEMA.TABLES 
WHERE TABLE_SCHEMA = 'justnews' AND TABLE_NAME IN ('sources', 'articles');
EOF
```

**Expected Output:**
```
Total Sources
100

country  count
US       40
GB       8
...

name                              domain              country
BBC News                          bbc.co.uk           GB
CNN                               cnn.com             US
The New York Times                nytimes.com         US
...

TABLE_NAME     Size KB
sources        45.50
articles       0.00
```

---

## Step 4: Start JustNews System

**Prerequisites:** Database initialized with sources

**Option A: Development Mode (Recommended for Testing)**
```bash
cd /app

# Terminal 1: Start the system
python run_memory_agent.py --dev
```

**Option B: Full System**
```bash
cd /app

# If you need specific startup
python manage.py runserver 0.0.0.0:8000
```

**Verification - Check if running:**
```bash
# In another terminal
curl -s http://localhost:8000/health | jq .

# Expected response:
# {
#   "status": "healthy",
#   "services": {
#     "database": "ok",
#     "cache": "ok"
#   }
# }
```

---

## Step 5: Run Full Crawl Pipeline

**Purpose:** Crawl all 100 sources and populate articles

**Command:**
```bash
cd /app && python run_full_crawl.py
```

**What It Does:**
1. Reads sources from database (all 100 active)
2. Sends crawl request to unified_production_crawl
3. Makes up to 10 requests per source  
4. Concurrent crawl (3 sites at a time)
5. Returns after ~10 articles minimum

**Expected Output:**
```
Fetching active domains...
Found 100 domains.
Sending crawl request...
Success! Job ID: crawl_abc123def456
```

**Monitor Progress:**
```bash
# Option 1: Check articles table
watch -n 5 'mysql -h mariadb -u justnews -pdev_justnews_password justnews -e "SELECT COUNT(*) as Article Count FROM articles;"'

# Option 2: Check by source
mysql -h mariadb -u justnews -pdev_justnews_password justnews << 'EOF'
SELECT 
  s.name, 
  COUNT(a.id) as article_count
FROM sources s
LEFT JOIN articles a ON s.id = a.source_id
GROUP BY s.id
ORDER BY article_count DESC
LIMIT 10;
EOF
```

**Typical Crawl Times:**
- 100 sources × ~10 articles = ~1000 articles
- At 3 concurrent sites = 30-50 minutes total
- Faster with fewer articles per site

---

## Step 6: Verify Data Population

**After crawl completes:**

```bash
# Check total articles
mysql -h mariadb -u justnews -pdev_justnews_password justnews << 'EOF'
SELECT 
  COUNT(DISTINCT source_id) as 'Sources with Articles',
  COUNT(*) as 'Total Articles',
  ROUND(AVG(LENGTH(content)), 0) as 'Avg Article Size (bytes)',
  MIN(published_at) as 'Oldest Article',
  MAX(published_at) as 'Newest Article'
FROM articles;
EOF
```

**Expected Output (after 30-50 min crawl):**
```
Sources with Articles    Total Articles    Avg Article Size    Oldest Article    Newest Article
85-95                    800-1000          5000-8000           2026-02-07        2026-02-08
```

**Verify by Source:**
```bash
mysql -h mariadb -u justnews -pdev_justnews_password justnews << 'EOF'
SELECT s.name, COUNT(a.id) as count
FROM sources s
LEFT JOIN articles a ON s.id = a.source_id
WHERE a.id IS NOT NULL
ORDER BY count DESC
LIMIT 15;
EOF
```

**Expected Output:**
```
name                    count
TechCrunch              12
The Verge               11
CNN                     10
BBC News                9
...
```

---

## Step 7: Analyze Results & Metrics

**Database Statistics:**
```bash
mysql -h mariadb -u justnews -pdev_justnews_password justnews << 'EOF'
-- Storage used
SELECT 
  TABLE_NAME,
  ROUND(((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024), 2) as 'Size (MB)'
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'justnews'
ORDER BY DATA_LENGTH DESC;

-- Article age distribution  
SELECT 
  DATEDIFF(NOW(), DATE(published_at)) as days_old,
  COUNT(*) as count
FROM articles
GROUP BY DATEDIFF(NOW(), DATE(published_at))
ORDER BY days_old;

-- Top sources by article count
SELECT 
  s.name,
  COUNT(a.id) as articles,
  COUNT(DISTINCT DATE(a.published_at)) as days,
  ROUND(AVG(LENGTH(a.content)), 0) as avg_size
FROM sources s
LEFT JOIN articles a ON s.id = a.source_id
WHERE a.id IS NOT NULL
GROUP BY s.id
ORDER BY articles DESC
LIMIT 20;
EOF
```

**Performance Analysis:**
```bash
# Articles ingested per minute
mysql -h mariadb -u justnews -pdev_justnews_password justnews << 'EOF'
SELECT 
  CONCAT(HOUR(created_at), ':00') as hour,
  COUNT(*) as articles
FROM articles
GROUP BY HOUR(created_at)
ORDER BY hour;
EOF
```

---

## Complete Workflow Command Sequence

**For Quick Execution:**

```bash
#!/bin/bash
set -e

echo "📋 Step 1: Environment Configuration"
cp /app/global.env /app/.env
echo "✓ Done\n"

echo "📋 Step 2: Load Sources"
cd /app && python load_sources.py
echo "✓ Done\n"

echo "📋 Step 3: Start System"
echo "Starting JustNews system..."
python run_memory_agent.py --dev &
SYSTEM_PID=$!
sleep 10
echo "✓ System started (PID: $SYSTEM_PID)\n"

echo "📋 Step 4: Run Crawl"
cd /app && python run_full_crawl.py
echo "✓ Crawl queued\n"

echo "📋 Step 5: Monitor Progress"
echo "Checking article count every 30 seconds..."
for i in {1..60}; do
  count=$(mysql -h mariadb -u justnews -pdev_justnews_password justnews -sN -e "SELECT COUNT(*) FROM articles;")
  echo "  Articles: $count"
  sleep 30
done

echo "✓ Done\n"

echo "📋 Step 6: Verify Results"
mysql -h mariadb -u justnews -pdev_justnews_password justnews << 'VERIFY'
SELECT COUNT(*) as 'Total Articles' FROM articles;
SELECT COUNT(DISTINCT source_id) as 'Sources with Content' FROM articles;
VERIFY

echo "✓ Complete!\n"
```

---

## Troubleshooting

### Issue: "Can't connect to MySQL server"
```bash
# Verify mariadb is running
mysql -h mariadb -u justnews -pdev_justnews_password -e "SELECT 1;"

# Check environment
cat /app/.env | grep MARIADB
```

### Issue: "No sources found"
```bash
# Check if sources loaded
mysql -h mariadb -u justnews -pdev_justnews_password justnews \
  -e "SELECT COUNT(*) FROM sources;"

# If 0, reload:
python load_sources.py
```

### Issue: Crawl not returning results
```bash
# Check if system is running
curl -s http://localhost:8000/health

# Check logs
tail -f /tmp/justnews.log  # or wherever logs go

# Reduce crawl scope for testing
# Edit run_full_crawl.py: max_articles_per_site = 2 (instead of 10)
```

### Issue: Out of memory
```bash
# Monitor memory
free -h

# Check what's using memory
ps aux --sort=-%mem | head -5

# Reduce crawl concurrency
# Edit run_full_crawl.py: concurrent_sites = 1 (instead of 3)
```

---

## Success Criteria

✅ **Phase 1 - Environment:** Environment vars properly loaded  
✅ **Phase 2 - Sources:** 100 sources in database  
✅ **Phase 3 - System:** JustNews service running  
✅ **Phase 4 - Crawl:** Crawl job queued successfully  
✅ **Phase 5 - Data:** Articles appearing in database  
✅ **Phase 6 - Volume:** 500+ articles after crawl  
✅ **Phase 7 - Metrics:** Database has real data to work with  

---

## Expected Results After Simulation

**Database State:**
- 100 sources populated (from 50 countries, 2 languages)
- 800-1000 articles crawled
- Database size: 50-100 MB
- Real publication dates and content

**Training Data:**
- Real articles for ML pipeline
- Natural language variation
- Multiple topics and writing styles
- Global news coverage

**System Validation:**
- End-to-end pipeline tested
- Source → Article → Database flow verified
- Crawling infrastructure working
- Database connectivity confirmed

---

## Next Steps After Simulation

1. **Training System Integration**
   - Embeddings generation from crawled articles
   - Training data pipeline validation
   - Model fine-tuning preparation

2. **Production Deployment**
   - Use DEPLOYMENT_PLAYBOOK.md
   - Scale to multiple workers
   - Implement Vault integration
   - Set up monitoring

3. **Monitoring & Optimization**
   - Track crawl success rates
   - Monitor article ingestion rates
   - Optimize source configurations
   - Fine-tune crawl parameters

---

## File References

**New Files:**
- `load_sources.py` - Source loading script
- `.env` - Environment configuration (copied from global.env)

**Existing Files:**
- `run_full_crawl.py` - Crawl orchestration
- `top_100_sources.md` - News source data
- `run_memory_agent.py` - System startup
- `SIMULATION_EXECUTION_REPORT.md` - Previous test results

**Related Documentation:**
- `DEPLOYMENT_SIMULATION_GUIDE.md` - Simulation procedures
- `DEPLOYMENT_PLAYBOOK.md` - Production deployment
- `SECURITY_AUDIT.md` - Security checklist

---

**Ready to Execute:** ✅ All components prepared  
**Estimated Total Time:** 50-70 minutes (mostly waiting for crawl)  
**Next Action:** Begin Step 1 - Environment Configuration

