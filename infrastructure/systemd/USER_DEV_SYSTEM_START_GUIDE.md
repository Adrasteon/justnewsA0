# JustNews — User / Dev System Start Guide

A concise, one-page checklist to start and verify a JustNews system on a host (developer or operator).

> Quick reference: For full troubleshooting and detailed context see
`infrastructure/systemd/COMPREHENSIVE_SYSTEMD_GUIDE.md`and`SYSTEM_STARTUP_CHECKLIST.md`.

---

## TL;DR (one command) ✅

- Run the canonical safe startup (recommended):

```bash
sudo ./infrastructure/systemd/canonical_system_startup.sh

```bash

This runs environment checks, optional DB probes, a reset+fresh start (GPU orchestrator → MCP Bus → agents), provisions
monitoring if needed, and performs a consolidated health check.

---

## Prerequisites (quick)

- Ensure `/etc/justnews/global.env` exists and contains:

- `SERVICE_DIR`,`PYTHON_BIN`or`CANONICAL_ENV`(default:`justnews-py312`)

- `MARIADB_HOST/PORT/USER/PASSWORD`(or set`SKIP_MARIADB_CHECK=true`)

- `CHROMA_HOST/PORT` if using ChromaDB

- Tools: `systemctl`,`curl`,`ss`,`python3`(see`preflight.sh` for full checks)

---

## Quick Start (operator-friendly)

1. Validate without changing system (dry-run):

```bash
sudo ./infrastructure/systemd/canonical_system_startup.sh --dry-run

```

1. Real startup (recommended):

```bash
sudo ./infrastructure/systemd/canonical_system_startup.sh

```bash

1. Optional manual orchestrator-first flow (when you need fine-grained control):

```bash
sudo systemctl enable --now justnews@gpu_orchestrator
curl -fsS <http://127.0.0.1:8014/ready>
sudo ./infrastructure/systemd/scripts/enable_all.sh start
sudo ./infrastructure/systemd/scripts/health_check.sh -v

```

---

## Verify the system is healthy

- Run the consolidated health script:

```bash
sudo ./infrastructure/systemd/scripts/health_check.sh -v

```

- Confirm key endpoints:

- GPU Orchestrator READY: `curl -fsS <http://127.0.0.1:8014/ready`>

- MCP Bus health: `curl -fsS <http://127.0.0.1:8000/health`>

- Agent health endpoints (example): `curl -fsS <http://127.0.0.1:8015/health`> (crawler)

- Check Prometheus / Grafana dashboards for `justnews_agent_health_status` (if monitoring provisioned)

---

## Monitoring & Alertmanager

- Monitoring installer is invoked automatically during canonical startup when needed.

- Alertmanager installation is opt-in: set `AUTO_INSTALL_ALERTMANAGER=1`in`/etc/justnews/global.env` ONLY on admin
  hosts.

---

## Troubleshooting quick actions

- If ports are occupied: `sudo ./infrastructure/systemd/preflight.sh --stop`or`sudo
  ./infrastructure/systemd/reset_and_start.sh` (it kills known ports).

- View service logs: `sudo journalctl -u justnews@<agent> -f`

- Orchestrator logs: `sudo journalctl -u justnews@gpu_orchestrator -f`

- Collect diagnostics bundle: `sudo infrastructure/systemd/collect_startup_diagnostics.sh`

- If many services failed on first boot, ensure `gpu_orchestrator`reported`/ready`then re-run:`sudo
  ./infrastructure/systemd/reset_and_start.sh`

---

## Safety notes

- To avoid GPU-driven OOMs on developer hosts, set `SAFE_MODE=true`in`/etc/justnews/global.env` (disables CUDA and
  applies conservative settings).

- `AUTO_BOOTSTRAP_CONDA=1` by default will attempt to bootstrap the canonical project environment if missing — it will prefer `mamba` if available (install into base with `conda install -n base -c conda-forge mamba -y`); set to `0` to opt out.

- Use `MARIADB_CHECK_REQUIRED=true` in production to enforce DB connectivity on startup.

---

## Where to read more

- Full guide: `infrastructure/systemd/COMPREHENSIVE_SYSTEMD_GUIDE.md`

- Deployment notes: `infrastructure/systemd/DEPLOYMENT.md`

- Checklist: `SYSTEM_STARTUP_CHECKLIST.md`

---

Last updated: 2025-12-28
