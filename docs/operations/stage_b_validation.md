--- title: "Stage B Validation Playbook" description: "Checklist and evidence collection steps to close out Stage B
ingestion quality work." tags: ["stage-b", "operations", "metrics", "governance", "validation"] ---

# Stage B Validation Playbook

This playbook captures the operational steps required to consider Stage B complete. Use it to track database migrations,
scheduler deployment, observability roll-out, QA cadences, and the proofs needed for exit criteria.

## 1. Database and Ingestion Plumbing

- Apply migration `database/migrations/003_stage_b_ingestion.sql`to your Stage B database.
  Confirm`collection_timestamp`,`normalized_url`,`url_hash`, metadata JSON columns, and the`embedding`vector field
  exist. Use`bash scripts/ops/apply_stage_b_migration.sh [DB_URL] --record`to apply and log the operation; command
  output is preserved under`logs/operations/migrations/` for audit.

- Verify the ingestion agent populates new fields:

- Invoke `agents/memory/tools.save_article`via unit tests (`tests/agents/memory/test_save_article.py`) or an ad-hoc
  ingestion to confirm`collection_timestamp`, dedupe hashes, review flags, and embeddings reach the database.

- Inspect a sample row with `SELECT title, normalized_url, url_hash, needs_review, collection_timestamp FROM articles
  ORDER BY id DESC LIMIT 5;`.

- Confirm Chroma metadata accepts the payload: run a spot check (for example, `python - <<'PY' ...
  collection.get(ids=['<article_id>']) ... PY`) and verify every metadata field is a scalar or JSON string. Null values
  or nested dicts must be stripped/serialized before ingestion; otherwise Chroma rejects the write
  with`metadatas[0].<field>: data did not match any variant of untagged enum MetadataValue`.

- When adding new metadata fields, update the sanitization helpers in `agents/memory/tools._make_chroma_metadata_safe`
  (and keep optional fields nullable in MariaDB) so embeddings continue to store cleanly.

- Document the migration execution (timestamp, operator, target database) in your ops log or ticket system.

## 2. Scheduler Bring-Up

- Ensure `config/crawl_schedule.yaml` matches the target source cohorts and governance metadata.

- Review the files under `config/crawl_profiles/` for the profile slugs each domain should receive (defaults, deep
  section overrides, explicit generic fallbacks). Keep this directory under version control; runtime changes do not
  require Python edits.

- Deploy the systemd timer:

- Install `infrastructure/systemd/scripts/run_crawl_schedule.sh`and the associated unit/timer
  under`/etc/systemd/system/`(e.g.,`justnews-crawl-scheduler.service`/`.timer`).

- Set environment values in `/etc/justnews/global.env`:`SERVICE_DIR`,`JUSTNEWS_PYTHON`,`CRAWL_SCHEDULE_PATH` (optional),
  and overrides for output paths if needed.

- Add `CRAWL_PROFILE_PATH=/etc/justnews/crawl_profiles` (or your custom path) if the default profiles live outside the
  repo checkout. The loader accepts either a directory or a single YAML file for backwards compatibility.

- Ensure the analytics directory exists and is writable by the scheduler user: `sudo mkdir -p
  "$SERVICE_DIR/logs/analytics" && sudo chown -R <scheduler-user>:<scheduler-group> "$SERVICE_DIR/logs"`.

- Run `sudo systemctl daemon-reload && sudo systemctl enable --now justnews-crawl-scheduler.timer`.

- Capture dry-run evidence:

- Execute `JUSTNEWS_PYTHON scripts/ops/run_crawl_schedule.py --dry-run --max-target 100 --profiles
  config/crawl_profiles` to show planned batches (and expanded profile payloads) without invoking the crawler.

- Capture live-run evidence:

- Tail the timer journal (`journalctl -u justnews-crawl-scheduler.service -n 200`) and archive the
  latest`logs/analytics/crawl_scheduler_state.json` snapshot.

## 3. Observability Roll-Out

- Prometheus textfile metrics are written to `logs/analytics/crawl_scheduler.prom`. Register (or symlink) this file with
  your node exporter textfile collector; on systemd hosts run:

```bash sudo mkdir -p /var/lib/node_exporter/textfile_collector sudo chown
adra:adra /var/lib/node_exporter/textfile_collector sudo sed -i 's|^CRAWL_SCHEDU
LER_METRICS=.*|CRAWL_SCHEDULER_METRICS=/var/lib/node_exporter/textfile_collector
/crawl_scheduler.prom|' /etc/justnews/global.env sudo systemctl daemon-reload &&
sudo systemctl restart justnews-crawl-scheduler.service ``` Confirm
`crawl_scheduler.prom` appears under
`/var/lib/node_exporter/textfile_collector/` and that Prometheus scrapes the new
target.

- Stage B embedding metrics:

  - `common/stage_b_metrics.StageBMetrics` exports `justnews_stage_b_embedding_total{status=...}` and `justnews_stage_b_embedding_latency_seconds{cache=...}`.

  - Ensure the memory agent’s Prometheus endpoint or push gateway path includes these counters.

- Dashboard updates:

  - Create panels for extraction/ingestion outcomes, embedding status (success, error, model_unavailable), latency percentiles, duplicate counts, and scheduler lag (`justnews_crawler_scheduler_lag_seconds`).

  - Add per-language filters where possible to highlight QA sampling needs.

- Alert thresholds (recommended):

  - Embedding errors > 3% over 15 minutes.

  - Scheduler lag > 5 minutes for two consecutive runs.

  - `needs_review` ratio > 10% for any source cohort.

## 4. Human QA and Governance Cadence

- Establish a weekly sampling review: pull `needs_review` articles per language/region into `logs/governance/crawl_terms_audit.md`. Use the provided template (cohort, URL, terms status, QA notes, follow-up) and attach supporting captures when anomalies appear.

- Track source terms-of-use and rate-limit acknowledgements in the same log; note remediation for violations.

- Confirm the success history file (`logs/analytics/crawl_scheduler_success.json`) is rotated and archived for audits.

## 5. Integration and Regression Validation

- Run targeted tests:

  - `conda run -n ${CANONICAL_ENV:-justnews-py312} python -m pytest tests/agents/crawler/test_extraction.py tests/agents/memory/test_save_article.py -q`

  - `conda run -n ${CANONICAL_ENV:-justnews-py312} python -m pytest tests/scripts/test_run_crawl_schedule_integration.py -q`

- Optional end-to-end smoke: trigger the scheduler with `--no-wait` and ensure articles flow into the database with embeddings present.

- Record test outputs (command, environment, timestamp) in the bring-up ticket.

## 6. Exit Evidence Checklist

Collect the following artifacts before declaring Stage B complete:

- [ ] Migration 003 applied, schema verified.

- [ ] Hourly scheduler active, last-run state JSON archived.

- [ ] Prometheus scrape showing embedding counters and scheduler gauges over a 24-hour window.

- [ ] Grafana (or equivalent) screenshot highlighting extraction success > 95% and `needs_review` < 5%.

- [ ] Duplicate suppression validated via sample queries (`SELECT COUNT(*) FROM articles WHERE status='duplicate'` or equivalent metrics) with results archived under `logs/operations/evidence/`.

- [ ] Human QA sampling log entries covering at least two cohorts.

- [ ] Test suite outputs attached to the change record.

Maintain this document alongside change requests so future operators can rapidly
revalidate Stage B after upgrades or incident recoveries.
