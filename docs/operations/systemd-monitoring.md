# Systemd Monitoring Stack

This guide explains how to install and operate the JustNews monitoring stack (Prometheus, Grafana, and node_exporter)
when running the platform with native systemd services.

## Components

| Component       | Purpose                                               | Service name                     |
|-----------------|-------------------------- ------------------------------|----------------------------------| |
node_exporter   | Exposes host metrics and textfile collectors           | `justnews-node-exporter.service` | |
Prometheus      | Scrapes agent endpoints and textfile collectors        | `justnews-prometheus.service`    | | Grafana
| Renders dashboards and surfaces alerts (if enabled)    | `justnews- grafana.service`       | | GPU Exporter    |
Custom NVIDIA GPU metrics exporter | Manual (Python script)           |

Dashboards are provisioned automatically from `monitoring/dashboards/generated/` and appear in Grafana after
installation.

## Prerequisites

- `justnews` system user (created during systemd setup)

- Internet access to download official release archives

- `curl`and`tar` installed on the host

## First-time installation

Run the installer script as root:

```bash
sudo ./infrastructure/systemd/scripts/install_monitoring_stack.sh \
  --install-binaries \
  --enable \
  --start

```bash

This performs the following actions:

1. Downloads Prometheus, Grafana, and node_exporter into `/opt/justnews/monitoring`

1. Creates `/etc/justnews/monitoring.env` (with sensible defaults)

1. Copies Prometheus/Grafana configs and dashboards to `/etc/justnews/monitoring/`

1. Installs systemd units under `/etc/systemd/system/`

1. Enables and starts `justnews-node-exporter`,`justnews-prometheus`, and`justnews-grafana`

> **Note:** If binaries already exist, omit `--install-binaries`. Use`--force` to overwrite config files with
timestamped backups.

## Configuration

All runtime settings live in `/etc/justnews/monitoring.env`. Key entries include:

```ini
PROMETHEUS_BIN=/opt/justnews/monitoring/prometheus/prometheus
PROMETHEUS_CONFIG_FILE=/etc/justnews/monitoring/prometheus.yml
PROMETHEUS_DATA_DIR=/var/lib/justnews/prometheus
GF_SERVER_HTTP_PORT=3000
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=change_me
NODE_EXPORTER_TEXTFILE_DIR=/var/lib/node_exporter/textfile_collector

```

After editing the file, reload services:

```bash
sudo systemctl restart justnews-node-exporter.service
sudo systemctl restart justnews-prometheus.service
sudo systemctl restart justnews-grafana.service

```bash

## GPU Monitoring Setup

The monitoring stack includes comprehensive NVIDIA GPU monitoring capabilities.

### Automatic GPU Metrics Collection

1. **GPU Exporter**: A custom Python-based exporter (`gpu_metrics_exporter.py`) automatically collects GPU metrics
   using`nvidia-smi`

1. **Prometheus Integration**: GPU metrics are automatically scraped every 15 seconds

1. **Dashboard Integration**: GPU panels are included in the JustNews Operations Dashboard

### GPU Metrics Available

The system monitors 10 comprehensive GPU metrics:

| Metric | Description | |--------|-------------| | `nvidia_gpu_count` | Number of GPUs detected | |
`nvidia_gpu_utilization_ratio`| GPU utilization (0-1 ratio) | |`nvidia_gpu_memory_utilization_ratio` | Memory
utilization (0-1 ratio) | | `nvidia_gpu_temperature_celsius` | GPU temperature in Celsius | |
`nvidia_gpu_power_draw_watts`| Current power consumption | |`nvidia_gpu_power_limit_watts` | Power limit setting | |
`nvidia_gpu_fan_speed_ratio`| Fan speed (0-1 ratio) | |`nvidia_gpu_memory_total_bytes` | Total GPU memory | |
`nvidia_gpu_memory_used_bytes`| Used GPU memory | |`nvidia_gpu_memory_free_bytes` | Free GPU memory |

### GPU Exporter Management

The GPU exporter runs as a background Python process. To manage it:

