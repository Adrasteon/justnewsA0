# JustNews Enterprise Dashboards - Complete Guide

**Last Updated:** February 3, 2026  
**Version:** 2.0 - Full Suite Implementation  
**Audience:** Operations, SRE, DevOps Teams

---

## 📊 Dashboard Suite Overview

The JustNews monitoring system provides **5 enterprise-grade Grafana dashboards** for complete system visibility:

| Dashboard | Purpose | Audience | Refresh Rate | Historical Window |
|-----------|---------|----------|--------------|-------------------|
| **System Health & Infrastructure** | Infrastructure monitoring, resource utilization, hotspot analysis | Infrastructure teams | 10s | 24h |
| **Request Performance & Throughput** | API latency distribution, throughput trends, per-agent performance | Operations, Product | 10s | 24h |
| **Pipeline Quality & Publishing** | Editorial acceptance rates, publishing latency, content metrics | Editorial, Publishing | 10s | 24h |
| **Agent Health & Status** | Per-agent health, connectivity, operational metrics | DevOps, Agents team | 10s | 24h |
| **Operational Overview** | Single pane of glass - key metrics consolidated | C-Level ops, On-call | 10s | 24h |

All dashboards use **Prometheus as the data source** and refresh every **10 seconds** for real-time monitoring.

---

## 🎯 Dashboard 1: System Health & Infrastructure

**File:** `system_health_dashboard.json`  
**UID:** `system-health-premium`  
**Use Case:** Comprehensive system infrastructure monitoring

### Purpose
Monitor the underlying infrastructure (CPU, memory, disk, network) and identify resource bottlenecks before they impact application performance.

### Metrics Reference

#### Fleet Availability
- **Metric:** Custom calculation from node status
- **What it measures:** Percentage of healthy infrastructure nodes
- **Healthy Range:** 100%
- **Alert Threshold:** < 95%

#### CPU Utilization
- **Metric:** `node_cpu_seconds_total` (rate over 5 minutes)
- **Calculation:** `1 - (idle CPU rate)`
- **Healthy Range:** 0-70%
- **Yellow Threshold:** 75%
- **Red Threshold:** 90%
- **Interpretation:**
  - **0-50%:** Ideal operating range
  - **50-75%:** Normal, acceptable
  - **75-90%:** High - investigate if sustained
  - **90%+:** Critical - immediate action needed

#### Memory Utilization
- **Metric:** `node_memory_MemAvailable_bytes` / `node_memory_MemTotal_bytes`
- **Calculation:** `1 - (available / total)`
- **Healthy Range:** 0-70%
- **Yellow Threshold:** 75%
- **Red Threshold:** 90%
- **Interpretation:**
  - **0-60%:** Optimal
  - **60-75%:** Good
  - **75-90%:** High - monitor trends
  - **90%+:** Critical - may impact performance

#### Disk Utilization
- **Metric:** `node_filesystem_avail_bytes` / `node_filesystem_size_bytes`
- **Interpretation:** Percentage of available (free) space
- **Green Threshold:** > 10% free
- **Yellow Threshold:** 5-10% free
- **Red Threshold:** < 2% free
- **Note:** This is inverted - we want HIGH available percentage

#### Load Average
- **Metric:** `node_load1`
- **Healthy Range:** < (number of CPU cores)
- **Interpretation:**
  - **< cores:** System has spare capacity
  - **= cores:** Full utilization but responsive
  - **> cores:** Overloaded - queuing occurring

#### Disk I/O
- **Metrics:** `node_disk_read_bytes_total`, `node_disk_write_bytes_total`
- **Calculation:** Rate over 1 minute
- **Units:** MB/s
- **Healthy Range:** Depends on storage type (SSD vs HDD)
- **Investigation Trigger:** Sustained > 500 MB/s

#### Network I/O
- **Metrics:** `node_network_transmit_bytes_total`, `node_network_receive_bytes_total`
- **Calculation:** Rate over 1 minute
- **Units:** Bps (bytes per second)
- **Expectations:**
  - **Transmit:** Crawler output, results to vector DB
  - **Receive:** Vector store results, API responses

### Panel Breakdown

