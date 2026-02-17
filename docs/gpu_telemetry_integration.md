Orchestrator integration ------------------------ The `gpu_orchestrator`/GPU manager can optionally trigger host-level
telemetry automatically when an allocation is created and stop it when allocations are released. Enable this behavior on
orchestrator hosts with the environment variable:

```bash

export GPU_TELEMETRY_AUTOSTART=true

```

When enabled the GPU allocation path will attempt to start system telemetry (via systemd service or fallback to the
local agent script) and stop it when no active allocations remain. This is recommended on dedicated GPU worker nodes so
telemetry is always captured during model runtimes.

# GPU Telemetry & Activity Monitoring — integration guide

This document explains how telemetry and the GPU activity monitor integrate with the JustNews GPU orchestration stack.

Goals

- Automatically collect GPU and host telemetry whenever the GPU is under load

- Keep telemetry off during idle periods to reduce noise and IO overhead

- Provide a Prometheus-friendly exporter for dashboards and alerting

Components

- scripts/perf/gpu_telemetry.sh — CSV per-second telemetry collector (nvidia-smi + hwmon)

- scripts/perf/gpu_telemetry_exporter.py — Prometheus exporter exposing the same metrics

- scripts/perf/gpu_activity_agent.py — Agent that automatically starts/stops telemetry + exporter based on GPU activity

How it works

1. The GPU activity agent polls nvidia-smi every second (configurable). When it observes sustained GPU utilization above
   a configured threshold the agent starts the CSV collector and the Prometheus exporter.

1. When GPU utilization drops and remains below a configured threshold for a configurable period, the agent stops both
   services.

Deployment modes

- Separate lightweight agent per host (recommended) — run `gpu_activity_agent.py` as a systemd unit or container on gpu
  hosts.

- Orchestrator-integrated (advanced) — the `gpu_orchestrator` can call (or listen to) the agent's start/stop events to
  co-ordinate telemetry capture with job allocation.

Recommended systemd service (example)

```json

[Unit]
Description=JustNews GPU activity monitor
After=network.target

[Service]
Type=simple
User=justnews
ExecStart=/usr/bin/python3 /home/adra/JustNews/scripts/perf/gpu_activity_agent.py --start-util 20 --start-seconds 5 --stop-util 10 --stop-seconds 15
Restart=on-failure

[Install]
WantedBy=multi-user.target

```

Notes & Security

- RAPL energy files (CPU package power) are often root-readable only. There are two safe options:

- run the telemetry under a service account with appropriate group-read access to `/sys/class/powercap/...` (preferred)
  or

- run telemetry under sudo (less recommended).

- Telemetry files are written to `/var/log/justnews-perf` by default; ensure retention/rotation is configured by ops
  (logrotate) if tests are long-running.

Next steps

- Integrate the agent into your GPU node provisioning (systemd, container) and add a Prometheus scrape job for the
  exporter port. Optionally, add alerts (high GPU temp, sudden drop in CPU/RAPL readings) to the monitoring stack.

Installation notes ------------------ We've included helper scripts to install the service and logrotate policy into the
host system. On a target GPU host run (requires sudo):

```bash

## Install logrotate and the systemd unit + defaults (installs /etc/logrotate.d/justnews-perf and /etc/default/justnews-gpu-telemetry)

sudo scripts/perf/install_all.sh

## Or do the steps individually if you want finer control

sudo scripts/perf/install_logrotate.sh
sudo scripts/perf/install_service.sh

```bash

The installer writes a runtime configuration file at `/etc/default/justnews-gpu- telemetry` with values the service
reads at startup. Edit this file to change the service user, working directory, log directory, exporter port, and the
start/stop thresholds.

Example entries you can tune in `/etc/default/justnews-gpu-telemetry`:

```

JN_USER=justnews
JN_GROUP=syslog
JN_WORKDIR=/home/justnews/JustNews
JN_LOGDIR=/var/log/justnews-perf
JN_EXPORTER_PORT=9118
JN_START_UTIL=20
JN_START_SECONDS=5
JN_STOP_UTIL=10
JN_STOP_SECONDS=15

```bash

After editing `/etc/default/justnews-gpu-telemetry` restart the service to apply changes:

```bash
sudo systemctl restart justnews-gpu-telemetry.service

```

OpenTelemetry collectors ------------------------ To tie GPU telemetry, kernel logs, and distributed traces together use
the OpenTelemetry collector assets added in `infrastructure/monitoring/otel/`.

### Node collectors (per GPU host)

1. Install the collector:

```
bash sudo scripts/ops/install_otel_node_collector.sh
```

1. Override any defaults in `/etc/justnews/monitoring/otel/node.env` (OTLP upstream endpoint, DCGM scrape target, etc.).

1. Validate the config: `sudo /usr/local/bin/otelcol-contrib --config /etc/justnews/monitoring/otel/node-collector-
   config.yaml --dry-run`.

1. Ensure `justnews-otel-node.service`is active before starting GPU workloads (`systemctl status justnews-otel-
   node.service`).

The node config tails `/var/log/kern.log` plus NVIDIA driver logs, ingests OTLP
spans/logs from agents, and forwards everything upstream over OTLP. DCGM/node
exporter scraping + Prometheus remote_write fan-out are paused (2025-11) until
we finish reworking the metrics story.

### Central collectors (fan-out tier)

1. Install on the monitoring/observability host:

```
bash sudo scripts/ops/install_otel_central_collector.sh
```

1. Populate `/etc/justnews/monitoring/otel/central.env` with the Tempo/Loki endpoints for your environment. Prometheus
   remote_write inputs are currently ignored while metrics are disabled.

1. Start and enable `justnews-otel-central.service`.

The central collector receives OTLP from the nodes and fans traces to Tempo/Jaeger plus logs to Loki/Elastic. Metrics
forwarding is temporarily disabled.

### Application instrumentation

- Services can opt-in to automatic tracing + OTLP export by calling
  `common.observability.bootstrap_observability("service-name")`during startup. The helper wires local logging and
  OpenTelemetry exporters (respecting the`OTEL_EXPORTER_*` env vars documented above).

- Our Python tracing helpers (`agents/common/tracing.py`) now forward spans to OpenTelemetry whenever the SDK is
  installed and initialized, so existing`@traced` decorators produce both legacy in-process summaries and OTLP spans.

### Prometheus integration

- For now, keep Prometheus scraping exporters directly. The OTEL remote_write fan-out is disabled while we address
  duplicate-series issues.

- Collector self-metrics remain exposed on `127.0.0.1:8889`/`8890`, but we no longer scrape them by default. Feel free
  to add ad-hoc scrapes if you need health signals during testing.

### Validation checklist

- `systemctl status justnews-otel-node.service`shows`active (running)` on every GPU host.

- (Optional) `curl -s <http://127.0.0.1:8889/metrics> | head` returns collector metrics if you are manually checking collector health.

- Tempo/Jaeger receives spans with `service.name`equal to your override in`/etc/justnews/monitoring/otel/*.env`.

- Loki/Elastic contains kernel/Xid lines with `justnews.gpu.host_role=node` labels.
