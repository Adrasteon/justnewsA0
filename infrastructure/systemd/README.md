---
title: "JustNews Systemd Deployment - Operator Index"
description: "Practical entry point for native systemd operations, service management, and orchestration"
tags: ["infrastructure", "systemd", "operations", "deployment", "reference"]
status: "current"
version: "2.0"
last_updated: "2026-02-02"
audience: ["operators", "devops", "sysadmins"]
---

# JustNews native deployment (systemd) – operator index

This directory contains the native (no Docker/K8s) deployment scaffold for running the MCP bus and all agents as systemd
instanced units.

## Quick operator flow (5 minutes)

1) Start GPU Orchestrator first (satisfies ExecStartPre model gating):

- `sudo systemctl enable --now justnews@gpu_orchestrator`

- Wait for READY: `curl -fsS <http://127.0.0.1:8014/ready`> → HTTP 200

2) Start the MCP Bus next (this will gate other agents and—if enabled via `AUTO_INSTALL_ALERTMANAGER=1` in
`/etc/justnews/global.env`—attempt to install and enable the host-level Alertmanager systemd unit idempotently):

- `sudo systemctl enable --now justnews@mcp_bus`

3) Start the rest in order:

- `sudo ./infrastructure/systemd/scripts/enable_all.sh start`

4) Check health:

- `sudo ./infrastructure/systemd/scripts/health_check.sh`

Note: The Alertmanager installer invoked by the startup flow is idempotent and will back up existing unit files to
`/var/backups/justnews/alertmanager/` before replacing them; enable the opt-in behaviour only on controlled admin hosts.
Troubleshooting? See the Quick Reference and Comprehensive guide below.

If the synthesizer service remains degraded, confirm the dashboard-hosted transparency endpoint is reachable: `curl -fsS
<http://127.0.0.1:8013/transparency/status> | jq '.integrity.status'`. Analytics health should report
`{"status":"healthy"}`via`curl -fsS <http://127.0.0.1:8011/health`.>

## Documents

- Quick Reference (copy-paste commands, port map, troubleshooting)

- `./QUICK_REFERENCE.md`

- Comprehensive systemd guide (gating internals, drop-ins, tuning)

- `./COMPREHENSIVE_SYSTEMD_GUIDE.md`

- MariaDB integration guide (DB URL and checks)

- `./mariadb_integration.md`

Incident reference:

- Systemd Orchestrator Incident Report — Sept 13, 2025

- `../../markdown_docs/development_reports/systemd_operational_incident_report_2025-09-13.md`

## Scripts

- `enable_all.sh` – enable/disable/start/stop/restart/fresh for all services

- `health_check.sh` – table view of systemd/port/HTTP/READY status

- `preflight.sh`– validation and ExecStartPre gating (with`--gate-only`)

- `canonical_system_startup.sh`– verifies env + data mount + database, then runs a full reset/start with health summary
  (use`sudo ./infrastructure/systemd/canonical_system_startup.sh stop` for a coordinated shutdown)

- `install_monitoring_stack.sh` – installs Prometheus, Grafana, and node_exporter (plus dashboards) and wires up their
  systemd units

- `install_alertmanager_unit.sh`– idempotent installer that installs an example Alertmanager systemd unit, backs up
  existing units to`/var/backups/justnews/alertmanager/`, and optionally enables/starts the service (use`--enable`).
  This is used by the MCP Bus startup sequence when`AUTO_INSTALL_ALERTMANAGER=1`.

- `wait_for_mcp.sh` – helper used by unit template to gate on the MCP bus

- `justnews-start-agent.sh` – unit ExecStart wrapper

Helpers (optional, recommended):

- `helpers/orchestrator-ready.sh` – poll /ready on 8014 with backoff

- `helpers/tail-logs.sh`– follow multiple`journalctl` streams with labels

- `helpers/diag-dump.sh` – capture statuses, logs, ports into a bundle

- `helpers/db-check.sh` – quick DB reachability check

- `run_crawl_schedule.sh`– Stage B1 hourly crawl scheduler entry point (copy to`/usr/local/bin/` and ensure executable)

### Crawl scheduler service (Stage B1)

- Unit: `units/justnews-crawl-scheduler.service`(oneshot wrapper around`run_crawl_schedule.sh`)

- Timer: `units/justnews-crawl-scheduler.timer` (hourly with a 5-minute jitter window)