1. **Fleet Availability (Stat):** Overall infrastructure health percentage
2. **CPU Utilization (Stat):** Current CPU usage - color changes indicate stress
3. **Memory Utilization (Stat):** Current memory usage - critical for OTel and vLLM
4. **Disk Utilization (Stat):** Free space available - watch for growth trends
5. **Load Average 1min (Stat):** System load relative to CPU cores
6. **CPU Utilization Trend (Timeseries):** 24h CPU history - identify patterns
7. **Memory Usage Trend (Timeseries):** 24h memory history - watch for leaks
8. **Disk Space Trend (Timeseries):** 24h disk usage - forecast full disks
9. **Network Transmit (Timeseries):** Outgoing bytes per second
10. **Network Receive (Timeseries):** Incoming bytes per second
11. **Disk Read/Write (Timeseries):** I/O patterns - identify I/O bottlenecks
12. **Hotspot Analysis (Heatmap/Table):** Which nodes are consuming resources

### When to Alert

- **CPU > 90%:** Immediate investigation needed
- **Memory > 90%:** Possible OOM approaching
- **Disk < 5% free:** Storage may fill unexpectedly
- **Load > 4x CPU cores:** System saturated
- **Network Spikes:** Unusual traffic patterns

---

## 📈 Dashboard 2: Request Performance & Throughput

**File:** `request_performance_dashboard.json`  
**UID:** `request-performance-premium`  
**Use Case:** API request latency, throughput, and per-agent performance analysis

### Purpose
Track application performance from the end-user perspective - how fast requests are being processed and how many requests the system is handling.

### Metrics Reference

#### Throughput (Requests per Second)
- **Metric:** `justnews_requests_total` (rate over 1 minute)
- **Units:** req/s
- **Healthy Range:** Depends on deployment size
- **Typical Production:** 10-100 req/s
- **Peak Capacity:** Up to 500 req/s (with scaling)
- **What it means:**
  - **Higher is better** (up to capacity limits)
  - **Sustained drop** suggests system degradation
  - **Spikes** are normal during crawls

#### Latency Percentiles
- **Metric:** `justnews_request_duration_seconds` histogram
- **Units:** milliseconds (converted from seconds)

##### P50 (Median Latency)
- **Healthy:** 100-300 ms
- **Yellow:** 300-500 ms
- **Red:** > 500 ms
- **Interpretation:** 50% of requests complete within this time

##### P95 (95th Percentile)
- **Healthy:** 500-1000 ms
- **Yellow:** 1000-2000 ms
- **Red:** > 2000 ms
- **Interpretation:** 95% of requests complete within this time

##### P99 (99th Percentile)
- **Healthy:** 1000-2000 ms
- **Yellow:** 2000-5000 ms
- **Red:** > 5000 ms
- **Interpretation:** 99% of requests complete within this time; worst-case scenario

### Panel Breakdown

1. **Throughput Stat (Req/s):** Current request rate
2. **Latency P50 Stat (ms):** Median response time
3. **Latency P95 Stat (ms):** 95th percentile response time
4. **Latency P99 Stat (ms):** Worst-case response time
5. **Throughput Over Time (Timeseries):** Request rate trends
6. **Per-Agent Throughput (Timeseries):** Which agents handling most requests
7. **Latency Distribution (Timeseries):** All three percentiles on one chart
8. **Latency by Agent (Timeseries):** Per-agent latency performance
9. **Request Rate Heatmap:** Burst patterns across time
10. **Cumulative Requests (Counter):** Total requests processed
11. **Request Success Rate:** Derived from error metrics
12. **Throughput Forecast (Trend):** Extrapolated capacity planning

### SLOs (Service Level Objectives)

| Objective | Target | Threshold |
|-----------|--------|-----------|
| Latency P99 | < 2,000 ms | Yellow at 2s, Red at 5s |
| Throughput | ≥ 10 req/s average | Alert if < 5 req/s |
| Availability | 99.5% | Alert if < 95% |

### When to Alert

- **P99 > 5000ms:** Severe performance degradation
- **Throughput < baseline - 30%:** Possible system issue
- **Latency spike:** Check CPU/Memory/Disk on System Health dashboard
- **Per-agent latency outlier:** Check Agent Health & Status dashboard