```bash

## Check if GPU exporter is running

ps aux | grep gpu_metrics_exporter

## Start GPU exporter manually (if needed)

```bash
cd ${SERVICE_DIR:-$HOME/JustNews}
python3 gpu_metrics_exporter.py &
```

## The exporter runs on port 9400 by default

curl <http://localhost:9400/health>
curl <http://localhost:9400/metrics>

```

## Dashboards

Dashboards are placed under `/etc/justnews/monitoring/grafana/dashboards/` and are automatically picked up by Grafana.
The generated bundle currently includes:

- **JustNews Operations Dashboard** – Comprehensive monitoring with 19 panels covering:

- **Content Processing**: Domains crawled, articles accepted, adaptive articles, scheduler lag

- **Application Health**: Active connections, total errors, request duration, crawler requests (time series)

- **System Resources**: CPU usage, memory usage, disk usage, network I/O

- **GPU Monitoring**: GPU utilization, memory usage, temperature, power draw, memory details, utilization trends

To add custom dashboards, drop JSON exports into the same directory and restart Grafana.

## Verification

1. Confirm services are active:

```bash systemctl status justnews-node-exporter.service justnews-
prometheus.service justnews-grafana.service ```

1. Check Prometheus targets at `http://localhost:9090/targets` - should show:

   - `nvidia-gpu-exporter` (port 9400) - GPU metrics

   - `justnews-node-exporter` (port 9100) - System metrics

   - Various JustNews agent endpoints

1. Log into Grafana at `http://localhost:3000/` (change the default password immediately)

1. Access the JustNews Operations Dashboard at:
`http://localhost:3000/d/ef37elu2756o0e/justnews-operations-dashboard`

1. Verify GPU metrics are displaying:

   - GPU Utilization gauge should show current usage

   - GPU Temperature should display current temperature

   - GPU Memory panels should show memory information

1. Validate crawl scheduler metrics appear under the dashboard's content processing panels

## Maintenance

- **Upgrade binaries:** re-run the installer with `--install-binaries --force` to download newer versions. Adjust `--prometheus-version`, `--grafana-version`, or `--node-exporter-version` if needed.

- **Rotate data:** adjust `PROMETHEUS_RETENTION` in `monitoring.env` to control TSDB retention (default: 30 days).

- **Backups:** include `/var/lib/justnews/prometheus` and `/var/lib/justnews/grafana` in your backup plan.

- **Textfile metrics:** scheduler metrics are exported to `/var/lib/node_exporter/textfile_collector/crawl_scheduler.prom`. Additional custom exporters can drop Prometheus-formatted files into this directory.

## Troubleshooting

| Symptom                                      | Resolution |
|---------------------------------------------|------------| | Services fail
with exit code 127            | Binaries missing/not executable. Re-run
installer with `--install-binaries` or update paths in `monitoring.env` | |
Grafana shows provisioning errors           | Ensure files under
`/etc/justnews/monitoring/grafana/provisioning` are readable by the `justnews`
user | | Prometheus target down for an agent         | Check the agent's
`/metrics` endpoint and confirm it is running (`systemctl status
justnews@<agent>`) | | node_exporter permission denied on textfile | Verify
`/var/lib/node_exporter/textfile_collector` owner is `justnews:justnews` and
mode `0775` | | GPU metrics not appearing                   | Check GPU exporter
is running: `ps aux \| grep gpu_metrics_exporter`. Restart with `cd ${SERVICE_DIR:-$HOME/JustNews}
&& python3 gpu_metrics_exporter.py &` | | GPU exporter shows "unknown" health
| Wait 15-30 seconds for initial scrape, then check
`http://localhost:9090/targets` | | GPU temperature shows [Not Supported]
| Some GPU models don't report temperature via nvidia-smi. Check with `nvidia-
smi --query-gpu=temperature.gpu --format=csv` | | Dashboard shows "No data" for
GPU panels    | Verify Prometheus can reach GPU exporter: `curl
<http://localhost:9400/metrics`> |

For full context, see `infrastructure/systemd/README.md` and
`infrastructure/systemd/QUICK_REFERENCE.md`.
