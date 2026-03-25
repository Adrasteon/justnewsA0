# Hermes JustNews Operating Playbook

Purpose:
- Standardize how Hermes is used for development, operations, and incident response in JustNews.
- Reduce drift, speed up changes, and improve consistency across sessions and operators.

## Scope

Use this playbook for:
- Daily development workflow
- Feature planning and implementation support
- PR preflight checks
- Incident triage and stabilization
- Release readiness checks

## Baseline Assumptions

- Hermes is authenticated to GitHub Copilot and default model is configured.
- Honcho is enabled and connected for cross-session memory continuity.
- Local indexing scripts are available under scripts/indexing.

## Daily Workflow

### 1. Morning bootstrap

Run:

```bash
make index-hermes-daily
```

Outcome:
- Session bootstrap and model binding refresh
- Incremental index refresh
- Bootstrap snapshot output
- Telemetry summary for health signal

### 2. Daily benchmark (quick quality gate)

Use prompt:
- .github/prompts/justnews-hermes-benchmark.prompt.md

Outcome:
- Detects retrieval or architecture understanding drift early

## Feature Delivery Workflow

### 1. Impact mapping

Run index query before editing:

```bash
make index-query QUERY='target subsystem behavior contract tests'
```

Ask Hermes for:
- likely files to edit
- tests to run
- migration or config touchpoints

### 2. Implementation

Use Hermes to:
- draft minimal change plan
- edit only impacted files
- preserve existing conventions

### 3. Focused validation

Run targeted checks relevant to changed area:

```bash
pytest tests/agents/test_crawler_engine.py -k 'keyword'
python3 scripts/ops/validate_crawl_lane_behavior.py
```

If full-suite pytest is known to fail from unrelated legacy deps, prefer focused suites for local validation.

## PR Preflight Workflow

### 1. Local preflight

```bash
git status --short
make index-bootstrap
make index-telemetry-summary
```

### 2. Hermes review checklist

Have Hermes verify:
- behavioral regressions
- riskier edge cases
- missing tests
- docs drift from code changes

### 3. Commit hygiene

- one concern per commit where practical
- clear commit subject with subsystem context

## Incident Triage Workflow

### 1. Fast signal sweep

Run only high-signal checks first:

```bash
python3 check_workflow_progress.py
python3 check_db_status.py
python3 check_latest_ingestion.py
```

### 2. Focused deep dive

Use Hermes to generate next-command sequence based on observed failures, not generic script sweeps.

### 3. Stabilization actions

- apply smallest safe fix
- re-run only relevant health checks
- record what changed and why

## Release Readiness Workflow

### 1. Pre-release checks

- telemetry trend healthy
- no known blocker in critical workflow scripts
- migration plan and rollback steps documented
- docs updated for operational behavior changes

### 2. Final gate prompts for Hermes

Ask Hermes to provide:
- release risk summary
- rollback plan sanity check
- missing evidence list for sign-off

## Messaging and Remote Ops (Telegram)

In this dev container, systemd user service may be unavailable. Use background process mode for gateway:

```bash
nohup hermes gateway run --replace >/root/.hermes/logs/gateway.out 2>&1 &
```

Health checks:

```bash
ps -ef | grep -E 'hermes gateway run|gateway/run.py' | grep -v grep
tail -n 80 /root/.hermes/logs/gateway.out
```

## Memory and Continuity Rules

- Keep Honcho in hybrid mode for resilient cross-session continuity.
- Store durable operational lessons in repo memory notes.
- Refresh JUSTNEWS_HERMES_KNOWLEDGE_PACK.md when architecture or runbook truth changes.

## Recommended Cadence

- Daily: make index-hermes-daily
- Weekly: run benchmark prompt and review score trend
- Per feature: index query first, focused tests before commit
- Per incident: log root cause and fix in ops notes

## Success Criteria

- Faster task startup (less context rehydration overhead)
- Fewer regression loops from broad/unscoped edits
- Higher consistency in operator actions and release checks
- Better long-horizon memory continuity across development sessions
