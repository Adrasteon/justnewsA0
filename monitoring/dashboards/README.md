# JustNews Dashboards - Complete Documentation Index

**Last Updated:** February 4, 2026  
**Status:** ✅ Production Deployment Complete

---

## 📖 Documentation Navigation

### 🚀 Getting Started (Pick One)

**For Quick Start (5 minutes):**  
👉 **[QUICKSTART_GUIDE.md](QUICKSTART_GUIDE.md)**
- How to access dashboards
- Quick overview of each dashboard
- Common Q&A
- Basic troubleshooting
- **Best for:** First-time users, on-call engineers

**For Complete Understanding (30 minutes):**  
👉 **[DASHBOARD_GUIDE_ENTERPRISE.md](DASHBOARD_GUIDE_ENTERPRISE.md)**
- Detailed metric definitions
- SLO/SLI thresholds and alert rules
- Per-dashboard deep dives
- Troubleshooting guide
- Best practices for each role
- **Best for:** Operators, SREs, architects

**For Implementation Status:**  
👉 **[IMPLEMENTATION_COMPLETE.md](IMPLEMENTATION_COMPLETE.md)**
- What was built and why
- Deployment details
- Files created
- Metrics verified
- Next steps and maintenance
- **Best for:** Managers, leads, audits

---

## 📊 Dashboard Quick Reference

### 1️⃣ System Health & Infrastructure
- **UID:** `system-health-premium`
- **Grafana ID:** 9
- **Panels:** 12
- **Use When:** Resource concerns, performance investigation
- **Key Metrics:** CPU, Memory, Disk, Load, Network I/O, Disk I/O
- **Thresholds:** CPU/Mem < 70% (yellow > 75%, red > 90%)
- **Access:** 
  - Direct: http://localhost:3000/d/system-health-premium
  - Search: `system-health-premium`

**In Dashboard Guide:** See "[Dashboard 1: System Health & Infrastructure](#dashboard-1-system-health--infrastructure)" in DASHBOARD_GUIDE_ENTERPRISE.md

---

### 2️⃣ Request Performance & Throughput
- **UID:** `request-performance-premium`
- **Grafana ID:** 10
- **Panels:** 12
- **Use When:** API performance issues, latency concerns
- **Key Metrics:** Req/s, Latency P50/P95/P99, Per-agent performance
- **SLOs:** P99 < 2s, Throughput ≥ 10 req/s, Availability 99.5%
- **Access:**
  - Direct: http://localhost:3000/d/request-performance-premium
  - Search: `request-performance-premium`

**In Dashboard Guide:** See "[Dashboard 2: Request Performance & Throughput](#dashboard-2-request-performance--throughput)" in DASHBOARD_GUIDE_ENTERPRISE.md

---

### 3️⃣ Pipeline Quality & Publishing
- **UID:** `pipeline-quality-premium`
- **Grafana ID:** 11
- **Panels:** 10
- **Use When:** Content quality concerns, publishing delays
- **Key Metrics:** Editorial acceptance, Publishing latency
- **Thresholds:** Acceptance > 80%, Publishing P50 < 1s, P99 < 10s
- **Access:**
  - Direct: http://localhost:3000/d/pipeline-quality-premium
  - Search: `pipeline-quality-premium`

**In Dashboard Guide:** See "[Dashboard 3: Pipeline Quality & Publishing](#dashboard-3-pipeline-quality--publishing)" in DASHBOARD_GUIDE_ENTERPRISE.md

---

### 4️⃣ Agent Health & Status
- **UID:** `agent-status-premium`
- **Grafana ID:** 12
- **Panels:** 9
- **Use When:** Service reliability, agent crashes, fleet changes
- **Key Metrics:** Agent health status, connectivity, queue depth
- **Escalation:** 1 unhealthy = page immediately, 50%+ degraded = incident
- **Access:**
  - Direct: http://localhost:3000/d/agent-status-premium
  - Search: `agent-status-premium`

**In Dashboard Guide:** See "[Dashboard 4: Agent Health & Status](#dashboard-4-agent-health--status)" in DASHBOARD_GUIDE_ENTERPRISE.md

---

### 5️⃣ Operational Overview
- **UID:** `operational-overview-premium`
- **Grafana ID:** 13
- **Panels:** 15
- **Use When:** Executive briefings, 30-second health check
- **Key Metrics:** All (fleet health + resources + requests + quality)
- **Use By:** On-call engineers, executives, incident commanders
- **Access:**
  - Direct: http://localhost:3000/d/operational-overview-premium
  - Search: `operational-overview-premium`

**In Dashboard Guide:** See "[Dashboard 5: Operational Overview](#dashboard-5-operational-overview)" in DASHBOARD_GUIDE_ENTERPRISE.md

---

## 🎯 Finding What You Need

