# Grafana Dashboards - Comprehensive Analysis & Fixes

**Date**: February 4, 2026  
**Status**: Analysis complete - Fixed versions created

---

## Executive Summary

**Critical Issues Found**:
- ❌ **Business Metrics Dashboard**: 100% broken (0/7 panels functional)
- ❌ **Operations Dashboard**: 93% broken (1/14 panels functional)
- ⚠️ **System Overview Dashboard**: 27% broken (4/15 panels with missing GPU metrics)

**Root Cause**: Dashboards reference metrics that are not being exported by the JustNews services.

---

## Detailed Dashboard Analysis

### 1. System Overview Dashboard

**File**: `monitoring/dashboards/generated/system_overview_dashboard.json`

#### Issues
| Panel | Status | Issue | Fix |
|-------|--------|-------|-----|
| Fleet Availability | ✅ Works | Uses `up{job=~"justnews-.*"}` | Keep as-is |
| Average CPU (%) | ✅ Works | Uses `node_cpu_seconds_total` | Keep as-is |
| Average Memory (%) | ✅ Works | Uses `node_memory_*` | Keep as-is |
| Average Disk Usage (%) | ✅ Works | Uses `node_filesystem_*` | Keep as-is |
| CPU Usage by Instance | ✅ Works | Time series of CPU | Keep as-is |
| Memory Usage by Instance | ✅ Works | Time series of memory | Keep as-is |
| Load Average (1m) | ✅ Works | Uses `node_load1` | Keep as-is |
| Network Throughput | ✅ Works | Uses `node_network_*` | Keep as-is |
| Disk Pressure Hotspots | ✅ Works | Uses `node_filesystem_*` | Keep as-is |
| **GPU Utilization** | ❌ BROKEN | `nvidia_gpu_utilization_ratio` missing | **REMOVED** |
| **GPU Memory Usage** | ❌ BROKEN | `nvidia_gpu_memory_used_bytes` missing | **REMOVED** |
| **GPU Temperature** | ❌ BROKEN | `nvidia_gpu_temperature_celsius` missing | **REMOVED** |
| **GPU Power Draw** | ❌ BROKEN | `nvidia_gpu_power_draw_watts` missing | **REMOVED** |
| MCP Bus Overall Health | ✅ Works | Uses `justnews_agent_health_status` | Keep as-is |
| MCP Bus Agent Status | ✅ Works | Uses `justnews_agent_health_status` | Keep as-is |

**Action Taken**: ✅ GPU panels (10-13) removed. File updated in place.

**Recommendation**: To restore GPU monitoring:
1. Install NVIDIA GPU Prometheus exporter
2. Configure exporter to emit `nvidia_gpu_*` metrics
3. Uncomment GPU panels or recreate them once metrics available

---

### 2. Business Metrics Dashboard

**File**: `monitoring/dashboards/generated/business_metrics_dashboard.json`

#### Issue Summary
**Status**: 🔴 **COMPLETELY NON-FUNCTIONAL**

All 7 panels depend on metrics that are **not being exported**:

| Panel | Status | Missing Metric | Impact |
|-------|--------|---|--------|
| Stage 1 Extraction Outcomes | ❌ | `justnews_stage_b_extraction_articles_total` | No data |
| Stage 2 Ingestion Outcomes | ❌ | `justnews_stage_b_ingestion_articles_total` | No data |
| Embedding Status | ❌ | `justnews_stage_b_embedding_total` | No data |
| Extraction Fallback Outcomes | ❌ | `justnews_stage_b_extraction_fallback_total` | No data |
| Editorial Acceptance Ratio | ⚠️ | Chart exists but uses histogram incorrectly | Incorrect calculation |
| Harness Runs | ❌ | `justnews_stage_b_editorial_harness_total` | No data |
| Adaptive Sufficiency Rate | ❌ | `justnews_crawler_scheduler_adaptive_articles_*` | No data |

#### Solution
**File Created**: `monitoring/dashboards/generated/business_metrics_dashboard_fixed.json`

**New Dashboard Uses**:
- ✅ `justnews_stage_b_editorial_acceptance` - Editorial metrics
- ✅ `justnews_stage_b_publishing_latency_seconds` - Publishing performance
- ✅ `justnews_requests_total` - General throughput
- ✅ `justnews_active_connections` - Connection tracking
- ✅ `justnews_processing_queue_size` - Queue health
- ✅ `justnews_agent_health_status` - Agent status
- ✅ `justnews_request_duration_seconds` - Request latency

