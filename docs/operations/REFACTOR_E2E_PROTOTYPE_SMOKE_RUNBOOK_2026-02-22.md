# Refactor E2E Prototype Smoke Runbook

> Historical context note: This document may describe legacy startup/orchestration flows captured at the time. Canonical runtime for JustNews is Docker-first. See `docs/operations/DOCKER_FIRST_STRATEGY.md` and `docs/operations/DOCKER_CANONICAL_COMMANDS.md`.


Date: 2026-02-22  
Scope: Fastest path to demonstrate refactored JustNews functionality end-to-end

## 1) Goal

Validate that the refactored code path is functional from orchestrator policy chain through publication lane metadata and publish behavior.

## 2) One-Command Smoke Check (No Writes)

```bash
/app/.venv/bin/python scripts/ops/run_refactor_e2e_smoke.py --limit 5
```

Outputs:
- JSON report: `logs/operations/e2e_refactor_smoke/refactor_e2e_smoke_check_<timestamp>.json`
- Markdown report: `logs/operations/e2e_refactor_smoke/refactor_e2e_smoke_check_<timestamp>.md`

Use this to confirm queue state and recent lane/provenance metadata presence.

## 3) One-Command Smoke Execute (Active)

```bash
/app/.venv/bin/python scripts/ops/run_refactor_e2e_smoke.py --execute --limit 5
```

This runs the policy chain in sequence:
1. `ingestion_to_analysis`
2. `analysis_to_embedding`
3. `analysis_to_fact_check`
4. `incremental_clustering`
5. `cluster_to_synthesis`
6. `synthesis_to_critique`
7. `synthesis_to_publishing`

## 4) Prototype Success Signals

- Report `summary.status` is `ok` or `warning` (no execution errors).
- Recent stories include `publication_lane` (`verified_story` or `developing_brief`).
- For `developing_brief` stories, publish output includes explicit caveat labeling.

## 5) If Status Is `warning`

`warning` usually means no recently published lane-tagged story was found in the sampled rows.

Actions:
- Re-run with larger sample: `--limit 20`
- Re-run active mode: `--execute --limit 20`
- Ensure live agents are reachable via MCP bus and have backlog items to process.

## 6) If Status Is `error`

Inspect `policy_results[*].execution_error` in the JSON report and verify:
- MCP bus URL (`--mcp-bus-url`) is correct,
- required agents are running and registered,
- MariaDB connectivity is healthy.

## 7) BBC Lane 1 Entity-Ingestion Verifier (Live)

Use this when validating the specific regression where feed content was collapsed
into a single ingested blob.

```bash
/app/.venv/bin/python scripts/ops/verify_bbc_lane1_entity_ingestion.py \
	--crawler-url "http://localhost:8015" \
	--domain "bbc.co.uk" \
	--requested 10 \
	--min-articles 8
```

The verifier asserts:
- BBC crawl returns multiple distinct article URLs.
- Feed XML/homepage payload is not ingested as a single article body.
- Ingestion details contain per-URL records (individual entity handling).

Outputs:
- JSON report: `logs/operations/live_validation/bbc_lane1_entity_verification_<timestamp>.json`
- Markdown report: `logs/operations/live_validation/bbc_lane1_entity_verification_<timestamp>.md`
