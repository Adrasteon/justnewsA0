# OpenTelemetry Collector Layout

This directory ships the reference configuration for deploying OpenTelemetry Collectors alongside the JustNews GPU
stack. Two roles are supported:

1. **Node collector** – runs on every GPU/agent host, scrapes exporters that run locally (DCGM, node exporter), tails
   kernel/NVIDIA logs, and forwards data upstream.

1. **Central collector** – runs once per environment (or as an HA pair) and fans the aggregated OTLP stream into
   Prometheus, Tempo/Jaeger, and Loki/Elastic.

The configs rely heavily on environment variables so operators can reuse the same file across staging/prod. Every
referenced variable has a documented default in the installer scripts.

## Files

| File | Purpose | | ---- | ------- | | `node-collector-config.yaml` | Collector config for GPU/agent hosts. Currently
limited to OTLP ingestion and log forwarding (metrics pipeline disabled 2025-11 while remote_write tuning is pending). |
| `central-collector-config.yaml` | Collector config for the aggregation tier. Fans node traffic into Tempo/Jaeger and
Loki/Elastic. Metrics forwarding is temporarily disabled (2025-11). |

## Installation scripts

Run the helper scripts (requires sudo):

```bash

## On every GPU/agent node

sudo scripts/ops/install_otel_node_collector.sh

## On monitoring/ops nodes hosting the aggregation tier

sudo scripts/ops/install_otel_central_collector.sh

```

Both scripts download the requested `otelcol-contrib`release, install it under`/usr/local/bin`, copy the configs +
systemd units, and create override env files under `/etc/justnews/monitoring/otel/`. Rerun the script after updating
this directory to redeploy changes.

## Customization knobs

Environment overrides live in:

- `/etc/justnews/monitoring/otel/node.env`

- `/etc/justnews/monitoring/otel/central.env`

The most useful variables include:

- `OTEL_SERVICE_NAME` – logical name that ends up on every span/log.

- `OTEL_UPSTREAM_ENDPOINT`– where node collectors forward OTLP data (defaults to`127.0.0.1:4317`).

- `TEMPO_ENDPOINT`/`JAEGER_ENDPOINT` – optional OTLP HTTP endpoints for traces.

- `LOKI_ENDPOINT` – log aggregation endpoint.

> **Note:** Prometheus remote_write knobs remain in the historical env files but are unused until we re-enable the OTEL
metrics pipelines.

Consult the inline comments inside each config for additional options (scrape intervals, log include paths, etc.).

## Dry-run testing

Before enabling the services, validate the config:

```bash
sudo /usr/local/bin/otelcol-contrib \
  --config /etc/justnews/monitoring/otel/node-collector-config.yaml \
  --dry-run

```bash

The same flag works for the central collector. The systemd units also expose `systemctl status`and`journalctl -u
justnews-otel-*.service` logs if anything fails during startup.
