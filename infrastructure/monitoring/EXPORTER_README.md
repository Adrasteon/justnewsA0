JustNews DB exporter =====================

This repository-level note documents the justnews DB exporter service we added to expose simple ChromaDB and MariaDB
connectivity metrics for Prometheus.

What changed ------------

- A small exporter script lives at: /opt/justnews/monitoring/exporters/justnews_db_exporter.py

- A virtualenv is used by the service: /opt/justnews/monitoring/exporters/venv (owned by user justnews)

- Systemd unit: /etc/systemd/system/justnews-db-exporter.service

- The unit includes an ExecStartPost health probe (waits ~5s for /metrics) and Restart/RestartSec/StartLimit* settings
  to prevent hot crash loops.

Operational notes -----------------

- To update exporter dependencies:
sudo -u justnews /opt/justnews/monitoring/exporters/venv/bin/pip install --upgrade prometheus_client requests

- To check metrics locally:
curl -sS <http://127.0.0.1:9127/metrics> | head -n 40

- To inspect systemd unit and recent logs:
sudo systemctl status justnews-db-exporter.service sudo journalctl -u justnews- db-exporter.service -n 200

Why this approach ----------------- Using a venv under /opt avoids running the exporter under a human user's home
directory and keeps the service isolated. The ExecStartPost probe gives a quick fail-fast behaviour so systemd will
restart the service if it doesn't come up correctly.

Alerting (repo) ---------------- We added a simple Prometheus alerting rules file in the repository. Path:

infrastructure/monitoring/alerts/justnews_db_alerts.yml

Rules included (high level):

- `ChromaDBDown`: fires when`justnews_chromadb_up == 0` for 1 minute (severity: critical)

- `MariaDBDown`: fires when`justnews_mariadb_up == 0` for 1 minute (severity: critical)

To enable these rules in the deployed Prometheus server, add the file (or a symlink) under
`/etc/justnews/monitoring/rules/`and include it in Prometheus'`rule_files` or add the directory to the Prometheus
configuration, then reload Prometheus:

sudo mkdir -p /etc/justnews/monitoring/rules sudo cp infrastructure/monitoring/alerts/justnews_db_alerts.yml
/etc/justnews/monitoring/rules/
# then either reload or restart Prometheus
sudo systemctl reload justnews-prometheus.service || sudo systemctl restart justnews-prometheus.service

Why this approach ----------------- Using a venv under `/opt` avoids running the exporter under a human user's home
directory and keeps the service isolated. The `ExecStartPost` probe gives a quick fail-fast behaviour so systemd will
restart the service if it doesn't come up correctly.

Operational runbook snippet --------------------------

- Check metrics:
curl -sS <http://127.0.0.1:9127/metrics>

- Update deps:
sudo -u justnews /opt/justnews/monitoring/exporters/venv/bin/pip install --upgrade prometheus_client requests

- Restart exporter service:
sudo systemctl restart justnews-db-exporter.service

- Check Prometheus target status:
curl -sS <http://127.0.0.1:9090/api/v1/targets> | jq '.data.activeTargets[] | select(.labels.job=="justnews-db-exporter")'

JustNews DCGM exporter ======================

The NVIDIA DCGM exporter publishes GPU health/telemetry so we can correlate future GPU hangs or machine-wide crashes
with device metrics. The exporter ships with a hardened metrics list and runs via systemd under the `justnews` account.

Deployment assets ------------------

- Metrics profile: `infrastructure/systemd/monitoring/dcgm/metrics_default.csv`

- Systemd unit template: `infrastructure/systemd/units/justnews-dcgm-exporter.service`

- Installer helper: `scripts/ops/install_dcgm_exporter.sh`

- Installed paths (after running the script):

- Binary: `/opt/justnews/monitoring/dcgm/dcgm-exporter`

- Metrics file: `/etc/justnews/monitoring/dcgm/metrics.csv`

- Env overrides: `/etc/justnews/monitoring/dcgm/dcgm-exporter.env`

- Systemd unit: `/etc/systemd/system/justnews-dcgm-exporter.service`

Installation workflow ---------------------

1. Ensure NVIDIA drivers + DCGM libs exist (the server already has `nvidia-smi`).

1. Run the installer as root (it drops files owned by `justnews` and installs the unit):

```
bash cd /home/adra/JustNews sudo scripts/ops/install_dcgm_exporter.sh
```

   - Script flags: set `DCGM_EXPORTER_VERSION`to override the default release,`DCGM_EXPORTER_PORT` if port 9400 cannot
     be used, and `DCGM_EXPORTER_LISTEN` to bind to a different interface (defaults provided inside the script). Edit
     `/etc/justnews/monitoring/dcgm/dcgm-exporter.env` after install to make persistent overrides.

1. Reload systemd and start the exporter (installer already runs these, but for manual tweaks):

```bash sudo systemctl daemon-reload sudo systemctl enable --now justnews-dcgm-
exporter.service
```

Prometheus integration ----------------------

- Scrape config snippet (append under `scrape_configs`in`prometheus.yml` and reload the service):

```yaml

  - job_name: justnews-dcgm-exporter
scrape_interval: 15s static_configs:

      - targets: ['127.0.0.1:9400']

```

- After updating Prometheus config:

```bash sudo systemctl reload justnews-prometheus.service || sudo systemctl
restart justnews-prometheus.service ```

Operational notes -----------------

- Check exporter logs/status:

```bash sudo systemctl status justnews-dcgm-exporter.service sudo journalctl -u
justnews-dcgm-exporter.service -n 200
```

- Query metrics locally (confirms scrape surface works):

```
bash curl -sS <http://127.0.0.1:9400/metrics> | head -n 40
```

- Adjust metrics profile: edit `/etc/justnews/monitoring/dcgm/metrics.csv` and restart the service. The file defaults to the repo copy; keep a copy in Git for future updates.

- Verify Prometheus has an active target:

```bash curl -sS <http://127.0.0.1:9090/api/v1/targets> | jq
'.data.activeTargets[] | select(.labels.job=="justnews-dcgm-exporter")'
```

Why DCGM -------- DCGM surfaces ECC/Xid error counters, clock throttling reasons, and utilization data directly from
NVIDIA drivers. Capturing these metrics continuously gives us pre-crash evidence when GPUs wedge or thermal- limit.
Running the exporter as `justnews` with a dedicated metrics file keeps configuration changes auditable while systemd
handles restarts.
