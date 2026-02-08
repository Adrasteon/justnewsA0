--- title: Systemd Deployment Overview description: Canonical entry-point for deploying and restarting JustNews with
systemd ---

# Systemd Deployment – Quick Start

## TL;DR: One-command fresh restart (recommended)

```bash

sudo ./infrastructure/systemd/reset_and_start.sh

```bash

What it does:

- Stops/disables all services, frees ports, reloads systemd if needed

- Ensures GPU Orchestrator is READY before any agents start

- Starts MCP Bus, then all agents in order, then runs health check

## Manual sequence (orchestrator-first)

```bash

sudo systemctl enable --now justnews@gpu_orchestrator
curl -fsS <http://127.0.0.1:8014/ready>
sudo ./infrastructure/systemd/scripts/enable_all.sh start
sudo ./infrastructure/systemd/scripts/health_check.sh

```

Notes:

- `enable_all.sh`supports`fresh`and`--fresh`alias and now starts`gpu_orchestrator`first, waiting for`/ready`.

- Adjust gating timeout via drop-in: `Environment=GATE_TIMEOUT=300`.
Content ingestion automation (`justnews-crawl-scheduler.timer`,`justnews@cluster_pipeline.service`,
`justnews@fact_intel.service`) remains disabled by default; enable each only after verifying Stage A health:

```bash

sudo systemctl enable --now justnews-crawl-scheduler.timer
sudo systemctl enable --now justnews@cluster_pipeline
sudo systemctl enable --now justnews@fact_intel

```

Enable `justnews@cluster_pipeline`only after fact intelligence services (e.g.,`justnews@fact_intel`) have run
successfully; the clustering stage consumes Grounded Truth scores emitted by the fact pipeline.

The crawl scheduler service (`justnews-crawl-scheduler.service`) is a oneshot wrapper around
`scripts/ops/run_crawl_schedule.py`. Override paths or crawler URL via`/etc/justnews/crawl_scheduler.env`; include
`CRAWL_PROFILE_PATH` if Crawl4AI profiles live outside the repo checkout. Prometheus textfile metrics default to
`logs/analytics/crawl_scheduler.prom`unless`CRAWL_SCHEDULER_METRICS` is set.

These services rely on the configuration described in `docs/operations/systemd- baseline-then-k8s-phased-plan.md`.

## Related documentation

- Quick Reference: `infrastructure/systemd/QUICK_REFERENCE.md`

- Comprehensive Guide: `infrastructure/systemd/COMPREHENSIVE_SYSTEMD_GUIDE.md`

- PostgreSQL Integration: `infrastructure/systemd/postgresql_integration.md`

## Crawl4AI bridge (managed agent)

The Crawl4AI bridge is managed as a normal JustNews agent via the instance template `justnews@.service` and is available
as `justnews@crawl4ai`.

Deployment notes:

- The agent is started by the standard flows (`reset_and_start.sh`/`enable_all.sh`) and therefore participates in the
  canonical ordering and health checks.

- Configure runtime variables in `/etc/justnews/global.env`or a per-instance env file`/etc/justnews/crawl4ai.env`.
  Important variables:

- CRAWL4AI_HOST (default 127.0.0.1)

- CRAWL4AI_PORT (default 3308)

- CRAWL4AI_BASE_URL (optional override)

- CRAWL4AI_USE_LLM (true/false)

- CRAWL4AI_MODEL_CACHE_DIR (local model cache directory)

If you previously used the standalone unit `infrastructure/systemd/crawl4ai- bridge.service`, switch to
`justnews@crawl4ai`to avoid duplication. The repository includes an agent wrapper at`agents/crawl4ai/main.py` which
launches the FastAPI bridge (`agents.c4ai.server:app`) under the configured Python runtime.

## Migration: Repository rename and systemd service root path

If the repository root on your machine was renamed (for example, from `JustNewsAgent-Clean`to`JustNews`), systemd unit
files and the global environment file may still point to the old path. To avoid UIDs/WORKDIR/ExecStart issues:

- Ensure `/etc/justnews/global.env`either sets`SERVICE_DIR` to the new location or is updated during deployment.

- Check systemd unit files (in `/etc/systemd/system`or`/lib/systemd/system`) that they
  use`$SERVICE_DIR`or`/opt/justnews` rather than hard-coded, outdated paths.

- For a one-off compatibility fix, create a symlink from the old path to the new one (e.g., `sudo ln -s
  /home/adra/JustNews /home/adra/JustNewsAgent-Clean`) to allow services to start while you update units.

- We include a helper script `infrastructure/systemd/scripts/migrate_project_root.sh`to help automate this migration (it
  updates`global.env` and can optionally create a compatibility symlink and reload systemd).