### "My dashboard shows No Data"
1. Read: [Troubleshooting → No Data Section](DASHBOARD_GUIDE_ENTERPRISE.md#troubleshooting)
2. Quick fix: Refresh page + check time range (top right)
3. Deep dive: Check if Prometheus is running (http://localhost:9090)

### "I want to set up alerts"
1. Read: [Alert Thresholds](DASHBOARD_GUIDE_ENTERPRISE.md#slos-slis)
2. Guide: [When to Alert Section](DASHBOARD_GUIDE_ENTERPRISE.md#when-to-alert)
3. Each dashboard has specific alert rules defined

### "I need to explain dashboards to my team"
1. Use: [QUICKSTART_GUIDE.md](QUICKSTART_GUIDE.md) - Dashboard Overview section
2. Each dashboard has 1-minute explanation
3. Share URLs from Quick Reference above

### "I'm on-call and need to respond to an issue"
1. Start: [Operational Overview](http://localhost:3000/d/operational-overview-premium)
2. Identify problem area (red stat)
3. Go to specific dashboard (infrastructure, requests, agents, or quality)
4. Use troubleshooting guide in DASHBOARD_GUIDE_ENTERPRISE.md

### "I need to understand SLOs and alerting"
1. Read: [SLO/SLI Quick Reference](DASHBOARD_GUIDE_ENTERPRISE.md#slogslile-quick-reference)
2. Each dashboard shows thresholds with color coding
3. Alert conditions defined in "When to Alert" sections

### "I want to export dashboard data for reporting"
1. Guide: [Dashboard Access & Sharing](DASHBOARD_GUIDE_ENTERPRISE.md#dashboard-access--sharing)
2. Each dashboard can be exported as PDF or JSON
3. Snapshots capture data at a point in time

---

## 🔧 Operations & Maintenance

### Provisioning Dashboards
**If you need to redeploy dashboards to Grafana:**

```bash
# Python script (recommended)
python3 /home/adra/justnewsA0/infrastructure/monitoring/provision_dashboards.py

# With options
python3 infrastructure/monitoring/provision_dashboards.py \
  --grafana-url http://grafana.example.com \
  --grafana-user admin \
  --grafana-password pass \
  -v
```

**Script automatically:**
- ✅ Verifies Prometheus datasource exists (or creates it)
- ✅ Creates JustNews folder in Grafana
- ✅ Imports all 5 dashboards with correct settings
- ✅ Verifies all imports successful

See: [infrastructure/monitoring/provision_dashboards.py](../provisioning_scripts/dashboards.md)

### Monitoring Metrics Flow
**Verify metrics are being collected:**

```bash
# Check Prometheus
curl http://localhost:9090/api/v1/label/__name__/values | grep justnews

# Check OTel collectors
curl http://localhost:4317/healthz  # Node collector
curl http://localhost:4319/healthz  # Central collector

# Check Grafana datasource
curl -u admin:admin http://localhost:3000/api/datasources
```

### Troubleshooting Checklist
- [ ] Grafana running? `curl http://localhost:3000/api/health`
- [ ] Prometheus running? `curl http://localhost:9090/api/health`
- [ ] OTel collectors running? `curl http://localhost:4317/healthz`
- [ ] Metrics exported by agents? `curl http://localhost:9090/api/v1/label/__name__/values`
- [ ] Dashboard data visible? Check Operational Overview
- [ ] Prometheus scrape config updated? Check `/etc/prometheus/prometheus.yml`

---

## 📋 Role-Specific Guidance

### For On-Call Engineers
📖 **Start with:** [QUICKSTART_GUIDE.md](QUICKSTART_GUIDE.md) — Dashboard Overview section
📍 **Main Dashboard:** [Operational Overview](http://localhost:3000/d/operational-overview-premium)
🎯 **Common Issues:** See [Troubleshooting](DASHBOARD_GUIDE_ENTERPRISE.md#common-troubleshooting-guide) section
⏱️ **Time Needed:** 10 minutes to get proficient

---

### For SREs / DevOps
📖 **Start with:** [DASHBOARD_GUIDE_ENTERPRISE.md](DASHBOARD_GUIDE_ENTERPRISE.md) — Full guide
🎯 **Focus Areas:** 
- SLO/SLI definitions
- Alert conditions
- Escalation procedures
📍 **Tasks:**
1. Set up alerting rules
2. Create runbooks for each alert
3. Test escalation procedures
4. Monitor for metric anomalies
⏱️ **Time Needed:** 1-2 hours for full setup

---

### For Product/Engineering Leads
📖 **Start with:** [IMPLEMENTATION_COMPLETE.md](IMPLEMENTATION_COMPLETE.md) — Executive Summary
📍 **Key Dashboards:**
1. [Operational Overview](http://localhost:3000/d/operational-overview-premium) — Overall health
2. [Request Performance](http://localhost:3000/d/request-performance-premium) — Performance metrics
3. [Pipeline Quality](http://localhost:3000/d/pipeline-quality-premium) — Quality metrics
⏱️ **Time Needed:** 5-10 minutes for daily check

---

### For Executives / Leadership
📖 **Start with:** [IMPLEMENTATION_COMPLETE.md](IMPLEMENTATION_COMPLETE.md#30-second-health-check)
📍 **Executive Dashboard:** [Operational Overview](http://localhost:3000/d/operational-overview-premium)
🎯 **Metrics to Track:**
1. Fleet Health (is system working?)
2. Request Performance (P99 latency)
3. Editorial Quality (acceptance rate)
4. Resource Utilization (do we have capacity?)
⏱️ **Time Needed:** 2-5 minutes for status briefing

---

## 🔗 External References

### JustNews Documentation
- [Architecture Overview](../docs/architecture_overview.md)
- [Operations Guide](../docs/operations)
- [Troubleshooting](../docs/operations/TROUBLESHOOTING.md)
- [Setup Guide](../docs/operations/SETUP_GUIDE.md)

### Grafana Resources
- [Grafana Dashboard Documentation](https://grafana.com/docs/grafana/latest/dashboards/)
- [Prometheus Query Language](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Alert Rules](https://grafana.com/docs/grafana/latest/alerting/alerting-rules/create-grafana-loki-loki-rule/)

### Prometheus/Monitoring
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Node Exporter Metrics](https://github.com/prometheus/node_exporter)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)

---

## ✅ Verification Checklist

**Before considering deployment complete:**

- [ ] All 5 dashboards accessible in Grafana
- [ ] All dashboards in "JustNews" folder
- [ ] No "No data" errors in any panels
- [ ] Operational Overview showing green stats
- [ ] Request Performance showing data flowing
- [ ] System Health showing infrastructure metrics
- [ ] Agent Status showing agent health
- [ ] Pipeline Quality showing quality metrics
- [ ] All dashboards have correct UIDs
- [ ] Provisioning script works (tested)
- [ ] Documentation complete and accurate
- [ ] Team has access to Grafana
- [ ] Quick start guide shared with team
- [ ] Alert thresholds documented
- [ ] On-call runbooks linked to dashboards

---

## 📞 Support & Feedback

### Questions About Specific Dashboards?
See: [DASHBOARD_GUIDE_ENTERPRISE.md](DASHBOARD_GUIDE_ENTERPRISE.md)

### Need Help Getting Started?
See: [QUICKSTART_GUIDE.md](QUICKSTART_GUIDE.md)

### Found an Issue or Have Feedback?
1. Document what you found
2. Link to the dashboard that shows the issue
3. Include time and context
4. Share with: [Your DevOps Team]

---

## 📅 Maintenance Schedule

| Task | Frequency | Owner |
|------|-----------|-------|
| Review dashboard data | Daily | On-call |
| Check alert thresholds | Weekly | SRE |
| Review trends | Weekly | DevOps |
| Capacity planning | Monthly | Leadership |
| Update documentation | As needed | DevOps |
| Test disaster recovery | Quarterly | DevOps |

---

## 🎯 Quick Links (Bookmarks)

Copy these URLs to your bookmarks:

```
System Health:
http://localhost:3000/d/system-health-premium

Request Performance:
http://localhost:3000/d/request-performance-premium

Pipeline Quality:
http://localhost:3000/d/pipeline-quality-premium

Agent Health:
http://localhost:3000/d/agent-status-premium

Operational Overview:
http://localhost:3000/d/operational-overview-premium

Prometheus:
http://localhost:9090
```

---

## 📊 File Structure

```
monitoring/dashboards/
├── generated/
│   ├── system_health_dashboard.json
│   ├── request_performance_dashboard.json
│   ├── pipeline_quality_dashboard.json
│   ├── agent_status_dashboard.json
│   ├── operational_overview_dashboard.json
│   └── (dashboard files)
├── DASHBOARD_GUIDE_ENTERPRISE.md      ← Full guide (1,400+ lines)
├── QUICKSTART_GUIDE.md                 ← Quick start (500+ lines)
├── IMPLEMENTATION_COMPLETE.md          ← Status & details
└── README.md (this file)

infrastructure/monitoring/
├── provision_dashboards.py             ← Provisioning script
└── provision_dashboards.sh             ← Bash alternative
```

---

## 🎉 You're All Set!

**The JustNews Enterprise Dashboard Suite is ready to use.**

**Next Steps:**
1. ✅ Open Grafana: http://localhost:3000
2. ✅ Browse to JustNews folder
3. ✅ Open each dashboard to explore
4. ✅ Read relevant guide for your role
5. ✅ Set up alerts for your responsibilities

**For questions:** Refer to the appropriate guide above or contact your DevOps team.

---

**Version:** 2.0 Production Deployment  
**Last Updated:** February 4, 2026  
**Status:** ✅ Complete and Verified  
**Next Review:** February 11, 2026

---

*Dashboard documentation maintained by JustNews DevOps Team*
