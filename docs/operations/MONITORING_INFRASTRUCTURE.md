--- title: Monitoring Infrastructure Analysis description: Analysis of Grafana/Prometheus configuration files and
recommendations date: 2024-12-15 ---

# Monitoring Infrastructure Analysis

## Summary

The USB drive contains a **complete Grafana and Prometheus monitoring stack** with 5 pre-configured dashboards and
integration with JustNews services. This monitoring infrastructure is **highly relevant and should be integrated** into
the production systemd setup.

## What's on the USB Drive

### Location

`/media/adra/37f1914d-e5fd-48ca-8c24-22d5f4e2e9dd/etc/justnews/monitoring/`

### Configuration Files

#### 1. **grafana.ini** (537 bytes)

Grafana server configuration with:

- HTTP server on `0.0.0.0:3000` (all interfaces)

- Data storage: `/var/lib/justnews/grafana`

- Provisioning from: `/etc/justnews/monitoring/grafana/provisioning/`

- Default credentials: `admin:admin` (⚠️ **CHANGE THESE IN PRODUCTION**)

- Security: Anonymous access disabled, gravatar disabled

#### 2. **prometheus.yml** (1.1 KB)

Prometheus server configuration with:

- Scrape interval: 15 seconds

- Global labels: `deployment=systemd`

- Targets configured for:

- **Prometheus itself** (9090)

- **MCP Bus** (8000)

- **Crawler** (8015, 10s scrape)

- **Dashboard** (8013)

- **Agents** (8001-8008, 8012) — 9 agent ports

- **Node Exporter** (9100) — System metrics

#### 3. **Grafana Dashboards** (5 total, 1,312 lines JSON)

| Dashboard | Purpose | Lines | |-----------|---------|-------| | `system_overview_dashboard.json` | Infrastructure
health (CPU, memory, network, GPU) | 461 | | `justnews_operations_dashboard.json` | Service health and operational
metrics | 489 | | `business_metrics_dashboard.json` | Content processing, crawl rates, ingestion | 253 | |
`ingest_archive_dashboard.json`| Article ingestion pipeline | 49 | |`parity_dashboard.json` | Extraction parity and
quality metrics | 60 |

**System Overview Dashboard includes**:

- Fleet availability (number of justnews services up)

- GPU utilization and memory

- Network throughput

- Service dependencies

- Error rate tracking

#### 4. **Datasource Configuration**

Grafana datasource provisioning configured to auto-connect to:

- Prometheus at `http://127.0.0.1:9090`

- Auto-refresh every 15 seconds

- Marked as default datasource

## What We Have in the Repo

The repository already contains a comprehensive **monitoring module** at `${SERVICE_DIR:-$HOME/JustNews}/monitoring/`:

### Monitoring Module Contents

```

monitoring/
├── README.md                    # Observability platform design doc
├── core/                        # Logging system (COMPLETED)
│   ├── log_collector.py        # Unified logging interface
│   ├── log_aggregator.py       # Centralized collection
│   ├── log_storage.py          # Searchable storage
│   └── log_analyzer.py         # Anomaly detection
├── refactor/
│   └── core/                   # Distributed tracing (COMPLETED Oct 2025)
│       ├── trace_collector.py  # OpenTelemetry integration
│       ├── trace_processor.py  # Bottleneck detection
│       ├── trace_storage.py    # Persistent trace storage
│       └── trace_analyzer.py   # Health scoring
├── dashboards/                 # Dashboard definitions
├── alerts/                     # Alert rule definitions
└── ops/                        # Operational tools

```

### Status Summary

- ✅ **Centralized Logging**: COMPLETED (full structured logging, aggregation, storage, analysis)

- ✅ **Distributed Tracing**: COMPLETED (Oct 22, 2025) with OpenTelemetry integration

- ⚠️ **Metrics & Dashboards**: Design exists, but **Grafana/Prometheus not deployed to systemd yet**

- ⚠️ **Alerting**: Rules exist; **AlertManager** is recommended for routing and notification (see
  `monitoring/alertmanager/alertmanager.example.yml`).

Installation quickstart (idempotent):

  1. Install Alertmanager and any required dependencies (the repo provides an installer and Makefile helpers):

  - Run `make alertmanager-install` to apt-install (or download a release) and copy example configs.

  - Use `make alertmanager-install-unit`to install the example systemd unit to`/etc/systemd/system/alertmanager.service`
    (idempotent copy).

  - Or run the idempotent installer script directly: `sudo ./scripts/install_alertmanager_unit.sh --enable` which will
    back up an existing unit file and enable/start the service.

  1. Configure receivers in `/etc/alertmanager/alertmanager.yml`and place templates
     in`/etc/alertmanager/templates/`(example in`monitoring/alertmanager/alertmanager.example.yml`).

  1. Reload systemd and start Alertmanager: `sudo systemctl daemon-reload && sudo systemctl enable --now
     alertmanager.service`(the installer can do this with`--enable`).

  1. Validate: `make alertmanager-status` shows service status and API health.

  1. Validate alert routing: send a test alert with `make alertmanager-test`.

