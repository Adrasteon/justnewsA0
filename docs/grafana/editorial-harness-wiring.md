# Editorial Harness Grafana Wiring

This guide describes how to expose the Stage 4 editorial-harness metrics to Grafana so operators can monitor acceptance
rates, follow-up volume, and failure spikes. It assumes Prometheus and Grafana already run next to the JustNews services
(systemd or docker-compose).

## Metric overview

| Metric | Type | Labels | Description | | --- | --- | --- | --- | | `justnews_stage_b_editorial_harness_total` |
Counter | `result`(`accepted`,`needs_followup`,`error`) | Incremented every time the harness finishes an article. | |
`justnews_stage_b_editorial_acceptance_bucket`/`sum`/`count`| Histogram |`le` | Acceptance score distribution
emitted for each harness run. |

All Stage B counters live in the default Prometheus registry from `common.stage_b_metrics`. Any process that imports
those helpers and exposes `/metrics` will publish the counters when Prometheus scrapes it.

## Step 1: expose the metrics to Prometheus

1. Ensure the agents that participate in Stage 4 expose `/metrics`.

- Every systemd unit started via `infrastructure/systemd/scripts/enable_all.sh` already runs a FastAPI service with
  Prometheus middleware.

- The editorial harness job typically runs via cron or CI (`scripts/dev/run_agent_chain_harness.py`). Pair it with a
  Pushgateway or textfile exporter so counters persist between runs.

1. Add (or extend) a Prometheus scrape job that hits those ports. Example for the crawler host:

```yaml scrape_configs:

     - job_name: justnews-agents
metrics_path: /metrics scrape_interval: 30s static_configs:

         - targets:

             - localhost:8011   # analytics

             - localhost:8012   # archive

             - localhost:8013   # dashboard / transparency

             - localhost:8014   # gpu orchestrator

             - localhost:8015   # crawler

             - localhost:8016   # crawler control / journalist harness calls

```

1. When the harness is a short-lived batch job, push its counters so data survives between runs.

- **Pushgateway**

```bash PROM_PUSH_GATEWAY=http://prometheus-pushgateway:9091 \ python - <<'PY'
from prometheus_client import CollectorRegistry, push_to_gateway from
common.stage_b_metrics import get_stage_b_metrics

registry = CollectorRegistry() metrics = get_stage_b_metrics()
push_to_gateway(PROM_PUSH_GATEWAY, job='justnews-editorial-harness',
registry=registry) PY ```

   - **Node exporter textfile collector**
     1. Create `/var/lib/node_exporter/textfile_collector` (or another writable path) and point node exporter to it.
     1. After each harness run, call `write_to_textfile(path, metrics.registry or CollectorRegistry())` similar to `scripts/ops/run_crawl_schedule.py`.

1. Validate locally: `curl -s <http://localhost:8011/metrics> | grep justnews_stage_b_editorial` should return samples once the harness runs at least one article.

## Step 2: provision Grafana

1. Copy the sample provisioning files and adjust the Prometheus URL:

```bash sudo mkdir -p /etc/grafana/provisioning/{datasources,dashboards} sudo cp
docs/grafana/provisioning/datasources.yml /etc/grafana/provisioning/datasources/ sudo cp
docs/grafana/provisioning/dashboards.yml /etc/grafana/provisioning/dashboards/ sudo mkdir -p
/var/lib/grafana/dashboards/justnews sudo cp docs/grafana/editorial-harness- dashboard.json
/var/lib/grafana/dashboards/justnews/
```

1. Restart Grafana (`sudo systemctl restart grafana-server`) or manually import`docs/grafana/editorial-harness-dashboard.json`via **Dashboards → Import**. The JSON expects a data source named`Prometheus`; rename yours or edit the dashboard if needed.

## Step 3: validate the dashboard

1. Open the dashboard with UID `justnews-editorial-harness` (title: *JustNews — Editorial Harness*).

1. Confirm the panels render:

- Outcomes per second should show accepted, follow-up, and error series after each run.

- Acceptance ratio (5m rolling) must remain within 0–1 (alert if < 0.6).

- Acceptance distribution visualizes histogram buckets (`<= 0.2`,`<= 0.4`, etc.).

- Harness runs (24h) reflects the cumulative executions for the window.

1. Use Grafana Explore to run `sum(increase(justnews_stage_b_editorial_harness_total[6h])) by (result)` when validating new scrapes.

## Step 4: add alerts

Recommended alert rules (Grafana or Prometheus):

- Error spike: `sum(rate(justnews_stage_b_editorial_harness_total{result="error"}[10m])) > 0` for three evaluations.

- Acceptance slump: `sum(rate(justnews_stage_b_editorial_harness_total{result="accepted"}[15m])) / clamp_min(sum(rate(justnews_stage_b_editorial_harness_total[15m])), 1e-9) < 0.6`.

- Volume gap: `increase(justnews_stage_b_editorial_harness_total[60m]) == 0` while cron/CI is expected to run.

## Troubleshooting

- **No samples**: confirm the Prometheus scrape job exists and that `curl <http://host:port/metrics`> outputs`justnews_stage_b_editorial_*` counters.

- **Counters reset each run**: store results in Pushgateway or a textfile collector so Prometheus retains the latest snapshot.

- **Dashboard missing data source**: rename your Grafana data source to `Prometheus` or edit the dashboard JSON.

- **Alert noise during maintenance**: pause the alert or add a silence when services are intentionally stopped via `enable_all.sh stop`.

With the scrape job, provisioning files, and dashboard imported, Stage 4 acceptance trends become visible ahead of the
Stage 5 publishing work.
