Continuation Plan — HITL Access & Crawler Integration

Summary:

- Goal: Ensure the Human-in-the-Loop (HITL) annotator UI is available, seeded with
candidates from the crawler, monitored, and safe to roll out into staging/production.

- Current state: HITL API serves the static UI at `/`and`/static/*`. The crawler builds candidate payloads and posts
  them to`/api/candidates`. Recent changes applied:`CandidateEvent.id`now defaults to`None` (prevents 422), crawler
  payload builder implemented, and automated tests added and passing.

Pending Tasks (prioritised): 1) CI + test coverage (High priority)

  - Why: ensure regressions are caught on PRs and remote CI runs the test suite.

  - Steps:

  - Add a minimal GitHub Actions workflow to run `pytest`on pushes/PRs (use the
    project's`environment.yml`or`requirements.txt` to install deps).

  - Run the new tests in CI and iterate if environment issues appear.

  - Verification: GitHub Actions shows green on this branch; tests pass.

2) Documentation and environment knobs (High priority)

  - Why: operators need clear guidance to configure the HITL service in different environments.

  - Steps:

  - Update `infrastructure/systemd/examples/hitl_service.env.example`with the key envs and brief descriptions:`HITL_SERV
    ICE_ADDRESS`,`HITL_DB_PATH`,`ENABLE_HITL_PIPELINE`,`HITL_STATS_INTERVAL_SECONDS`,`HITL_FAILURE_BACKOFF_SECONDS`,
    forwarding knobs (`HITL_FORWARD_AGENT`,`HITL_FORWARD_TOOL`).

  - Add `agents/hitl_service/README.md` explaining how to override DB path, enable/disable pipeline, and where the UI is
    served.

  - Verification: README present and example env includes knobs.

3) Ingest-forward integration test (Medium priority)

  - Why: validate the end-to-end label->ingest-forward path without requiring a live MCP Bus.

  - Steps:

  - Add a pytest that patches `mcp_client.call_tool`and exercises`store_label`/`dispatch_ingest` to ensure the code path
    constructs the right payload and handles retries/backoff.

  - Optionally add a small test that simulates `HITL_FORWARD_ENABLED=true` behavior with a dummy MCP client.

  - Verification: tests assert that `dispatch_ingest`calls`mcp_client.call_tool` and updates DB ingestion_status
    appropriately.

4) Controlled integration run and manual verification (Medium priority)

  - Why: verify crawler→HITL→UI→label→(ingest-forward) working in a full run.

  - Steps:

  - Run a controlled `unified_production_crawl` producing ~10 candidates from well-known domains.

  - Label a few items via the UI or programmatically (we have test coverage for programmatic labeling).

  - Check `GET /api/stats`,`GET /api/next`, and`hitl_labels`and`hitl_candidates` DB rows.

  - Verification: `/api/stats`reflects expected pending/in_review counts; labeled rows appear in`hitl_labels` and
    ingestion forward payloads are created.

5) Operational guidance and monitoring (Low priority)

  - Why: ensure service is observable and restartable in production.

  - Steps:

  - Document health endpoints: `GET /health`,`GET /ready`, and`GET /api/stats`.

  - Add a note to `infrastructure/systemd/scripts/enable_all.sh` docs to keep installed copies in sync.

  - Verification: operators can run health checks and the startup script includes HITL.

Acceptance criteria (for merge/rollout):

- Tests: New and existing tests pass in CI.

- End-to-end: a controlled run seeds candidates into HITL and the UI exposes them.

- Docs: example env file and `agents/hitl_service/README.md` added/updated.

Notes/Assumptions:

- This plan assumes local deployment and localhost endpoints by default; change `HITL_SERVICE_ADDRESS` for remote hosts.

- The local staging DB (`agents/hitl_service/hitl_staging.db`) is intentionally ignored from git and should remain
  local-only.

- The crawler will only POST candidates when `ENABLE_HITL_PIPELINE` is true (default true unless overridden).

Immediate next actions (recommendation):

- Add the GitHub Actions workflow to run `pytest` on pushes/PRs. I can scaffold this now and push it to the branch.

- Prepare `agents/hitl_service/README.md` and update the example env file. If you want, I can produce these files and
  push them.

If you want me to proceed: tell me which immediate action to take (add CI, add docs, or run a larger integrated crawl).
