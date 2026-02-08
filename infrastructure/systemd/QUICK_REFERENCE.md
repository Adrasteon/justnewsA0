--- title: Systemd Quick Reference description: 'This enables units (if needed), ensures GPU orchestrator is READY,
starts all services in order, and verifies health.'

tags: ["enables", "ensures", "health"] ---

# Quick Reference – systemd

## One-command cold start (after reboot)

```bash

sudo ./infrastructure/systemd/cold_start.sh

```yaml

This enables units (if needed), ensures GPU orchestrator is READY, starts all services in order, and verifies health.

Optional: Auto-run at boot (~45s):

```bash

sudo cp infrastructure/systemd/scripts/justnews-cold-start.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/justnews-cold-start.sh
sudo cp infrastructure/systemd/units/justnews-cold-start.service /etc/systemd/system/
sudo cp infrastructure/systemd/units/justnews-cold-start.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now justnews-cold-start.timer

```

Optional: Boot-time smoke test (~2 min after boot):

```bash

sudo cp infrastructure/systemd/helpers/boot_smoke_test.sh /usr/local/bin/
sudo cp infrastructure/systemd/scripts/justnews-boot-smoke.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/justnews-boot-smoke.sh /usr/local/bin/boot_smoke_test.sh
sudo cp infrastructure/systemd/units/justnews-boot-smoke.service /etc/systemd/system/
sudo cp infrastructure/systemd/units/justnews-boot-smoke.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now justnews-boot-smoke.timer

```bash

## Monitoring stack (Prometheus, Grafana, node_exporter)

### First-time setup

```bash
sudo ./infrastructure/systemd/scripts/install_monitoring_stack.sh --install-binaries --enable --start

```

### Routine operations

```bash
sudo systemctl status justnews-node-exporter.service
sudo systemctl restart justnews-prometheus.service justnews-grafana.service
sudo journalctl -u justnews-grafana.service -f

```bash

Configuration lives in `/etc/justnews/monitoring.env`and`/etc/justnews/monitoring/`. Grafana is available at
`http://localhost:3000/`(default credentials:`admin / change_me`).

## One-command fresh restart (recommended)

```bash

sudo ./infrastructure/systemd/reset_and_start.sh

```

This performs a clean stop, frees ports, ensures the GPU orchestrator is READY, starts all services in order, and runs a
health check.

## Startup order (orchestrator-first)

1) Start GPU Orchestrator (models gate):

```bash

sudo systemctl enable --now justnews@gpu_orchestrator
curl -fsS <http://127.0.0.1:8014/ready>

```bash

2) Start all services in order:

```bash

sudo ./infrastructure/systemd/scripts/enable_all.sh start

```

3) Check health:

```bash

sudo ./infrastructure/systemd/scripts/health_check.sh

```yaml

Tip: `enable_all.sh`defaults to`status`with no args. Use`start`,`stop`,`restart`, or`fresh` (also accepts
`--fresh`).

## Ports and health endpoints

| Service           | Port | Endpoint | |-------------------|------|----------| | mcp_bus           | 8000 | /health  |
| chief_editor      | 8001 | /health  | | scout             | 8002 | /health  | | fact_checker      | 8003 | /health  |
| analyst           | 8004 | /health  | | synthesizer       | 8005 | /health  | | critic            | 8006 | /health  |
| memory            | 8007 | /health  | | reasoning         | 8008 | /health  | | newsreader        | 8009 | /health  |
| analytics         | 8011 | /health  | | archive           | 8012 | /health  | | dashboard         | 8013 | /health  |
| gpu_orchestrator  | 8014 | /health, /ready, /models/status |

Examples:

```bash

curl -fsS <http://127.0.0.1:8004/health>    # analyst
curl -fsS <http://127.0.0.1:8014/ready>     # orchestrator ready
curl -fsS <http://127.0.0.1:8014/models/status> | jq

```

## Minimal environment files

Global (`/etc/justnews/global.env`):