---

## 🎯 Dashboard 3: Pipeline Quality & Publishing

**File:** `pipeline_quality_dashboard.json`  
**UID:** `pipeline-quality-premium`  
**Use Case:** Editorial acceptance, publishing latency, and content quality metrics

### Purpose
Monitor the downstream pipeline (Stage B) where editorial decisions are made and content is published. Track quality metrics and publishing performance.

### Metrics Reference

#### Editorial Acceptance Rate
- **Metric:** `justnews_stage_b_editorial_acceptance` histogram
- **Units:** Percentunit (0.0 - 1.0)

##### Median Acceptance
- **Healthy:** > 80% (0.80)
- **Yellow:** 60-80% (0.60-0.80)
- **Red:** < 60% (< 0.60)
- **Interpretation:**
  - **High rate (>80%):** Editorial quality standards being met
  - **Declining trend:** Quality controls may need adjustment
  - **Sudden drop:** Possible issue with content or agents

##### P50/P95/P99 Acceptance Distribution
- Shows spread of editorial decisions
- Wide spread = inconsistent quality
- Narrow spread = consistent editorial standards

#### Publishing Latency
- **Metric:** `justnews_stage_b_publishing_latency_seconds` histogram
- **Units:** milliseconds (converted from seconds)

##### P50 Publishing Latency
- **Healthy:** < 1,000 ms (1 second)
- **Yellow:** 1,000-5,000 ms
- **Red:** > 5,000 ms
- **Interpretation:** Time from editorial approval to published state

##### P95 Publishing Latency
- **Healthy:** < 3,000 ms
- **Yellow:** 3,000-10,000 ms
- **Red:** > 10,000 ms
- **Interpretation:** Worst-case publishing delay

##### P99 Publishing Latency
- **Healthy:** < 10,000 ms (10 seconds)
- **Yellow:** 10,000-30,000 ms
- **Red:** > 30,000 ms
- **Interpretation:** Absolute worst-case scenario

### Panel Breakdown

1. **Editorial Acceptance (Stat):** Current median acceptance rate
2. **Publishing Latency P50 (Stat):** Typical publishing time
3. **Publishing Latency P95 (Stat):** 95th percentile publishing time
4. **Publishing Latency P99 (Stat):** Worst-case publishing time
5. **Acceptance Rate Trend (Timeseries):** Quality trends over 24h
6. **Acceptance Distribution (Timeseries):** All percentiles showing spread
7. **Publishing Latency P50/P95/P99 (Timeseries):** Latency distribution trends
8. **Hourly Acceptance Rate (Timeseries):** Per-hour quality view
9. **Per-Window Acceptance (Table):** Acceptance by content type/source
10. **24-Hour Quality Summary (Stat):** Aggregate quality metric

### Quality Thresholds

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| Editorial Acceptance | > 80% | 60-80% | < 60% |
| Publishing P50 | < 1s | 1-5s | > 5s |
| Publishing P95 | < 3s | 3-10s | > 10s |
| Publishing P99 | < 10s | 10-30s | > 30s |

### When to Alert

- **Acceptance rate drops > 20%:** Investigate editorial policy or content quality
- **Publishing P99 > 30s:** Check database and API health
- **Sustained high latency:** May indicate queue backlog, check Operations dashboard
- **Quality metrics trending down:** Possible training data or model quality issue

---

## 🚀 Dashboard 4: Agent Health & Status

**File:** `agent_status_dashboard.json`  
**UID:** `agent-status-premium`  
**Use Case:** Per-agent health, connectivity, and operational tracking

### Purpose
Monitor individual agent services - their health status, connectivity, and how the fleet is distributed and operating.

### Metrics Reference

#### Fleet Health Status
- **Metric:** `justnews_agent_health_status{target="overall"}`
- **Values:**
  - `0` = Healthy (green)
  - `1` = Degraded (orange)
  - `2` = Unhealthy (red)
  - `3` = Unreachable (red)
  - `4` = Unknown (gray)

