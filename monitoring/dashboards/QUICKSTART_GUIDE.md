# JustNews Dashboards - Quick Start Guide

**Updated:** February 4, 2026  
**Status:** ✅ All 5 Dashboards Live & Verified

---

## 🚀 Get Started in 5 Minutes

### Step 1: Open Grafana
```
http://localhost:3000
Username: admin
Password: admin
```

### Step 2: Access JustNews Dashboards

**Option A - Browse Folder:**
1. Click **Dashboards** → **Browse**
2. Find folder named **"JustNews"**
3. Open any of the 5 dashboards

**Option B - Direct Search:**
1. Press **Ctrl+K** (Mac: **Cmd+K**)
2. Type dashboard name or UID:
   - `system-health-premium` - Infrastructure metrics
   - `request-performance-premium` - API performance
   - `pipeline-quality-premium` - Editorial quality
   - `agent-status-premium` - Agent health
   - `operational-overview-premium` - Executive summary

**Option C - Direct URL:**
```
# System Health
http://localhost:3000/d/system-health-premium

# Request Performance
http://localhost:3000/d/request-performance-premium

# Pipeline Quality
http://localhost:3000/d/pipeline-quality-premium

# Agent Status
http://localhost:3000/d/agent-status-premium

# Operational Overview
http://localhost:3000/d/operational-overview-premium
```

### Step 3: Check Your First Dashboard

Visit the **Operational Overview** for a complete health snapshot:
- ✅ Fleet Health Status
- ✅ Resource Utilization (CPU/Memory/Disk)
- ✅ Request Throughput & Latency
- ✅ Quality Metrics
- ✅ Trend Charts

---

## 📊 Dashboard Overview (1 Minute Each)

### Dashboard 1: System Health & Infrastructure
**When to use:** Resource usage concerns, performance investigation

**Key Quick-Checks:**
- Is CPU under 70%? ✅ Green | ⚠️ Orange | 🔴 Red
- Is Memory under 70%? ✅ Green | ⚠️ Orange | 🔴 Red  
- Is Disk > 10% free? ✅ Green | ⚠️ Orange | 🔴 Red
- Load avg reasonable? Check "Load Average" panel

**If RED:**
- →CPU high: Check "CPU Utilization Trend" for spikes
- →Memory high: Check for memory leaks or OTel issues
- →Disk full: Immediate action needed, cleanup or provision storage

---

### Dashboard 2: Request Performance & Throughput
**When to use:** API performance issues, slowness complaints, SLA violations

**Key Quick-Checks:**
- Latency P99 under 2s? ✅ Green | ⚠️ > 5s | 🔴 > 10s
- Throughput stable? Look for drops or unusual spikes
- Per-agent latency similar? Major outliers need investigation

**Healthy Patterns:**
- Throughput: Steady line (10-100 req/s typical)
- Latency: Stable or gradually improving
- Per-agent: Similar performance across agents

**If Degraded:**
- →High latency: Check System Health dashboard (resource constrained?)
- →Low throughput: Check Agent Status (agents unhealthy?)
- →Outlier agent: SSH into that agent and check logs

---

### Dashboard 3: Pipeline Quality & Publishing
**When to use:** Content quality concerns, editorial reviews, publishing delays

**Key Quick-Checks:**
- Acceptance rate > 80%? ✅ Healthy | ⚠️ 60-80% | 🔴 < 60%
- Publishing latency P50 < 1s? ✅ Good | ⚠️ 1-5s | 🔴 > 5s
- Acceptance trending up/down? Look for concerning patterns

**Expected Patterns:**
- Acceptance: Should be consistently high and stable
- Publishing: P50 <1s, P95 <3s, P99 <10s

**If Degraded:**
- →Low acceptance: Review editorial policies, content quality
- →High latency: Check database, vector store health
- →Sudden change: Check recent deployments or config changes

---

### Dashboard 4: Agent Health & Status
**When to use:** Service reliability, agent crashes, fleet status