```bash

JUSTNEWS_PYTHON=/home/adra/miniconda3/envs/${CANONICAL_ENV:-justnews-py312}/bin/python
SERVICE_DIR=/home/adra/JustNews
JUSTNEWS_DB_URL=mysql://user:pass@localhost:3306/justnews
ENABLE_MPS=true
UNIFIED_CRAWLER_ENABLE_HTTP_FETCH=true
ARTICLE_EXTRACTOR_PRIMARY=trafilatura
ARTICLE_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ARTICLE_URL_HASH_ALGO=sha256
ARTICLE_URL_NORMALIZATION=strict
CLUSTER_SIMILARITY_THRESHOLD=0.85
TRANSPARENCY_PORTAL_BASE_URL=http://localhost:8013/transparency
EVIDENCE_AUDIT_BASE_URL=http://localhost:8013/transparency
TRANSPARENCY_DATA_DIR=/var/lib/justnews/transparency-archive
REQUIRE_TRANSPARENCY_AUDIT=1

## Optional: override Prometheus textfile output for the crawl scheduler

## CRAWL_SCHEDULER_METRICS=/var/lib/node_exporter/textfile_collector/crawl_scheduler.prom

```

Per-instance (example `/etc/justnews/analyst.env`):

```

CUDA_VISIBLE_DEVICES=0

```

Use `https://news.example.com/*` style URLs when the transparency portal is exposed publicly; the local defaults above
target the dashboard agent on port 8013 so the synthesizer gate can pass in lab environments.

## NVIDIA MPS Setup (Enterprise GPU Isolation)

Enable NVIDIA Multi-Process Service for GPU resource isolation:

1. **Start MPS Daemon** (run once at system boot):

```bash
sudo nvidia-cuda-mps-control -d

```bash

1. **Verify MPS Status**:

```bash
pgrep -x nvidia-cuda-mps-control
ls -la /tmp/nvidia-mps/

```

1. **Environment Configuration**:

- Set `ENABLE_MPS=true`in`/etc/justnews/global.env`

- Set `ENABLE_MPS=true`and`ENABLE_NVML=true`in`/etc/justnews/gpu_orchestrator.env`

1. **Check MPS Allocation**:

```bash
curl -s <http://127.0.0.1:8014/mps/allocation> | jq '.mps_resource_allocation.system_summary'

```bash

## Common operations

```bash

sudo systemctl status justnews@scout
sudo journalctl -u justnews@scout -e -n 200 -f
sudo ./infrastructure/systemd/scripts/enable_all.sh status
sudo ./infrastructure/systemd/scripts/enable_all.sh restart
sudo systemctl status justnews-crawl-scheduler.service
sudo systemctl status justnews@cluster_pipeline
sudo systemctl status justnews@fact_intel
curl -fsS <http://127.0.0.1:8011/health>
curl -fsS <http://127.0.0.1:8013/transparency/status> | jq '.integrity.status'

```

Sequence tip: ensure fact intelligence services complete before starting clustering jobs so that GTV weights inform
cluster creation.

Transparency tip: keep any transparency portal service (e.g., `justnews@transparency_portal`) and evidence APIs healthy;
locally confirm with `curl -fsS <http://127.0.0.1:8013/transparency/status`.> Synthesizer gate: if`/transparency/status`
fails, `justnews@synthesizer` readiness will remain false until integrity recovers.

## Orderly shutdown (all agents)

```bash

sudo ./infrastructure/systemd/scripts/enable_all.sh stop

```yaml

Notes:

- Stops all JustNews instances in reverse dependency order.

- Does not stop MariaDB (managed separately by your OS/service).

- To also stop the orchestrator explicitly:

```bash

sudo systemctl stop justnews@gpu_orchestrator

```

Troubleshooting:

- If ports remain in use, run: `sudo ./infrastructure/systemd/preflight.sh --stop`.

- Inspect logs: `journalctl -u justnews@<name> -e -n 200`.

## Optional: PATH wrappers (run from any directory)

Install small wrappers to `/usr/local/bin` so these commands work regardless of your current directory:

```bash

sudo cp infrastructure/systemd/scripts/enable_all.sh /usr/local/bin/
sudo cp infrastructure/systemd/scripts/health_check.sh /usr/local/bin/
sudo cp infrastructure/systemd/scripts/reset_and_start.sh /usr/local/bin/
sudo cp infrastructure/systemd/scripts/cold_start.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/enable_all.sh /usr/local/bin/health_check.sh \
  /usr/local/bin/reset_and_start.sh /usr/local/bin/cold_start.sh

```bash