**Panels in Fixed Version**:
1. Editorial Acceptance Rate (24h) ✅
2. Publishing Latency p95 ✅
3. Request Rate (5m) ✅
4. Active Connections ✅
5. Processing Queue Depth ✅
6. Agent Health Status ✅
7. Request Latency Distribution ✅
8. Request Rate by Agent ✅
9. Publishing Latency Trends ✅

---

### 3. Operations Dashboard

**File**: `monitoring/dashboards/generated/justnews_operations_dashboard.json`

#### Issue Summary
**Status**: 🔴 **MOSTLY NON-FUNCTIONAL** (1/14 panels working)

| Panel | Status | Metric | Issue |
|-------|--------|--------|-------|
| Domains Crawled (6h) | ❌ | `justnews_crawler_scheduler_domains_crawled_total` | Not exported |
| Articles Accepted (6h) | ❌ | `justnews_crawler_scheduler_articles_accepted_total` | Not exported |
| Adaptive Articles (6h) | ❌ | `justnews_crawler_scheduler_adaptive_articles_total` | Not exported |
| Editorial Acceptance (24h) | ❌ | `justnews_stage_b_editorial_harness_total` | Not exported |
| Scheduler Lag (p95) | ❌ | `justnews_crawler_scheduler_lag_seconds` | Not exported |
| **Crawler Throughput** | ✅ | `justnews_requests_total` | **WORKS** |
| Stage B Extraction | ❌ | `justnews_stage_b_extraction_articles_total` | Not exported |
| Stage B Ingestion | ❌ | `justnews_stage_b_ingestion_articles_total` | Not exported |
| Stage B Embedding | ❌ | `justnews_stage_b_embedding_total` | Not exported |
| Fallback Usage | ❌ | `justnews_stage_b_extraction_fallback_total` | Not exported |
| Adaptive Sufficiency | ❌ | `justnews_crawler_scheduler_adaptive_articles_sufficient_total` | Not exported |
| Adaptive Stop Reasons | ❌ | `justnews_crawler_scheduler_adaptive_stop_reasons_total` | Not exported |
| Editorial Harness Outcomes | ❌ | `justnews_stage_b_editorial_harness_total` | Not exported |
| Pipeline Error Rate | ❌ | `justnews_errors_total` | Not exported |

#### Solution
**File Created**: `monitoring/dashboards/generated/operations_dashboard_fixed.json`

**New Dashboard Structure**:
1. Total Requests (6h) ✅
2. Current Request Rate (5m) ✅
3. Queue Depth ✅
4. Active Connections ✅
5. Request Rate (1m rolling) ✅
6. Queue Depth Over Time ✅
7. Request Latency Distribution ✅
8. Requests by Agent Type ✅
9. Publishing Latency (p50/p95/p99) ✅
10. Editorial Acceptance Distribution ✅
11. Agent Health Status Table ✅

---

## Available Metrics

### JustNews Custom Metrics (Both Exported and Working)

| Metric | Type | Description | Status |
|--------|------|-------------|--------|
| `justnews_active_connections` | Gauge | Active client connections | ✅ |
| `justnews_agent_health_status` | Gauge | Health state per agent (0-4) | ✅ |
| `justnews_processing_queue_size` | Gauge | Items in process queue | ✅ |
| `justnews_request_duration_seconds` | Histogram | HTTP request latency | ✅ |
| `justnews_requests_total` | Counter | Total requests processed | ✅ |
| `justnews_stage_b_editorial_acceptance` | Histogram | Editorial acceptance ratio | ✅ |
| `justnews_stage_b_publishing_latency_seconds` | Histogram | Publishing latency | ✅ |

### Node Exporter Metrics (System Infrastructure)

| Metric | Type | Description | Status |
|--------|------|-------------|--------|
| `node_cpu_seconds_total` | Counter | CPU time per mode | ✅ |
| `node_memory_*_bytes` | Gauge | Memory metrics | ✅ |
| `node_filesystem_*_bytes` | Gauge | Disk metrics | ✅ |
| `node_load1` | Gauge | 1-minute load average | ✅ |
| `node_network_*_bytes_total` | Counter | Network throughput | ✅ |
| `up{job=~"..."}` | Gauge | Service availability | ✅ |

### NOT EXPORTED (Missing from Agents)

