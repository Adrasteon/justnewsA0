--- title: "Stage B Validation Ticket Template" description: "Template for tracking Stage B ingestion validation in the
ops ticketing system." tags: ["stage-b", "ops", "ticket-template"] ---

# Stage B Validation Ticket Template

## Summary

- **Objective**: `Stage B validation for <environment>`

- **Change window**: `<start-end>`

- **Owner(s)**: `<ops-oncall>`

- **Related artifacts**: `docs/operations/stage_b_validation.md`

## Preconditions

- Stage A bring-up verified ✅

- Required migrations reviewed (`database/migrations/003_stage_b_ingestion.sql`)

- Scheduler configuration confirmed (`config/crawl_schedule.yaml`)

## Execution Plan

1. Apply migration 003 to target database.

1. Enable `justnews-crawl-scheduler.timer` and monitor first live run.

1. Register Prometheus textfile exporter path for scheduler metrics.

1. Validate embedding counters/histogram in Prometheus scrape.

1. Run targeted pytest suites (crawler + memory + scheduler integration).

1. Capture QA sampling notes for needs_review cohorts.

## Validation Checklist

- [ ] Migration applied; schema inspected with `SELECT` sample.

- [ ] Scheduler timer active; last run timestamp recorded.

- [ ] `logs/analytics/crawl_scheduler_state.json` archived.

- [ ] Prometheus scrape shows Stage B embedding counters and latency histogram.

- [ ] Dashboard panels updated for Stage B metrics (extraction, ingestion, embeddings, scheduler lag).

- [ ] QA sampling log updated in `logs/governance/crawl_terms_audit.md`.

- [ ] Duplicate suppression sample query executed and result captured.

- [ ] Test outputs attached (commands + timestamps).

## Evidence Log

| Item | Evidence | Status | | --- | --- | --- | | Migration 003 | `<psql output or screenshot>` | Pending | | Scheduler
| `journalctl -u justnews-crawl- scheduler.service -n 200`| Pending | | Metrics |`conda run -n
${CANONICAL_ENV:-justnews-py312} python -m pytest ...`| Pending | | Dashboard |`<Grafana panel link>` | Pending | | QA
Sampling | `logs/governance/crawl_terms_audit.md` entry | Pending |

## Rollback Plan

- Disable scheduler timer: `sudo systemctl disable --now justnews-crawl-scheduler.timer`.

- Revert migration if necessary using `database/migrations/003_stage_b_ingestion.sql` down script.

- Restore previous metrics or dashboard configuration snapshots.

## Notes

- Attach relevant screenshots/logs as ticket attachments.

- Reference the `docs/operations/stage_b_validation.md` playbook for detailed steps and thresholds.