Notes:

- The installer script is idempotent and will back up existing unit files into `/var/backups/justnews/alertmanager/`
  before replacing.

- Update the example config with your Slack/webhook/email credentials before enabling in production.

AUTO_INSTALL_ALERTMANAGER environment toggle -------------------------------------------

- You can opt-in to the Alertmanager systemd unit installation as part of the standard agent startup by setting the
  environment variable `AUTO_INSTALL_ALERTMANAGER=1`in`/etc/justnews/global.env`.

- This runs only when the `mcp_bus`agent starts (to avoid multiple hosts attempting to manage a single host-level unit)
  and executes the idempotent`scripts/install_alertmanager_unit.sh --enable` script.

- Default behavior is disabled (`AUTO_INSTALL_ALERTMANAGER=0`). Use in controlled admin environments only.

## Recommendations

### Phase 1: Integrate Existing Grafana/Prometheus Configuration ✅ **DO THIS**

**What to do**:

1. Copy configuration files from USB to `/etc/justnews/monitoring/`:

```bash sudo mkdir -p /etc/justnews/monitoring/grafana/provisioning sudo cp -r
/media/adra/.../etc/justnews/monitoring/* /etc/justnews/monitoring/ ```

1. Create systemd units for Prometheus and Grafana:

```bash sudo systemctl enable --now prometheus sudo systemctl enable --now
grafana-server
```

1. Update password security in `/etc/justnews/monitoring/grafana.ini`:

```ini [security] admin_user = admin admin_password = <strong-random-password>

```bash

1. Update Prometheus to point to actual service ports (verify ports match your deployment)

**Why**:

- Pre-built dashboards save development time

- Immediate visibility into system health

- Integration already configured for your service architecture

- Low effort, high value

**Time to deploy**: ~30 minutes

### Phase 2: Deploy Prometheus & Grafana as Systemd Services ✅ **RECOMMENDED**

**What to do**:

1. Install Prometheus:

```bash sudo apt-get install -y prometheus grafana-server prometheus-node-
exporter
```

1. Create systemd units:

   - `/etc/systemd/system/prometheus.service` (use config from USB)

   - `/etc/systemd/system/grafana.service` (use config from USB)

1. Update configuration paths to match system locations

1. Enable and start services:

```
bash sudo systemctl enable --now prometheus grafana-server
```

**Benefits**:

- Auto-start on boot (matching your Vault/MariaDB/ChromaDB pattern)

- Service restart on failure

- Standard systemd logging integration

- Easy to manage alongside other JustNews services

**Time to deploy**: ~45 minutes

### Phase 3: Deploy Node Exporter for System Metrics

**What to do**:

1. Install Node Exporter:

```
bash sudo apt-get install -y prometheus-node-exporter
```

1. Configure to listen on `127.0.0.1:9100`

1. Enable and start:

```
bash sudo systemctl enable --now prometheus-node-exporter
```

**Benefits**:

- Track CPU, memory, disk, network metrics

- Required for system_overview_dashboard

- Low overhead

**Time to deploy**: ~15 minutes

### Phase 4: Integrate Application Metrics

**What to do**:

1. Uncomment `prometheus-client>=0.19.0`in`requirements.txt`

1. Implement metrics collection in agents using `common/metrics.py`

1. Ensure agents expose Prometheus endpoints on configured ports (8001-8008, 8015)

**Current State**:

- Code is partially ready (`common/metrics.py` exists but may need updates)

- Agent ports are already defined

- Just needs activation

**Time to deploy**: ~1-2 hours (depends on agent implementation)

## Files Needed from USB

### Essential (Copy These First)

```

/etc/justnews/monitoring/
├── grafana.ini                                          [537 bytes]
├── prometheus.yml                                       [1.1 KB]
└── grafana/
    ├── provisioning/
    │   ├── datasources/prometheus.yaml                 [data source config]
    │   └── dashboards/justnews.yaml                    [dashboard provisioning]
    └── dashboards/
        ├── system_overview_dashboard.json              [461 lines]
        ├── justnews_operations_dashboard.json          [489 lines]
        ├── business_metrics_dashboard.json             [253 lines]
        ├── ingest_archive_dashboard.json               [49 lines]
        └── parity_dashboard.json                       [60 lines]

```