**Key Quick-Checks:**
- Any red status values? 🔴 Immediate attention needed
- How many agents are healthy? Should be near 100%
- Queue depth < 1,000? ✅ Good | ⚠️ 1-5k | 🔴 > 5k

**Status Values:**
- 0 = ✅ Healthy (green)
- 1 = ⚠️ Degraded (orange)
- 2 = 🔴 Unhealthy (red)
- 3 = 🔴 Unreachable (red)

**If Issues:**
- →1 unhealthy agent: Page on-call immediately
- →Growing queue: System can't keep up, scale or investigate
- →Degrading trend: Pattern of failures, investigate root cause

---

### Dashboard 5: Operational Overview
**When to use:** Check overall system health at a glance (on-call, standup, exec briefing)

**The 6 Key Numbers:**
1. **Fleet Health** - Is everything working? (0=✅ Healthy)
2. **CPU/Memory/Disk** - Are resources available?
3. **Throughput** - How many requests/sec?
4. **Latency P99** - Is it under 2 seconds?
5. **Acceptance Rate** - Is content quality good (>80%)?
6. **Queue Depth** - Is work backing up?

**30-Second Health Check:**
- All stats green? ✅ System healthy
- Any red? 🔴 Investigate which dashboard
- Orange? ⚠️ Monitor trends, may need attention

---

## 🎯 Common Questions & Answers

### "Why is everything red?"
check in this order:
1. **System Health** - Are resources maxed out?
2. **Agent Status** - Are services running?
3. **Request Performance** - Is throughput zero?
4. **Grafana Data Source** - Can Grafana reach Prometheus?

Test connection:
```bash
curl http://localhost:9090/api/v1/label/__name__/values | grep justnews
```

### "How do I know if SLAs are being met?"
Check **Operational Overview**:
- Latency P99 should be < 2,000ms
- Throughput should be consistent
- Acceptance rate should be > 80%

### "What do the colors mean?"
- ✅ **Green:** All is well, no action needed
- ⚠️ **Orange/Yellow:** Warning - monitor this, action may be needed soon
- 🔴 **Red:** Alarm - something is broken or degraded, action needed now

### "How often do dashboards update?"
- **Refresh:** Every 10 seconds
- **Data Points:** New data point every 15 seconds from Prometheus
- **Latency:** 5-10 second delay between event and dashboard visibility

### "Can I change the time window?"
**Yes!** Top right corner of any dashboard:
- Last **5 minutes** - Real-time troubleshooting
- Last **1 hour** - Recent patterns
- Last **24 hours** - Daily trends (default)
- Custom range - Specific incident investigation

### "How do I export dashboard data?"
1. Click kebab menu (three dots) → **Export**
2. Choose format: **PDF**, **JSON**, or **CSV** (varies by dashboard)
3. Use for: Reports, incident documentation, trend analysis

### "Can I share dashboards with my team?"
**Yes!**
1. Click kebab menu → **Share**
2. Options: **Snapshot**, **Direct link**, **Embed link**
3. Snapshots capture data at a point in time (good for reports)
4. Direct links sync with live data

---

## ⚠️ Common Issues & Troubleshooting

### Issue: Dashboard shows "No Data in Response"

**Quick Fix:**
1. Check time range (top right) - is it set to Last 24h?
2. Refresh page (Ctrl+R or Cmd+R)
3. Check if agents are running:
   ```bash
   sudo systemctl status justnews@*
   ```

**Deep Dive:**
1. Open System Health dashboard
2. If all panels show data → Prometheus is working
3. If System Health is empty → Prometheus not responding
   ```bash
   curl http://localhost:9090/api/health
   ```

### Issue: High latency spike (sudden, unusual)

**Steps to diagnose:**
1. Open **Request Performance** dashboard
2. Click on latency spike
3. Note the time
4. Check **System Health** dashboard for same time
   - CPU spike? Database slower?
   - Memory spike? GC pause?
   - Disk spike? I/O contention?

### Issue: Agents keep going unhealthy