- Enable sequence:
  1. `sudo cp infrastructure/systemd/scripts/run_crawl_schedule.sh /usr/local/bin/run_crawl_schedule.sh`
  1. `sudo chmod +x /usr/local/bin/run_crawl_schedule.sh`
  1. `sudo cp infrastructure/systemd/units/justnews-crawl-scheduler.* /etc/systemd/system/`
  1. `sudo systemctl daemon-reload`
  1. `sudo systemctl enable --now justnews-crawl-scheduler.timer`

- Optional overrides: `/etc/justnews/crawl_scheduler.env`

- `CRAWLER_AGENT_URL=http://127.0.0.1:8015`

- `CRAWL_SCHEDULE_PATH=/etc/justnews/crawl_schedule.yaml` (if relocating config)

- `CRAWL_PROFILE_PATH=/etc/justnews/crawl_profiles.yaml` (optional path to the Crawl4AI profile registry)

- `CRAWL_SCHEDULER_METRICS=/var/lib/node_exporter/textfile_collector/crawl_scheduler.prom`

- `CRAWL_SCHEDULER_STATE=/var/log/justnews/crawl_scheduler_state.json`

- `CRAWL_SCHEDULER_SUCCESS=/var/log/justnews/crawl_scheduler_success.json`

## Unit template and drop-ins

- Template: `units/justnews@.service`→ create instances like`justnews@scout`

- Drop-in templates: `units/drop-ins/`(copy into`/etc/systemd/system/justnews@<name>.service.d/`)

- `05-gate-timeout.conf` – tune model gate timeout

- `10-preflight-gating.conf`– run preflight in`--gate-only` mode

- `20-restart-policy.conf` – restart policy knobs

## Minimal environment files (examples)

Global: `/etc/justnews/global.env`

```bash

## absolute python for agents

JUSTNEWS_PYTHON=/home/adra/miniconda3/envs/${CANONICAL_ENV:-justnews-py312}/bin/python

Helpers & validation
--------------------
This repository includes two helper scripts to ensure and validate that the system
has a canonical runtime configured in `/etc/justnews/global.env`:

- `infrastructure/systemd/scripts/ensure_global_python_bin.sh` — idempotent helper which will create or add `PYTHON_BIN` to `/etc/justnews/global.env` (invoked by canonical startup flow). Requires root to write `/etc/justnews/global.env`.

- `infrastructure/scripts/validate-global-env.sh` — CI-friendly validation helper that checks for `PYTHON_BIN` in `/etc/justnews/global.env` and, as a fallback, checks the repository example `infrastructure/systemd/examples/justnews.env.example`.

Use `make check-global-env` in the repository to run the validation script (CI-friendly). The canonical startup flow runs the ensure helper so hosts booted with the repository's deployment scripts will have `PYTHON_BIN` set when possible.

## optional: default working directory

SERVICE_DIR=/home/adra/JustNews

## database URL for Memory agent (adjust as needed)

JUSTNEWS_DB_URL=mysql://user:pass@localhost:3306/justnews

```yaml

Per-instance: `/etc/justnews/analyst.env`

```

CUDA_VISIBLE_DEVICES=0

## override exec if needed

## EXEC_START="$JUSTNEWS_PYTHON -m agents.analyst.main"

```bash

See Quick Reference for the full port map and more examples.

## Monitoring stack (Prometheus + Grafana + node_exporter + Alertmanager)

We now include an integrated monitoring and alerting stack with example configurations and provisioning for Prometheus,
Grafana, and Alertmanager. Key additions:

- Prometheus alert rules for MCP Bus health: `monitoring/alerts/mcp_bus_alerts.yml` (MCPBusOverallDegraded,
  MCPBusAgentUnreachable, MCPBusAgentDegraded).

- Grafana system overview dashboard includes MCP Bus panels (overall health stat, degraded agent count, agent status
  table) and is provisioned from `monitoring/dashboards/generated/system_overview_dashboard.json`.

- Alertmanager example config and templates:
  `monitoring/alertmanager/alertmanager.example.yml`and`monitoring/alertmanager/mcp_bus_templates.tmpl`.

- An idempotent Alertmanager installer script and Makefile helpers are available for operators to provision Alertmanager
  safely.

The monitoring assets live under `infrastructure/systemd/monitoring`. Install and manage them with:

```bash
sudo ./infrastructure/systemd/scripts/install_monitoring_stack.sh --install-binaries --enable --start

```

This command downloads the official Prometheus, Grafana, and node_exporter builds into `/opt/justnews/monitoring`, lays
down `/etc/justnews/monitoring.env`, publishes dashboards, and enables the following services:

- `justnews-node-exporter.service`