| Category | Missing Metrics | Impact |
|----------|---|---------|
| **Crawler Pipeline** | `justnews_crawler_scheduler_*` | Cannot track crawl throughput |
| **Stage B Extraction** | `justnews_stage_b_extraction_articles_total` | Cannot track extraction results |
| **Stage B Ingestion** | `justnews_stage_b_ingestion_articles_total` | Cannot track ingestion results |
| **Stage B Embedding** | `justnews_stage_b_embedding_total` | Cannot track embedding status |
| **GPU Monitoring** | `nvidia_gpu_*` | GPU metrics unavailable |
| **Error Tracking** | `justnews_errors_total` | Cannot track error rates by agent |

---

## Recommendations

### Immediate Actions (Priority 1)

1. **Replace Old Dashboards**
   ```bash
   # Replace old versions with fixed versions
   cp /monitoring/dashboards/generated/business_metrics_dashboard_fixed.json \
      /monitoring/dashboards/generated/business_metrics_dashboard.json
   
   cp /monitoring/dashboards/generated/operations_dashboard_fixed.json \
      /monitoring/dashboards/generated/justnews_operations_dashboard.json
   ```

2. **Reload Grafana**
   ```bash
   curl -X POST http://localhost:3000/api/admin/provisioning/dashboards/reload
   ```

### Short-Term (Priority 2)

1. **Implement Missing Metrics in Agents**
   - Add `justnews_crawler_scheduler_*` metrics to crawler
   - Add `justnews_stage_b_extraction_articles_total` to extraction pipeline
   - Add `justnews_stage_b_ingestion_articles_total` to ingestion
   - Add `justnews_stage_b_embedding_total` to embedding
   - Add `justnews_errors_total` with agent label

2. **Enable GPU Monitoring** (if GPUs available)
   - Install NVIDIA GPU Prometheus exporter
   - Configure to emit `nvidia_gpu_*` metrics
   - Restore GPU panels in System Overview

### Long-Term (Priority 3)

1. **Create Agent-Specific Dashboards**
   - Use `infrastructure/monitoring/grafana_dashboard_agents.json` as base
   - Add per-agent metrics and performance indicators

2. **Implement SLI/SLO Tracking**
   - Create service level objective dashboards
   - Track request latency SLOs
   - Track uptime/availability SLOs

3. **Add Alerts**
   - Queue depth exceeds threshold
   - Publishing latency p95 exceeds SLO
   - Agent health status degraded
   - Request error rate spike

---

## Testing the Fixes

### Verify New Dashboards Load

1. Access Grafana: http://localhost:3000
2. Navigate to: Dashboards → General
3. Check that fixed dashboards show data for:
   - Request rates
   - Latency percentiles
   - Queue depth
   - Active connections
   - Agent health

### Verify No "No Data" Panels

All panels should show one of:
- ✅ Data with trends or current value
- ⚠️ Gray panel with "No data in response" (acceptable if metric not yet exposed)
- ❌ Red error (indicates broken query - SHOULD NOT OCCUR in fixed versions)

---

## Summary of Changes

| Dashboard | Status | Action | File |
|-----------|--------|--------|------|
| System Overview | ⚠️ Fixed | Removed 4 GPU panels | `system_overview_dashboard.json` (updated) |
| Business Metrics | 🔴→✅ | Recreated with available metrics | `business_metrics_dashboard_fixed.json` (new) |
| Operations | 🔴→✅ | Recreated with available metrics | `operations_dashboard_fixed.json` (new) |

---

## Metrics Gap Analysis - Implementation Priority

To restore full dashboard functionality, implement these metrics in this order:

**Phase 1 (Highest Impact)**:
- `justnews_crawler_scheduler_domains_crawled_total` - Tracks crawl volume
- `justnews_stage_b_extraction_articles_total{result}` - Extraction outcomes
- `justnews_stage_b_ingestion_articles_total{status}` - Ingestion success/failure

**Phase 2 (Medium Impact)**:
- `justnews_stage_b_embedding_total{status}` - Embedding tracking
- `justnews_errors_total{agent,type}` - Error tracking by agent
- `justnews_crawler_scheduler_adaptive_articles_*` - Adaptive crawling metrics

**Phase 3 (Lower Impact)**:
- `nvidia_gpu_*` - GPU metrics (if applicable)
- `justnews_stage_b_extraction_fallback_total` - Fallback tracking
- `justnews_crawler_scheduler_adaptive_stop_reasons_total` - Stop reason tracking

---

**Document Version**: 2.0  
**Last Updated**: 2026-02-04T00:00:00Z  
**Status**: Ready for implementation
