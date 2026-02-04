# Crawler & Ingestion Metrics Dashboard

## Overview

A new **Crawler & Ingestion Metrics Dashboard** has been created to monitor the ongoing crawl in real-time. This complements the existing publishing dashboards by focusing on the **ingestion phase** of the workflow.

## Dashboard Location

**File:** `monitoring/dashboards/generated/crawler_ingestion_dashboard.json`

## Key Metrics

### 1. **Ingestion Rate (articles/min)**
- Real-time rate of articles being ingested
- Candidates found per minute
- Helps identify when crawling is active/stalled

### 2. **Sites Status**
- **Sites Attempted:** Total number of sites crawl was initiated for
- **Sites Completed:** Total completed sites (regardless of success)
- Expected: 541 total sites

### 3. **Crawl Mode Usage**
- **AI-Enhanced:** Sites using advanced LLM-powered extraction
- **Generic:** Standard pattern-based extraction
- **Crawl4AI Profiled:** Sites using custom extraction profiles
- Status: Currently **100% AI-Enhanced** with `FORCE_AI_ENHANCED_ALL=true`

### 4. **Cumulative Ingestion Metrics**
- **Total Ingested:** Articles successfully added to database
- **Duplicates:** Articles rejected as duplicates
- **Errors:** Ingestion failures
- Helps identify bottlenecks

### 5. **Crawl Obstacles**
- **Paywall Detected:** Sites found behind paywalls
- **No Candidates:** Sites where articles couldn't be found
- Root cause analysis for 0-article sites

### 6. **Top 10 Sites by Articles**
- Ranking of most productive sources
- Helps identify working vs. broken crawlers

## Manual Import Instructions

### Method 1: Grafana UI Direct Import

1. Open Grafana: http://localhost:3000
2. Click **+** (Create) → **Import dashboard**
3. Paste the dashboard JSON from: `monitoring/dashboards/generated/crawler_ingestion_dashboard.json`
4. Set dashboard title: "Crawler & Ingestion Metrics"
5. Click **Import**

### Method 2: Copy to Grafana Provisioning

```bash
# Copy dashboard to provisioning directory
cp monitoring/dashboards/generated/crawler_ingestion_dashboard.json \
   /etc/grafana/provisioning/dashboards/

# Restart Grafana
sudo systemctl restart grafana-server
```

## Expected Results During Current Crawl

### Timeline

| Phase | Duration | Description |
|-------|----------|------------|
| **Warm-up** | 2-5 min | Browser initialization, first batch |
| **Active Crawl** | 2-3 hours | 541 sites × 3 concurrent = ~180 min |
| **Peak Rate** | During active | 20-30 articles/min with AI-enhanced |
| **Tail-off** | 30 min | Finishing slow/blocking sites |

### Current Configuration

✅ **HITL Bypass Enabled** (`ENABLE_HITL_PIPELINE=false`)
- Recovering ~318 stalled sites that were blocked before

✅ **AI-Enhanced Crawling** (`FORCE_AI_ENHANCED_ALL=true`)
- Advanced extraction for all 541 sites

✅ **LoRA Training** (`VLLM_ENABLE_LORA=true`)
- Adapters improving as articles flow through

### Success Metrics

**Before Crawl:**
- Articles: 2,945 (baseline)
- Sources: 406 (75%)
- 0-article sites: 135 (25%)

**Expected After Crawl:**
- Articles: 4,000+ (gain ~1,000+)
- Sources: ~495 (92%)
- 0-article sites: ~45 (8%)

## Real-Time Monitoring Commands

### Check by Database

```bash
# Current article count
conda run -n justnews-py312-phase1 python -c "
from database.utils.migrated_database_utils import create_database_service
db = create_database_service()
db.ensure_conn()
conn = db.get_connection()
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM articles')
print(f'Articles: {cursor.fetchone()[0]:,}')
cursor.close()
db.close()
"
```

### Check Crawler Logs

```bash
# Watch real-time crawler activity
tail -f /tmp/crawler_batch.log | grep -E "(Completed|Generic|AI-enhanced|candidates|ingested)"

# Get latest status
tail -50 /tmp/crawler_batch.log | grep -E "🏁|candidates|ingested"
```

### Check Job Status

```bash
# Query crawler agent for job details
curl -s http://localhost:8015/job/e9cfeac24ee3402aa94e01a38e41efbe | python -m json.tool
```

## Dashboard Panels Explained

### Ingestion Rate
- **Y-axis:** articles/min
- **X-axis:** Time
- **Target:** 20-30 articles/min (peak), declining as sites complete

### Mode Distribution
- **Stacked bar** showing usage of each crawl strategy
- Should show 100% AI-Enhanced currently

### Cumulative Metrics
- **Monotonically increasing** (never decrease)
- Total is sum of: New Ingested + Duplicates + Errors

### Obstacles
- **Decreases** as HITL bypass recovers blocked sites
- Should see reduction in "Ingestion Stalled" after restart

### Top Sites Rankings
- Shows which sources are most productive
- Helps identify if specific domains are having issues

## Troubleshooting

### Panel Shows "No Data"

This is expected if:
1. ✅ Prometheus not yet collecting these metrics (they may not be exposed)
2. ✅ Crawl just started (data collection has 30-60s latency)
3. ✅ Metrics names in Prometheus don't match panel queries

**Solution:** Check available metrics in Prometheus:
```
http://localhost:9090/api/v1/label/__name__/values
```

Look for metrics starting with `justnews_crawler_*`

### Dashboard Not Appearing in Grafana

1. Verify Grafana is running: `curl http://localhost:3000`
2. Check if JSON file exists: `ls monitoring/dashboards/generated/crawler_ingestion_dashboard.json`
3. Manual import via UI (see Method 1 above)

## Metrics Collection

The dashboard queries these Prometheus metrics (must be exported by crawler):

- `justnews_crawler_articles_ingested_total` - Cumulative articles
- `justnews_crawler_sites_attempted_total` - Total sites attempted
- `justnews_crawler_sites_completed_total` - Sites finished
- `justnews_crawler_mode_usage{mode="ai_enhanced"}` - AI-Enhanced usage
- `justnews_crawler_paywall_detections_total` - Paywall blocks
- `justnews_crawler_no_candidates_total` - No-articles found
- `justnews_crawler_duplicates_total` - Duplicate articles
- `justnews_crawler_ingestion_errors_total` - Ingestion failures

If these metrics aren't available, see [CrawlerEngine](../../agents/crawler/crawler_engine.py) for metric initialization.

## Next Steps

1. **Import the dashboard** (manual UI or provision)
2. **Refresh every 30s** to see progress
3. **Monitor rates:** Should see 20-30 articles/min during peak
4. **Watch endpoints** decline as crawl progresses through all sites
5. **Final check:** Compare before/after article counts

---

**Dashboard Created:** 2026-02-04  
**Crawl Job ID:** e9cfeac24ee3402aa94e01a38e41efbe  
**Expected Completion:** ~2-4 hours from start