#### Per-Agent Health Status
- **Metric:** `justnews_agent_health_status{target="per_agent"}`
- **Same scale as above**
- **Shown in tabular format** for easy identification of problematic agents

#### Healthy Agents Count
- **Metric:** `sum(justnews_agent_health_status{target="per_agent"} == 0)`
- **Healthy:** Count ≥ (total agents - 1)
- **Degraded:** Count 50-100% of total
- **Unhealthy:** Count < 50% of total

#### Degraded vs Unhealthy Count
- **Degraded agents:** `health_status == 1` (services running, possible performance issues)
- **Unhealthy agents:** `health_status >= 2` (services not responding or crashed)
- **Alert if:** Any unhealthy agents for > 5 minutes

#### Active Connections
- **Metric:** `justnews_active_connections`
- **Indicates:** Total active client connections
- **Healthy:** Stable, predictable patterns
- **Alert if:** Sudden spike (> 2x baseline) or complete drop

#### Queue Depth
- **Metric:** `justnews_processing_queue_size`
- **Indicates:** Work items waiting for processing
- **Healthy:** < 1,000 items
- **Yellow:** 1,000-5,000 items
- **Red:** > 5,000 items
- **Interpretation:**
  - **Growing queue:** System cannot keep up with demand
  - **Draining queue:** Processing backlog being cleared
  - **Zero queue:** All work processed immediately

### Panel Breakdown

1. **Overall Fleet Health (Stat):** Health status for entire fleet
2. **Healthy Agents (Stat):** Count of agents in healthy state
3. **Degraded Agents (Stat):** Count of agents with issues
4. **Unhealthy Agents (Stat):** Count of agents not responding
5. **Agent Health Status Table:** All agents with current health
6. **Fleet Health Over Time (Timeseries):** Health status trends
7. **Degraded/Unhealthy Count (Timeseries):** Problem agent trends
8. **Active Connections (Timeseries):** Connection count over time
9. **Queue Depth (Timeseries):** Work queue size trends

### Agent Health Escalation

| Condition | Duration | Action |
|-----------|----------|--------|
| 1 agent degraded | < 5 min | Monitor |
| 1 agent degraded | > 5 min | Page on-call |
| 1 agent unhealthy | Any | Page on-call immediately |
| 50%+ agents degraded | Any | Incident |
| Any agent unreachable | Any | Page on-call |

### When to Alert

- **Unhealthy agents:** Immediate attention - restart or investigate
- **Degraded agents increasing:** Trend may indicate systemic issue
- **Queue depth > 5,000:** Performance degrading, may need scaling
- **Connections dropping to 0:** Possible network issue or service crash

---

## 🎛️ Dashboard 5: Operational Overview

**File:** `operational_overview_dashboard.json`  
**UID:** `operational-overview-premium`  
**Use Case:** Single pane of glass - consolidated key metrics for on-call and executives

### Purpose
Provide a high-level summary of all critical metrics in one consolidated view. Designed for:
- On-call engineers (quick health check)
- Executives (health status briefings)
- War rooms (shared incident view)

### Key Metrics (All at a Glance)

1. **Fleet Health** - Is the system healthy?
2. **CPU/Memory/Disk Utilization** - Are resources available?
3. **Network Health** - Is network I/O normal?
4. **Active Agents** - How many agents are running?
5. **Throughput** - How many requests/sec?
6. **Latency (P50/P95/P99)** - Is performance acceptable?
7. **Queue Depth** - Is work backing up?
8. **Active Connections** - Are clients connected?
9. **Editorial Acceptance** - Is quality acceptable?
10. **Publishing Latency** - How long to publish?
11. **Total Requests (24h)** - Daily volume
12. **Trends** - Visual timeseries of key metrics

### SLO Quick Reference

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Fleet Health | Healthy (0) | Degraded (1+) |
| CPU Util | < 70% | > 90% |
| Memory Util | < 70% | > 90% |
| Disk Free | > 10% | < 5% |
| Throughput | ≥ baseline | < 30% of baseline |
| Latency P99 | < 2s | > 5s |
| Queue Depth | < 1,000 | > 5,000 |
| Acceptance Rate | > 80% | < 60% |
| Publishing P50 | < 1s | > 5s |