**Steps to diagnose:**
1. Open **Agent Status** dashboard
2. Note which agents are unhealthy
3. Check agent logs:
   ```bash
   sudo journalctl -u justnews@AGENT_NAME -n 100 -f
   ```
4. Check connectivity:
   ```bash
   # Test MCP Bus
   curl http://localhost:8000/health
   # Test database
   curl http://127.0.0.1:3306  # Should timeout or give error
   ```

### Issue: Grafana not accessible

```bash
# Check if running
sudo systemctl status grafana-server

# Check port
sudo lsof -i :3000

# Restart if needed
sudo systemctl restart grafana-server
```

---

## 📚 Next Steps for Your Role

### If You're On-Call:
1. **Bookmark "Operational Overview"** dashboard
2. **Monitor these 3 dashboards this week:**
   - System Health (resource issues)
   - Request Performance (latency issues)
   - Agent Status (service reliability)
3. **Create a runbook** for each alert condition

### If You're SRE/DevOps:
1. **Read full guide:** `monitoring/dashboards/DASHBOARD_GUIDE_ENTERPRISE.md`
2. **Set up alerting rules** using thresholds in the guide
3. **Create escalation policies** for each alert
4. **Test your alerts** before production

### If You're Product:
1. **Monitor Editorial Acceptance** daily
2. **Track Publishing Latency** if responsible for performance
3. **Review Request Patterns** to understand user load

### If You're an Executive:
1. **Use Operational Overview** for health briefings
2. **Request PDF exports** for reporting
3. **Review trends weekly** for capacity planning

---

## 🔗 Important Links

| Resource | Link |
|----------|------|
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| Full Guide | `monitoring/dashboards/DASHBOARD_GUIDE_ENTERPRISE.md` |
| Troubleshooting | `docs/operations/TROUBLESHOOTING.md` |
| Runbooks | (Link to your runbook wiki) |
| On-Call | (Link to your on-call schedule) |

---

## ✅ Quick Setup Checklist

- [ ] Can access Grafana at http://localhost:3000
- [ ] Can see "JustNews" folder in Dashboards
- [ ] Can open System Health dashboard (see 12 panels)
- [ ] Can see data in panels (not "No data")
- [ ] Request Performance shows request count growing
- [ ] Agent Status shows healthy agents
- [ ] Operational Overview shows all green stats
- [ ] Bookmarked Operational Overview dashboard
- [ ] Shared dashboards with your team
- [ ] Set up alerts for your role

---

## 🎓 Learning Path

**Day 1:** 
- Open each of the 5 dashboards
- Spend 5 minutes on each
- Get familiar with what's displayed

**Day 2:**
- Check Operational Overview during your shift
- Notice normal patterns (throughput, latency ranges)
- Identify baseline metrics

**Day 3:**
- Read the full dashboard guide
- Learn alert thresholds for your role
- Create your own alert rules (try non-critical alert first)

**Ongoing:**
- Weekly dashboard review
- Monthly trend analysis
- Quarterly capacity planning

---

## 💡 Pro Tips

1. **Use Dark Mode** for long-term monitoring (less eye strain)
2. **Set up Slack integration** for alerts (see Grafana settings)
3. **Create team-specific dashboards** (duplicate and customize)
4. **Use annotations** for deployments and incidents
5. **Export dashboards as backup** JSON format
6. **Test your whole stack** with the graphs (what correlates with what?)
7. **Create incident postmortems** linking to dashboard data
8. **Share learnings** when dashboards help you find root cause

---

## 📞 Need Help?

**For dashboard-specific questions:**
- See section "Common Questions & Answers" above
- Check [Full Dashboard Guide](DASHBOARD_GUIDE_ENTERPRISE.md)

**For metric/data questions:**
- Check Prometheus: http://localhost:9090
- See [Troubleshooting] docs

**For on-call/escalation:**
- See on-call runbook
- Contact: [Your DevOps Team]

---

**Dashboard Suite Status:** ✅ Production Ready  
**Last Updated:** February 4, 2026  
**Questions?** Ask your DevOps team  

🚀 **Happy Monitoring!**
