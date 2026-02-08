--- title: Monitoring Quick Deploy Guide description: Step-by-step guide to deploy Prometheus and Grafana using the
automated script ---

# Monitoring Quick Deploy Guide

## Overview

The `scripts/deploy_monitoring.sh` script automates the complete deployment of the Prometheus and Grafana monitoring
stack from your USB drive. It handles:

- ✅ Package installation (Prometheus, Grafana, Node Exporter)

- ✅ Copying configurations from USB drive

- ✅ Creating directory structure and setting permissions

- ✅ Creating systemd units for all services

- ✅ Enabling services for auto-start

- ✅ Starting services and waiting for readiness

- ✅ Verifying deployment

- ✅ Configuring Grafana security

- ✅ Displaying access information

**Time to Deploy**: 5-10 minutes (fully automated)

## Prerequisites

### Required

- **Root/sudo access**: Script must run as root

- **USB drive mounted**: At `/media/adra/37f1914d-e5fd-48ca-8c24-22d5f4e2e9dd`

- Contains monitoring configs at `etc/justnews/monitoring/`

- **Internet connection**: To download and install packages

- **Ubuntu/Debian Linux**: Script uses apt-get package manager

### Optional

- **GRAFANA_PASSWORD environment variable**: Set a strong password before running

- If not set, a random password will be generated

## Quick Start (One Command)

```bash

## Deploy with automatic password generation

sudo bash scripts/deploy_monitoring.sh

## Or specify a custom Grafana password

GRAFANA_PASSWORD="your-strong-password" sudo bash scripts/deploy_monitoring.sh

```bash

**That's it!** The script will complete deployment in 5-10 minutes.

## What Happens During Deployment

### Step 1: Package Installation

```

Installing:
  • prometheus - Time series database for metrics
  • grafana-server - Dashboard and visualization platform
  • prometheus-node-exporter - System metrics collector

```

### Step 2: Configuration Files Copied

```

From USB:    /media/adra/.../etc/justnews/monitoring/
To System:   /etc/justnews/monitoring/

Copied:
  • prometheus.yml - Service targets and scrape config
  • grafana.ini - Grafana server configuration
  • grafana/provisioning/ - Datasource and dashboard configs
  • grafana/dashboards/ - 5 pre-built dashboards

```

### Step 3: Directories and Permissions

```

Created:
  /var/lib/prometheus/ - Prometheus data storage
  /var/lib/justnews/grafana/ - Grafana data storage
  /var/log/justnews/grafana/ - Grafana logs
  /var/lib/node_exporter/textfile_collector/ - Custom metrics

```

### Step 4: Systemd Units

```

Created:
  /etc/systemd/system/prometheus.service
  /etc/systemd/system/grafana-server.service
  /etc/systemd/system/prometheus-node-exporter.service

```

### Step 5: Services Enabled

```

All services configured to auto-start on boot:
  • systemctl enable prometheus
  • systemctl enable grafana-server
  • systemctl enable prometheus-node-exporter

```bash

### Step 6: Services Started

```

Starting:
  • Prometheus (internal, :9090)
  • Grafana (http, :3000)
  • Node Exporter (internal, :9100)

```bash

### Step 7-10: Verification

```

Verifying:
  • Services are running
  • Configuration files present
  • Prometheus targets are being scraped
  • Grafana password configured

```bash

## Advanced Options

### Skip Package Installation

If you already have packages installed:

```bash
sudo bash scripts/deploy_monitoring.sh --skip-install

```

### Skip Service Startup

To install but not start services (for manual testing first):

```bash
sudo bash scripts/deploy_monitoring.sh --skip-start

```bash

### Combine Options

```bash
GRAFANA_PASSWORD="strong-password" sudo bash scripts/deploy_monitoring.sh --skip-install --skip-start

```

### Show Help

```bash
bash scripts/deploy_monitoring.sh --help

```bash

## Environment Variables

### GRAFANA_PASSWORD

Set custom Grafana admin password before running:

```bash
export GRAFANA_PASSWORD="MyStrong123!Pass"
sudo -E bash scripts/deploy_monitoring.sh

```

If not set, a random 32-character password is generated.

### USB_PATH

If USB is mounted at different location:

```bash
export USB_PATH="/mnt/my-usb"
sudo -E bash scripts/deploy_monitoring.sh

```yaml

Default: `/media/adra/37f1914d-e5fd-48ca-8c24-22d5f4e2e9dd`

## After Deployment

### Access Dashboards

**Grafana** (Dashboards and Visualization)

- URL: `http://localhost:3000`

- Default User: `admin`

- Password: (displayed after deployment)

- Dashboards: 5 pre-configured dashboards available

**Prometheus** (Metrics and Targets)

- URL: `http://localhost:9090`

- Metrics: `http://localhost:9090/metrics`

- Targets: `http://localhost:9090/targets`

### Change Grafana Password

If you forgot or want to change the password:

```bash
sudo grafana-cli admin reset-admin-password "new-strong-password"

```

### View Service Logs

```bash

## View Prometheus logs

sudo journalctl -u prometheus -f

## View Grafana logs

sudo journalctl -u grafana-server -f

## View Node Exporter logs

sudo journalctl -u prometheus-node-exporter -f

```bash

### Check Service Status

```bash

## Check all monitoring services

sudo systemctl status prometheus grafana-server prometheus-node-exporter

## Check individual service

sudo systemctl status prometheus

```

