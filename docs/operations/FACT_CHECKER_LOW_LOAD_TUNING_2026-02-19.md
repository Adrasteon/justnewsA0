# Fact-Checker Low-Load Tuning Note (2026-02-19)

## Objective

Increase fact-check queue drain speed under low system load while preserving call-path stability.

## Applied Defaults

- Workflow orchestrator
	- `polling_interval_seconds=3`
	- `max_concurrent_tasks=20`
- Fact-check shim
	- `FACT_CHECKER_SHIM_TIMEOUT_SEC=45`
	- `FACT_CHECKER_SHIM_MAX_RETRIES=0`
	- `FACT_CHECKER_SHIM_CB_FAILURE_THRESHOLD=20`
	- `FACT_CHECKER_SHIM_CB_OPEN_SEC=20`

## Validation Evidence

- Recovery check: `fact_checker.verify_article` via MCP returned `200` and persisted status updates to DB.
- 10-minute post-change monitor:
	- Backlog: `581 -> 501` (drain `80`)
	- Completed: `1655 -> 1735` (increase `80`)
	- Effective throughput: `8.0 items/min`
	- Policy error growth: `0`

## Operational Guardrails

- Keep `polling_interval_seconds` at `3` for this profile.
- Do not increase `max_concurrent_tasks` above `20` without a fresh canary.
- If `fact_checker.verify_article` begins returning `400/502/503` bursts:
	1. Check `GET http://localhost:8018/health` for `circuit_open`.
	2. Verify direct shim path (`POST /verify_article`) and MCP path (`POST /call`) separately.
	3. Temporarily reduce orchestrator concurrency to `15` until stable.

## Fast Rollback

- Runtime rollback (hot):

```bash
curl -sS -X PATCH http://127.0.0.1:8023/runtime-config \
	-H 'Content-Type: application/json' \
	-d '{
		"patch": {
			"orchestrator.max_concurrent_tasks": 15,
			"orchestrator.polling_interval_seconds": 3
		},
		"reason": "rollback_after_factcheck_instability",
		"actor": "operator"
	}'
```

- Shim recovery (if breaker remains open): restart `fact_checker` shim process with the configured env loaded from `global.env`.

