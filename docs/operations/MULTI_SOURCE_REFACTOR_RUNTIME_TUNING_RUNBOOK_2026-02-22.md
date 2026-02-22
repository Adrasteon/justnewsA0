# Multi-Source Refactor Runtime Tuning Runbook

**Date:** 2026-02-22  
**Scope:** Safe runtime tuning and rollback of lane policy controls  
**Service:** `workflow_orchestrator`

## 1) Purpose

Provide copy/paste runtime-config procedures for:

- enabling/disabling lane policy,
- tuning lane thresholds by environment,
- and performing versioned rollback.

This runbook is for **dev/canary/full staged rollout** only.

## 2) Preconditions

- Workflow orchestrator is reachable.
- You have operator access to runtime-config endpoints.
- A reason string is prepared for audit history.

Base URL example:

```bash
export ORCH_URL="http://localhost:8023"
```

## 3) Runtime Keys (Current)

- `orchestrator.lane_policy.enabled` (bool)
- `orchestrator.lane_policy.min_source_count` (int)
- `orchestrator.lane_policy.min_unique_domains` (int)
- `orchestrator.lane_policy.version` (str)

## 4) Validate a Patch Before Apply

```bash
curl -sS -X POST "$ORCH_URL/runtime-config/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "patch": {
      "orchestrator.lane_policy.enabled": true,
      "orchestrator.lane_policy.min_source_count": 2,
      "orchestrator.lane_policy.min_unique_domains": 2,
      "orchestrator.lane_policy.version": "v1"
    }
  }' | jq .
```

Expected: `"status": "ok"` and no validation errors.

## 5) Apply Patch (Hot Runtime)

```bash
curl -sS -X PATCH "$ORCH_URL/runtime-config" \
  -H "Content-Type: application/json" \
  -d '{
    "patch": {
      "orchestrator.lane_policy.enabled": true,
      "orchestrator.lane_policy.min_source_count": 2,
      "orchestrator.lane_policy.min_unique_domains": 2,
      "orchestrator.lane_policy.version": "v1"
    },
    "reason": "enable lane policy for dev burn-in",
    "actor": "ops"
  }' | jq .
```

Expected response includes:

- `status: ok`
- `version: <new version>`
- `owner_apply_result.applied` containing the lane keys.

## 6) Common Change Recipes

### A) Disable lane policy quickly (safety hold)

```bash
curl -sS -X PATCH "$ORCH_URL/runtime-config" \
  -H "Content-Type: application/json" \
  -d '{
    "patch": {
      "orchestrator.lane_policy.enabled": false,
      "orchestrator.lane_policy.version": "v1-hold"
    },
    "reason": "temporary hold while investigating quality regression",
    "actor": "ops"
  }' | jq .
```

### B) Tighten thresholds in canary

```bash
curl -sS -X PATCH "$ORCH_URL/runtime-config" \
  -H "Content-Type: application/json" \
  -d '{
    "patch": {
      "orchestrator.lane_policy.min_source_count": 3,
      "orchestrator.lane_policy.min_unique_domains": 3,
      "orchestrator.lane_policy.version": "v2-canary"
    },
    "reason": "canary threshold increase",
    "actor": "ops"
  }' | jq .
```

### C) Loosen thresholds for sparse-topic fallback

```bash
curl -sS -X PATCH "$ORCH_URL/runtime-config" \
  -H "Content-Type: application/json" \
  -d '{
    "patch": {
      "orchestrator.lane_policy.min_source_count": 2,
      "orchestrator.lane_policy.min_unique_domains": 1,
      "orchestrator.lane_policy.version": "v2-sparse-topic"
    },
    "reason": "sparse topic relief tuning",
    "actor": "ops"
  }' | jq .
```

## 7) Inspect Active Runtime State

```bash
curl -sS "$ORCH_URL/runtime-config" | jq '{config_version, owner_overrides, effective_owner_config}'
```

Use this before/after each apply to capture evidence.

## 8) Versioned Rollback

1. Get available versions:

```bash
curl -sS "$ORCH_URL/runtime-config" | jq '.available_versions'
```

2. Roll back to target version:

```bash
curl -sS -X POST "$ORCH_URL/runtime-config/rollback" \
  -H "Content-Type: application/json" \
  -d '{
    "target_version": 0,
    "reason": "rollback lane policy to baseline",
    "actor": "ops"
  }' | jq .
```

## 9) Post-Change Verification

- Confirm runtime state reflects intended keys.
- Confirm orchestrator `/metrics` includes refactor gauges/counters.
- Confirm lane behavior in sampled synthesized records (`synth_metadata.publication`).

Suggested checks:

```bash
curl -sS "$ORCH_URL/runtime-config" | jq '.owner_overrides'
curl -sS "$ORCH_URL/metrics" | grep -E "published_verified_share|published_total_"
```

## 10) Rollback Triggers

Execute rollback immediately when any is true:

- Verified-share drops below agreed floor for sustained window.
- Promotion-failure counters spike above expected baseline.
- Unintended lane behavior appears in sampled records.
- Sev1/Sev2 quality incident is active.

## 11) Evidence to Attach to Ticket

- Validation request/response JSON.
- Apply/rollback response JSON with version IDs.
- Before/after `owner_overrides` snapshots.
- Metrics snapshots for verified share and lane totals.
