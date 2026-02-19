# Autonomic Orchestrator Phase 1 Baseline Snapshot

Date: 2026-02-19
Purpose: Baseline observability snapshot and regression guardrails before autonomic orchestrator implementation advances beyond Phase 1.

## Environment State

- Branch: `feat/autonomic-orchestrator`
- System state at snapshot close: fully stopped (all key service and database ports confirmed down)
- Verification command used:

```bash
for p in 8000 8001 8004 8005 8006 8007 8008 8009 8012 8013 8014 8016 8018 8020 8022 8023 8100 3306 3307 6379; do
  ss -ltn "sport = :$p" | tail -n +2 | sed '/^$/d' | awk -v port="$p" 'BEGIN{found=0} {found=1} END{if(found) print port" LISTEN"; else print port" down"}'
done
```

## Baseline Workflow Metrics (pre-shutdown snapshot)

Captured from live DB query immediately before full shutdown:

- Crawler jobs:
  - pending: 0
  - running: 0
  - completed: 49
  - failed: 6
  - outstanding jobs: 0
- Article pipeline:
  - total articles: 2236
  - not analyzed: 421
  - not embedded: 0
  - pending fact-check: 431
- Synthesis:
  - total synthesized articles: 1181
  - critique status distribution: completed=1181

## Regression Guardrails (Phase 1)

These guardrails must hold while implementing and validating Phase 1 changes:

1. Runtime stability
   - No orchestrator startup failures after port/mapping normalization.
   - No MCP bus agent discovery regressions for `workflow-orchestrator`.

2. Workflow health
   - `pending + running` crawler jobs should not show unexplained sustained growth after restart.
   - Analysis and fact-check backlogs should not worsen by more than 10% over two consecutive windows without a known cause.

3. Error boundaries
   - No new policy parsing errors tied to override expiry handling.
   - No repeated exceptions from `_safe_datetime` during policy evaluation.

4. Rollback trigger
   - If orchestrator registration/discovery breaks or policy loop errors rise materially, revert Phase 1 code changes before proceeding to Phase 2.

## Evidence References

- Implementation plan: `docs/architecture/AUTONOMIC_ORCHESTRATOR_IMPLEMENTATION_PLAN.md`
- Execution checklist: `docs/architecture/AUTONOMIC_ORCHESTRATOR_EXECUTION_CHECKLIST.md`
- Runbook: `docs/operations/AUTONOMIC_ORCHESTRATOR_RUNBOOK.md`