Then you can run:

```bash

sudo enable_all.sh stop
sudo reset_and_start.sh
sudo cold_start.sh
sudo health_check.sh

```

These wrappers resolve `JUSTNEWS_ROOT`or`SERVICE_DIR`from`/etc/justnews/global.env` automatically.

## Status panel (auto-refresh health)

Open a live, auto-refreshing system health panel:

```bash

sudo health_check.sh --panel

```yaml

Options:

- `--refresh SEC` to change interval (default: 2)

- `--host HOST`and`-t/--timeout SEC` respected

- Limit to specific services, e.g.: `sudo health_check.sh --panel mcp_bus analyst`

Notes:

- Tries to launch a new terminal (x-terminal-emulator/gnome-terminal/konsole/xterm).

- Falls back to tmux (new window) if available; otherwise runs inline via `watch`.

- Ensure `watch` (procps) is installed on servers.

## Troubleshooting first-run issues

- Many services “failed/inactive” immediately:

- Ensure orchestrator is running and READY (see startup order above).

- Preflight shows “run as root” and exit 1 under systemd:

- Expected for ExecStartPre limited checks; continue with orchestrator-first.

- Ports already in use:

- `sudo ./infrastructure/systemd/preflight.sh --stop` to free conflicting services.

- DB connectivity (Memory):

- Set `JUSTNEWS_DB_URL`in`global.env`and run`helpers/db-check.sh`.

## Install helpers (optional)

```bash

sudo cp infrastructure/systemd/scripts/wait_for_mcp.sh /usr/local/bin/
sudo cp infrastructure/systemd/scripts/justnews-start-agent.sh /usr/local/bin/
sudo cp -r infrastructure/systemd/helpers/* /usr/local/bin/
sudo chmod +x /usr/local/bin/wait_for_mcp.sh /usr/local/bin/justnews-start-agent.sh /usr/local/bin/*

## Hourly crawl scheduler (Stage B1)

Once Stage A is healthy, enable the Stage B1 ingestion scheduler to execute the curated crawl plan automatically:

1. Install the script wrapper (idempotent):

```bash

sudo cp infrastructure/systemd/scripts/run_crawl_schedule.sh /usr/local/bin/ sudo chmod +x
/usr/local/bin/run_crawl_schedule.sh

```

1. Install the service/timer units:

```bash

sudo cp infrastructure/systemd/units/justnews-crawl-scheduler.* /etc/systemd/system/ sudo systemctl daemon-reload

```bash

1. Provide optional overrides in `/etc/justnews/crawl_scheduler.env` (paths, crawler URL, Prometheus textfile location). Include `CRAWL_PROFILE_PATH` if the crawl profile directory lives outside the repo checkout. The loader accepts a directory path or a single YAML file.

1. Enable the hourly timer:

```bash

sudo systemctl enable --now justnews-crawl-scheduler.timer

```

Status commands:

```bash

sudo systemctl status justnews-crawl-scheduler.timer sudo systemctl status justnews-crawl-scheduler.service journalctl
-u justnews-crawl-scheduler.service -e -n 200 -f

```yaml

Outputs:

- Scheduler state JSON: `${CRAWL_SCHEDULER_STATE:-$SERVICE_DIR/logs/analytics/crawl_scheduler_state.json}`

- Success log (rolling): `${CRAWL_SCHEDULER_SUCCESS:-$SERVICE_DIR/logs/analytics/crawl_scheduler_success.json}`

- Prometheus textfile (node_exporter): `${CRAWL_SCHEDULER_METRICS:-$SERVICE_DIR/logs/analytics/crawl_scheduler.prom}`

- Governance log template: `logs/governance/crawl_terms_audit.md`

Dry-run (no crawler calls):

```bash

sudo conda run -n ${CANONICAL_ENV:-justnews-py312} python scripts/ops/run_crawl_schedule.py --dry-run --profiles
config/crawl_profiles

```

```