### When to Page On-Call

🔴 **Critical (Page Immediately):**
- Fleet Health = Unhealthy or Unreachable
- Unhealthy agents ≥ 1
- CPU > 95%
- Memory > 95%
- Disk < 2%
- Latency P99 > 10s
- Queue depth > 100k
- Acceptance rate < 30%

🟠 **Urgent (Page Within 5 min):**
- CPU > 90% sustained
- Memory > 90% sustained
- Queue depth > 5,000 sustained
- Publishing latency P95 > 10s
- Degraded agents ≥ 2

🟡 **Monitor (Check within 30 min):**
- Each degraded agent
- Disk free < 5%
- Acceptance rate < 60%
- Latency P95 > 3s

### Executive Briefing

Use this dashboard for executive reporting:
- **Availability:** Fleet Health stat
- **Performance:** Latency stats and throughput trend
- **Capacity:** Queue depth and resource utilization
- **Quality:** Editorial Acceptance and Publishing Latency
- **Volume:** Total Requests (24h) and throughput trend

---

## 🔧 Common Troubleshooting Guide

### Symptom: High CPU Usage

1. Check **System Health dashboard** → CPU panel
2. Identify affected nodes in hotspot panel
3. Check **Request Performance dashboard** → Throughput (is load high?)
4. Check **Agent Health dashboard** → Queue depth (is work queued?)
5. If sustained, scale horizontally or investigate resource leak

### Symptom: High Latency

1. Check **Request Performance dashboard** → Latency panels
2. Check **System Health dashboard** → Resource utilization (CPU/Memory/Disk?)
3. Check **Agent Health dashboard** → Queue depth (is system backed up?)
4. Check **Operational Overview dashboard** → All metrics
5. Correlate with recent deployments or configuration changes

### Symptom: Low Acceptance Rate

1. Check **Pipeline Quality dashboard** → Editorial Acceptance panels
2. Review editorial policies and acceptance thresholds
3. Check **Request Performance dashboard** → Latency (is pipeline congested?)
4. Check quality of incoming content
5. Review any recent agent or model updates

### Symptom: Queue Backing Up

1. Check **Agent Health dashboard** → Queue Depth panel trend
2. Check **Request Performance dashboard** → Throughput (is ingestion overwhelming?)
3. Check **System Health dashboard** → Resource limitation?
4. Scale processing capacity or reduce ingestion rate
5. Check for stuck agents in **Agent Health dashboard** → Status Table

### Symptom: Agents Unhealthy

1. Go to **Agent Health dashboard** → Status Table
2. Identify which agents are unhealthy
3. Check agent logs: `sudo journalctl -u justnews@<agent-name> -n 100`
4. Check connectivity to dependencies (DB, vector store, MCP bus)
5. Restart unhealthy agent: `sudo systemctl restart justnews@<agent-name>`

---

## 📊 Dashboard Access & Sharing

### Accessing Dashboards

1. **Navigate to Grafana:** http://localhost:3000
2. **Go to Dashboards → Browse**
3. **Look for "JustNews" folder** containing all 5 dashboards
4. **Or search by UID:**
   - System Health: `system-health-premium`
   - Request Performance: `request-performance-premium`
   - Pipeline Quality: `pipeline-quality-premium`
   - Agent Status: `agent-status-premium`
   - Operational Overview: `operational-overview-premium`

### Sharing Dashboards

1. **With Team:** Click kebab menu → "Share..." → Choose sharing option
2. **Time Period:** Each dashboard defaults to 24h history (adjustable)
3. **Refresh Rate:** All dashboards refresh every 10 seconds
4. **Export for Reports:** Use Grafana's "Download as PDF" feature

### Setting Alerts

1. Open any panel → Edit → Create Alert Rule
2. Set conditions based on thresholds in this guide
3. Assign notification channels (Slack, PagerDuty, etc.)
4. Test alert before deploying

---

## 📈 Metrics Data Source Configuration

### Prometheus Connection

All dashboards use **Prometheus** as the data source.

**Prometheus URL:** `http://localhost:9090`

To verify connection:

```bash
# Query Prometheus directly
curl http://localhost:9090/api/v1/label/__name__/values | grep justnews

# Should return: justnews_active_connections, justnews_requests_total, etc.
```

### Available Metrics

**JustNews Custom Metrics (7 total):**
- `justnews_active_connections` - Active client connections
- `justnews_agent_health_status` - Agent health (0-4 scale)
- `justnews_processing_queue_size` - Queue depth
- `justnews_request_duration_seconds` - Request latency histogram
- `justnews_requests_total` - Total request counter
- `justnews_stage_b_editorial_acceptance` - Editorial acceptance histogram
- `justnews_stage_b_publishing_latency_seconds` - Publishing latency histogram

**Node Exporter Infrastructure Metrics:**
- `node_cpu_seconds_total` - CPU time
- `node_memory_*` - Memory metrics (MemTotal, MemAvailable, etc.)
- `node_filesystem_*` - Disk metrics (avail_bytes, size_bytes, etc.)
- `node_load1` - Load average
- `node_network_*` - Network metrics (rx_bytes, tx_bytes, etc.)
- `node_disk_*` - Disk I/O metrics

### Metric Troubleshooting

**No data in panels?**
1. Check Prometheus is running: `curl http://localhost:9090/-/healthy`
2. Query available metrics: `curl http://localhost:9090/api/v1/label/__name__/values`
3. Check OTel is exporting to Prometheus: `curl http://localhost:9090/metrics`

**Missing JustNews metrics?**
1. Verify agents are running: `sudo systemctl status justnews@*`
2. Check OTel collectors: `curl http://localhost:4317/healthz` (should be OK)
3. Verify metrics export in agent code: Check `performance_monitoring.py`

---

## 🎓 Best Practices

### For On-Call Engineers

1. **Start with Operational Overview** - Get overall health
2. **If issues detected, drill into specific dashboard** - System Health for resource issues, Agent Health for service issues
3. **Use Request Performance dashboard** - For latency correlations
4. **Document in runbook** - What you found and how you fixed it

### For SREs

1. **Set up alerting** - Use SLOs table in each dashboard guide
2. **Create runbooks** - For each alert condition
3. **Regular review** - Weekly trends and capacity planning
4. **Test alerts** - Fire low-severity alerts to validate notification channels

### For Product Teams

1. **Monitor Operational Overview** - Daily health checks
2. **Track Editorial Acceptance** - Quality metric for content
3. **Watch Publishing Latency** - User experience metric
4. **Review daily throughput trends** - Capacity planning

---

## 📝 Dashboard Maintenance

### Adding New Metrics

1. Update agent code to export new metric
2. Verify metric appears in Prometheus: `curl http://localhost:9090/api/v1/label/__name__/values | grep metric_name`
3. Create query in Grafana
4. Add panel to appropriate dashboard
5. Update this guide with new metric documentation

### Updating Thresholds

If thresholds need adjustment:
1. Edit dashboard → Edit panel → Thresholds tab
2. Update values based on operational needs
3. Update corresponding section in this guide
4. Save dashboard

### Removing Panels

If a metric becomes obsolete:
1. Edit dashboard → Delete panel
2. Save dashboard
3. Update this guide to reflect removal

---

## 🔗 Related Documentation

- [System Architecture Overview](../architecture_overview.md)
- [Prometheus Configuration](./prometheus_config.md)
- [OpenTelemetry Setup](../infrastructure/otel_setup.md)
- [On-Call Runbook](../operations/ON_CALL_RUNBOOK.md)
- [SLO & SLI Definitions](./SLO_DEFINITIONS.md)

---

## 📞 Support & Questions

For dashboard issues:
1. Check this guide first
2. Verify Prometheus is running and healthy
3. Check agent logs for metric export errors
4. Consult [TROUBLESHOOTING.md](../operations/TROUBLESHOOTING.md)

For feedback on this guide:
- Submit issues to: [issues tracker]
- Suggest improvements to: [team slack channel]

---

**Dashboard Suite Status:** ✅ All 5 dashboards operational and verified  
**Last Configuration Update:** February 3, 2026  
**Next Review Date:** February 10, 2026