### Optional (For Future Expansion)

```

Backup files (.bak.* files) - can skip these

```bash

## Integration Path Forward

### Immediate (Next 1-2 Days)

1. ✅ Document monitoring infrastructure (THIS FILE)

1. ⬜ Copy USB monitoring configs to `/etc/justnews/monitoring/`

1. ⬜ Create systemd units for Prometheus and Grafana

1. ⬜ Update configuration with actual service ports

1. ⬜ Deploy and test dashboard access

### Short Term (Next Week)

1. ⬜ Deploy Node Exporter for system metrics

1. ⬜ Activate `prometheus-client` in requirements

1. ⬜ Update agent code to emit Prometheus metrics

1. ⬜ Test dashboard data population

### Medium Term (Next Month)

1. ⬜ Deploy AlertManager with alert rules

1. ⬜ Configure alert notifications (email, Slack, etc.)

1. ⬜ Train team on dashboard usage and alerting

1. ⬜ Document runbook for common alerts

## Security Considerations

### Changes Needed

1. **Change Grafana admin password** from default `admin:admin`

```
bash sudo grafana-cli admin reset-admin-password <new-password>
```

1. **Enable authentication** for Prometheus API (optional but recommended)

   - Add reverse proxy (nginx) in front of Prometheus

   - Require API token authentication

1. **Secure metric collection** endpoints

   - Run Prometheus on localhost only: `127.0.0.1:9090`

   - Use firewall rules to restrict access

1. **Protect Grafana credentials**

   - Store in Vault alongside other secrets

   - Use strong password (16+ chars, mixed case, symbols, numbers)

### Already Handled

- ✅ Anonymous Grafana access disabled

- ✅ Gravatar disabled (privacy)

- ✅ Console logging only (no file logs with secrets)

- ✅ `reporting_enabled=false` (no telemetry)

- ✅ `check_for_updates=false` (no external calls)

## Documentation to Create

### Create These New Docs

1. **docs/operations/MONITORING_SETUP.md** — How to deploy Prometheus/Grafana

1. **docs/operations/DASHBOARDS.md** — Guide to using the 5 dashboards

1. **docs/operations/ALERTING.md** — Setting up and managing alerts

### Update Existing Docs

1. **README.md** — Add link to monitoring in quick start

1. **docs/operations/README.md** — Add monitoring to quick links

1. **docs/operations/TROUBLESHOOTING.md** — Add monitoring section

## Quick Start (If You Decide to Deploy Now)

```bash

## 1. Copy monitoring configs from USB

sudo mkdir -p /etc/justnews/monitoring/grafana/provisioning/{datasources,dashboards} sudo cp
/media/adra/.../monitoring/* /etc/justnews/monitoring/

## 2. Install Prometheus and Grafana

sudo apt-get update sudo apt-get install -y prometheus grafana-server prometheus-node-exporter

## 3. Update config symlinks (optional)

sudo ln -sf /etc/justnews/monitoring/prometheus.yml /etc/prometheus/prometheus.yml sudo ln -sf
/etc/justnews/monitoring/grafana.ini /etc/grafana/grafana.ini

## 4. Start services

sudo systemctl daemon-reload sudo systemctl enable --now prometheus grafana-server prometheus-node-exporter

## 5. Access dashboards

## Open browser to: <http://localhost:3000/>

## Default credentials: admin / admin (CHANGE IMMEDIATELY)

## 6. Verify Prometheus targets

## Open browser to: <http://localhost:9090/targets>

```

## Verdict

| Aspect | Decision | Rationale | |--------|----------|-----------| |
**Needed?** | ✅ YES | Production system requires monitoring | | **Use USB
configs?** | ✅ YES | Pre-built, tested, matches architecture | | **Deploy now?**
| ⚠️ OPTIONAL | Can wait 1-2 weeks if system works fine | | **Deploy
eventually?** | ✅ YES | Essential for production reliability | | **Priority** |
MEDIUM-HIGH | After core services (Vault, MariaDB, ChromaDB) stable |

## Next Steps

1. **Decision**: Decide if you want monitoring deployed now or in 1-2 weeks

1. **If YES**: Follow "Quick Start" section above

1. **If LATER**: Save this document and USB path for reference

1. **Either way**: Create documentation for monitoring setup (for team consistency)

---

**USB Drive Location**:
`/media/adra/37f1914d-e5fd-48ca-8c24-22d5f4e2e9dd/etc/justnews/monitoring/`

**Documentation**: See `docs/operations/systemd-monitoring.md` (existing) and
`docs/DOCUMENTATION_INDEX.md` (updated)

**Recommendation**: Integrate Prometheus/Grafana **within next 1-2 weeks** for
production observability.