### Restart Services

```bash

## Restart all services

sudo systemctl restart prometheus grafana-server prometheus-node-exporter

## Restart individual service

sudo systemctl restart prometheus

```bash

## Troubleshooting

### Script Won't Run - Permission Denied

```bash

## Make script executable

chmod +x scripts/deploy_monitoring.sh

## Run with sudo

sudo bash scripts/deploy_monitoring.sh

```

### USB Not Found

```bash

## Check if USB is mounted

ls -la /media/adra/37f1914d-e5fd-48ca-8c24-22d5f4e2e9dd

## If not mounted, mount it

sudo mount /dev/sdX1 /media/adra/37f1914d-e5fd-48ca-8c24-22d5f4e2e9dd

## Specify custom path

USB_PATH="/your/usb/path" sudo bash scripts/deploy_monitoring.sh

```bash

### Prometheus Won't Start

```bash

## Check logs

sudo journalctl -u prometheus -n 50

## Check config syntax

promtool check config /etc/justnews/monitoring/prometheus.yml

## Check if port 9090 is available

sudo ss -tlnp | grep 9090

```

### Grafana Won't Start

```bash

## Check logs

sudo journalctl -u grafana-server -n 50

## Check if port 3000 is available

sudo ss -tlnp | grep 3000

## Check permissions

ls -la /var/lib/justnews/grafana
ls -la /var/log/justnews/grafana

```bash

### Dashboards Not Loading Data

This is normal! Dashboards may take 1-2 minutes to show data as Prometheus:

1. Scrapes service targets (every 15 seconds)

1. Stores metrics in time series database

1. Grafana queries and displays data

To speed this up:

1. Access Prometheus targets page: <http://localhost:9090/targets>

1. Verify all targets show green (up)

1. Wait 2-3 scrape cycles for data to accumulate

1. Refresh Grafana dashboards

### Port Already in Use

If ports are already in use (9090 Prometheus, 3000 Grafana):

```bash

## Find what's using the port

sudo lsof -i :9090
sudo lsof -i :3000

## Stop the conflicting service

sudo systemctl stop <service-name>

## Or change port in configuration files

## Edit /etc/justnews/monitoring/prometheus.yml for web.listen-address

## Edit /etc/justnews/monitoring/grafana.ini for http_port

```

## Security Considerations

### Passwords

- ✅ Default Grafana password is changed during deployment

- ✅ Password is displayed and should be saved securely

- ⚠️ Change password immediately if default is used

### Network Access

- ✅ Prometheus listens on localhost only (127.0.0.1:9090)

- ✅ Node Exporter listens on localhost only (127.0.0.1:9100)

- ⚠️ Grafana listens on all interfaces (0.0.0.0:3000)

- Restrict with firewall if needed:

```bash sudo ufw allow from <your-ip> to any port 3000 sudo ufw deny from any to
any port 3000 ```

### Data Protection

- ✅ Prometheus stores data in `/var/lib/prometheus/`

- ✅ Data retention is 30 days (configurable)

- ✅ Consider backup strategy for production

## Configuration Files Location

After deployment, configurations are at:

```

/etc/justnews/monitoring/ ├── prometheus.yml              # Prometheus configuration ├── grafana.ini                 #
Grafana configuration └── grafana/ ├── provisioning/ │   ├── datasources/        # Prometheus datasource │   └──
dashboards/         # Dashboard definitions └── dashboards/             # Dashboard JSON files ├──
system_overview_dashboard.json ├── justnews_operations_dashboard.json ├── business_metrics_dashboard.json ├──
ingest_archive_dashboard.json └── parity_dashboard.json

```

## Systemd Service Files

```

/etc/systemd/system/ ├── prometheus.service           # Prometheus service ├── grafana-server.service       # Grafana
service └── prometheus-node-exporter.service  # Node Exporter service

```

## Data Storage Locations

```

/var/lib/prometheus/            # Prometheus metrics storage /var/lib/justnews/grafana/      # Grafana data and plugins
/var/log/justnews/grafana/      # Grafana logs /var/lib/node_exporter/         # Node Exporter textfiles

```

## Next Steps

### Verify Deployment

1. Open Grafana: <http://localhost:3000>

1. Login with admin / (generated password)

1. Check System Overview dashboard

1. Verify data is being collected

### Configure Alerts (Optional)

1. Review `docs/operations/ALERTING.md` (future doc)

1. Deploy AlertManager

1. Configure notification channels

### Monitor System Health

1. Check dashboards regularly

1. Set up alerts for critical metrics

1. Monitor logs: `sudo journalctl -u prometheus -f`

### Backup Configuration

```bash

## Backup Prometheus configs

sudo cp -r /etc/justnews/monitoring /backup/monitoring.backup

## Backup Prometheus data

sudo cp -r /var/lib/prometheus /backup/prometheus.backup

## Backup Grafana data

sudo cp -r /var/lib/justnews/grafana /backup/grafana.backup

```bash

## Support and Documentation

For more information, see:

- **Setup Details**: `docs/operations/MONITORING_INFRASTRUCTURE.md`

- **Troubleshooting**: `docs/operations/TROUBLESHOOTING.md` (Monitoring section)

- **All Documentation**: `docs/DOCUMENTATION_INDEX.md`

---

**Ready to Deploy?**

```bash
sudo bash scripts/deploy_monitoring.sh

```

**That's all you need!** ✅