- `justnews-prometheus.service`

- `justnews-grafana.service`

Key paths:

- Prometheus config: `/etc/justnews/monitoring/prometheus.yml`

- Grafana config: `/etc/justnews/monitoring/grafana.ini`

- Dashboards: `/etc/justnews/monitoring/grafana/dashboards`

- Textfile collector: `/var/lib/node_exporter/textfile_collector`

Routine operations:

```bash
sudo systemctl status justnews-node-exporter.service
sudo systemctl restart justnews-prometheus.service justnews-grafana.service
sudo journalctl -u justnews-grafana.service -e -n 200

```bash

Dev telemetry (optional) -------------------------

For developer hosts you can opt-in to automatically start the local dev telemetry stack (Loki + Tempo + an OpenTelemetry
node collector using the repository's `infrastructure/monitoring/dev-docker-compose.yaml`) during the canonical startup
flow by setting this in `/etc/justnews/global.env`:

```

ENABLE_DEV_TELEMETRY=true

```bash

When enabled, `canonical_system_startup.sh` will launch the repository dev telemetry docker-compose when starting the
system and will tear it down during the coordinated shutdown path (`canonical_system_startup.sh stop`). This is strictly
opt-in so operator systems are unaffected unless explicitly chosen.

Important — dev telemetry default host ports -----------------------------------------

The dev telemetry stack uses canonical container ports but, to avoid colliding with a system-level OpenTelemetry
collector on developer machines, the compose file maps container ports to an alternate set of default host ports by
default. These host port defaults reduce the chance of a bind failure when a host collector is already running.

Default dev host port mapping (host -> container):

- ${LOKI_PORT:-13100} -> 3100 (Loki)

- ${TEMPO_HTTP_PORT:-24268} -> 14268 (Tempo HTTP)

- ${TEMPO_JAEGER_PORT:-19411} -> 9411 (Tempo/Jaeger)

- ${OTEL_GRPC_PORT:-24317} -> 4317 (OTLP gRPC)

- ${OTEL_HTTP_PORT:-24318} -> 4318 (OTLP HTTP)

- ${NODE_METRICS_PORT:-18889} -> 8889 (node collector metrics)

- ${DEMO_PORT:-18080} -> 8080 (demo emitter)

```bash

## Force-start dev telemetry even if canonical ports are already in use

ENABLE_DEV_TELEMETRY_FORCE=1 ENABLE_DEV_TELEMETRY=true \
  /path/to/infrastructure/systemd/scripts/dev-telemetry-manager.sh up

```

If you need to use canonical host ports instead (e.g. to mirror production networking exactly) you can override
individual host ports by exporting the appropriate environment variable when starting the stack. Example:

```bash

## Launch dev telemetry but map Loki to canonical 3100 and OTLP gRPC to 4317

LOKI_PORT=3100 OTEL_GRPC_PORT=4317 ENABLE_DEV_TELEMETRY=true \
  /path/to/infrastructure/systemd/scripts/dev-telemetry-manager.sh up

```bash

To avoid surprises canonical_system_startup.sh will still detect port conflicts on the configured host ports and will
skip starting the stack unless you set `ENABLE_DEV_TELEMETRY_FORCE=1`.

If you'd prefer the dev telemetry stack to be managed directly by systemd, you can install the provided unit file and
enable it using the helper script:

```bash
sudo ./infrastructure/systemd/scripts/install_dev_telemetry_unit.sh
sudo systemctl enable --now justnews-dev-telemetry.service

```bash

This will let operators control the dev telemetry stack with `systemctl start|stop`.

Operator playbook, automation & checks -------------------------------------

We included a detailed operator playbook at `infrastructure/systemd/operators/dev-telemetry-playbook.md`, an example
Ansible playbook at `infrastructure/ansible/playbooks/enable_dev_telemetry.yml`, and a host check script at
`scripts/ops/check_dev_telemetry_status.sh` to help run a consistent enable/verify workflow across many hosts.

Grafana defaults to `http://localhost:3000/`with`admin / change_me`. Update credentials via the UI after first login.

## Optional preflight checks (DB / Vector store / SQLite)

This section documents the existing helpers and how to perform simple operator checks for MariaDB/Postgres, Chroma
(vector database), and local SQLite use by the HITL and crawler paywall aggregator components.

### MariaDB/Postgres (Memory DB)

- Helper: `infrastructure/systemd/helpers/db-check.sh`— reads`/etc/justnews/global.env`and tries a minimal`SELECT
  1;`using`mysql`or`psql`.

- Example usage: `sudo ./infrastructure/systemd/helpers/db-check.sh`or if installed:`sudo /usr/local/bin/db-check.sh`.

- If this fails, confirm `JUSTNEWS_DB_URL`(or`DATABASE_URL`) in`/etc/justnews/global.env`or use the native client:`mysql
  --user=... --host=... -p -e 'SELECT 1;'`or`psql "$DATABASE_URL" -c 'SELECT 1;'`.

#### MariaDB startup probe (new)

The `canonical_system_startup.sh` script includes an optional MariaDB probe which can be enabled for operator safety.
The probe is designed to be lightweight and environment-driven. Relevant environment variables in
`/etc/justnews/global.env`:

- `MARIADB_HOST`/`MARIADB_PORT`/`MARIADB_USER`/`MARIADB_PASSWORD`/`MARIADB_DB` — used by the probe.

- `SKIP_MARIADB_CHECK=true` — skip the probe entirely (handy for dev machines).

- `MARIADB_CHECK_REQUIRED=true` — require a successful probe and abort startup on failure (recommended for production).

The probe prefers the `mysql` client when installed. If the client is missing it will attempt a small Python check using
the `PYTHON_BIN`runtime and`pymysql` (if available). If neither is available the probe will be skipped unless
`MARIADB_CHECK_REQUIRED` is set.

Recommendation: Install `mysql-client`on host deployments, or ensure the`PYTHON_BIN` referenced by
`/etc/justnews/global.env`has`pymysql` installed to get deterministic health checks during startup.

### Chroma (vector store)

- Config vars: `CHROMADB_HOST`,`CHROMADB_PORT`in`/etc/justnews/global.env`(defaults to`localhost:3307`).

- Quick probe (Python):

```bash CHROMA_HOST=${CHROMADB_HOST:-localhost}
CHROMA_PORT=${CHROMADB_PORT:-3307} python3 - <<'PY' from chromadb import
HttpClient import os host = os.getenv('CHROMADB_HOST', 'localhost') port =
int(os.getenv('CHROMADB_PORT', '3307')) client = HttpClient(host=host,
port=port) print('Collections:', client.list_collections()) PY ```

### Local SQLite checks (HITL and Paywall aggregator)

- Env vars: `HITL_DB_PATH`, `CRAWL4AI_PAYWALL_AGG_DB`.

- Quick probe (Python):

```bash python3 - <<'PY' import os, sqlite3 path = os.getenv('HITL_DB_PATH',
'agents/hitl_service/hitl_staging.db') os.makedirs(os.path.dirname(path), exist_ok=True) conn = sqlite3.connect(path)
conn.execute('PRAGMA user_version;') conn.close() print('OK', path) PY
```

### How to gate startup on these checks

You may prefer not to gate production startup on DB/Chroma/SQLite checks for developer convenience. If you want to add
gating:

1) Manual option: Run the checks before `canonical_system_startup.sh`:

