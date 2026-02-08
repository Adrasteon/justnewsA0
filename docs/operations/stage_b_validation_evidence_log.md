--- title: "Stage B Validation Evidence Log" description: "Chronological record of artifacts collected while executing
the Stage B validation playbook." tags: ["stage-b", "ops", "evidence"] ---

# Stage B Validation Evidence Log

## 2025-10-26 — Initial Capture

- **Operator**: GitHub Copilot (automation assist)

- **Environment**: Stage B development host (`conda env ${CANONICAL_ENV:-justnews-py312-phase1}`)

- **Ticket Template**: `docs/operations/stage_b_ticket_template.md`

### Evidence Summary

| Item | Status | Notes | Proof Reference | | --- | --- | --- | --- | | Migration 003 applied | Complete | Executed
2025-10-26 with superuser credentials; see transcripts `logs/operations/migrations/migration_003_20251026T185331Z.log`
and `migration_003_20251026T194119Z.log`. |`database/migrations/003_stage_b_ingestion.sql` | Scheduler timer enabled |
Complete | Unit installed under `/etc/systemd/system`; first production run captured 2025-10-26T19:12Z. |`journalctl -u
justnews-crawl-scheduler.service -n 200 --no-pager` | Scheduler state archive | Complete |
`logs/analytics/crawl_scheduler_state.json`saved after first live run. |`logs/analytics/crawl_scheduler_state.json` |
Scheduler metrics exported | Complete | Node exporter textfile collector now consumes
`/var/lib/node_exporter/textfile_collector/crawl_scheduler.prom`. |`ls -l
/var/lib/node_exporter/textfile_collector/crawl_scheduler.prom` | Stage B metrics emitting | Complete | Embedding
counters/histogram verified via targeted pytest run. | `conda run -n ${CANONICAL_ENV:-justnews-py312-phase1} python -m pytest
tests/agents/crawler/test_extraction.py tests/agents/memory/test_save_article.py -q` | Migration helper script |
Complete | `scripts/ops/apply_stage_b_migration.sh` added for repeatable migration execution and evidence capture. |
`scripts/ops/apply_stage_b_migration.sh`| Migration logs | Complete | Helper now stores`psql` output under
`logs/operations/migrations/`so transcripts persist after execution. |`logs/operations/migrations/` | Dashboard
updates | Deferred | Snapshot capture awaits GUI export; Prometheus data confirmed. | Grafana board (deferred by devs) |
QA sampling log | Complete | Initial governance capture recorded 2025-10-26 with prioritized source sampling. |
`logs/governance/crawl_terms_audit.md`| Duplicate suppression query | Complete | Query run 2025-10-26; only`NULL`
buckets surfaced (expected for legacy rows without hashes). | `logs/operations/evidence/dedupe_query_20251026.txt` |
Test artifacts stored | Complete | Pytest command executed 2025-10-26; results 8 passed. | Terminal session
(`tests/agents/...`)

### Follow-Up Actions

- 2025-10-26T18:53:44Z — Migration 003 applied via `bash scripts/ops/apply_stage_b_migration.sh
  postgresql://postgres@localhost/justnews --record`; transcript stored
  under`logs/operations/migrations/migration_003_20251026T185331Z.log`.

- 2025-10-26T19:12:18Z — Scheduler timer run completed; see `journalctl`excerpt and state/success JSON
  under`logs/analytics/`plus Prometheus textfile`crawl_scheduler.prom`.

- 2025-10-26T19:21:21Z — Scheduler metrics redirected to node exporter textfile collector
  (`/var/lib/node_exporter/textfile_collector/crawl_scheduler.prom`).

- 2025-10-26T19:25:00Z — QA sampling log initialized in `logs/governance/crawl_terms_audit.md` covering Stage B smoke
  check.

- Dashboard snapshot capture deferred pending Grafana GUI export by ops (metrics validated in Prometheus textfile).

- 2025-10-26T19:41:35Z — Migration 003 reapplied via `bash scripts/ops/apply_stage_b_migration.sh
  postgresql://postgres@localhost/justnews --record`; transcript stored
  under`logs/operations/migrations/migration_003_20251026T194119Z.log`.

- 2025-10-26T19:43:10Z — Duplicate suppression query executed; results archived under
  `logs/operations/evidence/dedupe_query_20251026.txt`.

## 2025-11-02 — BBC profile verification

- **Operator**: GitHub Copilot (automation assist)

- **Environment**: systemd baseline host after canonical restart (`conda env ${CANONICAL_ENV:-justnews-py312-phase1}`)

- **Scope**: validate BBC Crawl4AI profile after JSON sanitization fixes

### Evidence Summary

| Item | Status | Notes | Proof Reference | | --- | --- | --- | --- | | Canonical restart | Complete | `sudo
./infrastructure/systemd/canonical_system_startup.sh` run; all 17 services healthy post-check. | Terminal transcript
2025-11-02T16:25Z (ticket attachment) | Scheduler rerun | Complete | `PYTHONPATH=. conda run -n
${CANONICAL_ENV:-justnews-py312-phase1} python scripts/ops/run_crawl_schedule.py --schedule config/crawl_schedule_bbc.yaml
--profiles config/crawl_profiles --testrun --no-wait`. |`logs/analytics/crawl_scheduler_state.json` | Ingestion outcome
| Complete | Latest state shows 60 attempted, 60 ingested, 0 duplicates/errors for bbc.co.uk. |
`logs/analytics/crawl_scheduler_state.json` | Sample verification | Complete | Random sampler captured article
titles/text for three newly ingested URLs. | Terminal snippet `sample_bbc_articles_20251102.txt` | Metrics check |
Complete | Stage B counters show success-only increments post- run. | `logs/analytics/crawl_scheduler.prom`

### Follow-Up Actions

- 2025-11-02T16:18Z — Canonical restart executed to load shared `make_json_safe` logic across crawler and memory agents.

- 2025-11-02T16:31Z — BBC scheduler test run completed (`--testrun`), producing all-new ingestion entries with zero
  serialization errors.

- 2025-11-02T16:34Z — Random sample script recorded titles/text snippets for audit; attached to bring-up ticket and
  stored under `logs/operations/evidence/sample_bbc_articles_20251102.txt`.
