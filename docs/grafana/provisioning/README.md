Grafana provisioning (docs) ---------------------------------

This folder contains example Grafana provisioning files that can be used to auto-provision dashboards and datasources in
a Grafana instance. These are documentation examples and must be wired into your Grafana container or server (for
example by copying them into /etc/grafana/provisioning/)

How to use

1. Copy `datasources.yml`to Grafana`/etc/grafana/provisioning/datasources/` and adjust the Prometheus URL or
   authentication block to match your deployment.

1. Copy `dashboards.yml`to`/etc/grafana/provisioning/dashboards/`and copy the`dashboards/`folder contents (for
   example,`docs/grafana/editorial-harness-dashboard.json`) to the configured path.

1. Restart Grafana or reload provisioning to pick up the new dashboards and datasources.

1. For the Stage 4 harness specifically, see `docs/grafana/editorial-harness-wiring.md` for scrape job requirements and
   alert suggestions.

## JustNews production specifics

- The canonical generated dashboards for production live under `monitoring/dashboards/generated/`(`*_dashboard.json`).
  Each file already carries the Grafana-ready shape (no`{"dashboard": ...}` wrapper) and includes the UID that exists in
  the live instance:

- `monitoring/dashboards/generated/business_metrics_dashboard.json`→ UID`af5zdqbqc8xkwf` (Business Metrics Dashboard)

- `monitoring/dashboards/generated/justnews_operations_dashboard.json`→ UID`ef37elu2756o0e` (JustNews Operations
  Dashboard)

- `monitoring/dashboards/generated/system_overview_dashboard.json`→ UID`ef5zdqbvm17uoc` (JustNews System Overview)

- To push updates into the systemd-managed Grafana service, copy those three files into
  `/etc/justnews/monitoring/grafana/dashboards/`and restart`justnews-grafana.service`. Provisioning runs every
  30 seconds, but a restart guarantees the reload and surfaces any validation errors in`journalctl -u justnews-grafana`.

- If you export a dashboard from the Grafana UI, strip the `{"dashboard": ...}`envelope and keep only the dashboard body
  with the correct`uid`before committing back into`monitoring/dashboards/generated/`. Provisioning rejects wrapped
  payloads with`Dashboard title cannot be empty`.

- When removing a dashboard permanently, delete the JSON file, remove the row from Grafana (`curl -X DELETE
  /api/dashboards/uid/<uid>`or, if RBAC blocks that, stop Grafana and prune the`dashboard`+`dashboard_provisioning`rows
  from`/var/lib/justnews/grafana/grafana.db` after taking a backup). This keeps the UI aligned with the curated set of
  dashboards tracked in Git.