```bash
sudo ./infrastructure/systemd/helpers/db-check.sh
CHROMADB_HOST=... CHROMADB_PORT=... python3 ./infrastructure/systemd/helpers/chroma_probe.py
HITL_DB_PATH=/var/lib/justnews/hitl.db python3 ./infrastructure/systemd/helpers/sqlite_check.py
sudo ./infrastructure/systemd/canonical_system_startup.sh

```

2) Automated option (recommended for production): Add `ExecStartPre` entries to the drop-in files. For example, add to
`/etc/systemd/system/justnews@<instance>.service.d/10-preflight-gating.conf`:

```json

[Service]
ExecStartPre=/usr/local/bin/db-check.sh
ExecStartPre=/usr/local/bin/chroma-probe.sh
ExecStartPre=/usr/local/bin/sqlite-writable-check.sh

```

3) Opt-in gating environment variable (safe for rolling upgrades): Set `ENABLE_DB_GATING=1` in
`/etc/justnews/global.env`and consider adding`if [ "$ENABLE_DB_GATING" = "1" ]; then /usr/local/bin/db-check.sh; fi`
into the `canonical_system_startup.sh`drop-in generation logic, or into`justnews- preflight-check.sh`.

Note: Gating failures cause `systemd` to mark the unit as failed. Use gating only when your architecture requires
immediate database readiness before the agent can start.

---

If you'd like, we can add small `chroma-probe.sh`and`sqlite-writable-check.sh` helpers to the
`infrastructure/systemd/helpers/`directory for easier integration with`ExecStartPre` in a follow-up change.
