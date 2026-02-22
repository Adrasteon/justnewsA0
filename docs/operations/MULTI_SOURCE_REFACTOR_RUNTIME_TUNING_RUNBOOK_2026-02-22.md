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
- `orchestrator.lane_policy.min_article_count` (int)
- `orchestrator.lane_policy.min_source_count` (int)
- `orchestrator.lane_policy.min_unique_domains` (int)
- `orchestrator.lane_policy.version` (str)
- `orchestrator.lane_policy.topic_overrides_json` (str/json)

Canonical payload examples are also available directly from the service:

```bash
curl -sS "$ORCH_URL/runtime-config/examples" | jq .
```

## 4) Runtime API Reference

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/runtime-config/examples` | `GET` | Returns canonical lane-policy payload examples |
| `/runtime-config/validate` | `POST` | Validates patch shape and constraints without applying |
| `/runtime-config` | `PATCH` | Applies hot runtime overrides with reason/actor audit |
| `/runtime-config` | `GET` | Shows current overrides, config version, and available rollback versions |
| `/runtime-config/rollback` | `POST` | Rolls back to a target config version |
| `/runtime-config/actuate` | `POST` | Applies tier-scoped runtime patch (`tier1` includes orchestrator keys) |
| `/runtime-config/actuate/rollback` | `POST` | Rolls back by apply version (inverse operation) |

## 5) End-to-End Operator Flow (Validate → Apply → Verify → Rollback)

1. Validate desired patch with `/runtime-config/validate`.
2. Apply patch with `/runtime-config` and record returned `version`.
3. Verify state via `/runtime-config` and signals via `/metrics`.
4. Roll back by version with `/runtime-config/rollback` if quality signals regress.

Example sequence:

```bash
# 1) Validate
curl -sS -X POST "$ORCH_URL/runtime-config/validate" \
  -H "Content-Type: application/json" \
  -d '{"patch":{"orchestrator.lane_policy.enabled":true,"orchestrator.lane_policy.min_source_count":2,"orchestrator.lane_policy.min_unique_domains":2,"orchestrator.lane_policy.version":"v1-dev"}}' | jq .

# 2) Apply
curl -sS -X PATCH "$ORCH_URL/runtime-config" \
  -H "Content-Type: application/json" \
  -d '{"patch":{"orchestrator.lane_policy.enabled":true,"orchestrator.lane_policy.min_source_count":2,"orchestrator.lane_policy.min_unique_domains":2,"orchestrator.lane_policy.version":"v1-dev"},"reason":"dev baseline lane policy","actor":"ops"}' | tee /tmp/lane_apply.json | jq .

# 3) Verify
curl -sS "$ORCH_URL/runtime-config" | jq '{config_version, owner_overrides}'
curl -sS "$ORCH_URL/metrics" | grep -E "published_verified_share|published_total_"

# 4) Roll back (example target)
curl -sS -X POST "$ORCH_URL/runtime-config/rollback" \
  -H "Content-Type: application/json" \
  -d '{"target_version":0,"reason":"rollback after regression","actor":"ops"}' | jq .
```

Rollback guarantee: when a lane-policy key is removed from active runtime overrides, the corresponding orchestrator env mapping is cleared on apply/sync so stale topic overrides do not persist after rollback.

## 6) Validate a Patch Before Apply

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

## 7) Apply Patch (Hot Runtime)

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

## 8) Common Change Recipes

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

## 9) Inspect Active Runtime State

```bash
curl -sS "$ORCH_URL/runtime-config" | jq '{config_version, owner_overrides, effective_owner_config}'
```

Use this before/after each apply to capture evidence.

## 10) Versioned Rollback

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

3. Confirm override removal is reflected in env-backed behavior:

```bash
curl -sS "$ORCH_URL/runtime-config" | jq '.owner_overrides'
```

Expected for full rollback to baseline: `topic_overrides_json` and other removed lane keys are absent from `owner_overrides` and no longer influence lane decisioning.

## 11) Post-Change Verification

- Confirm runtime state reflects intended keys.
- Confirm orchestrator `/metrics` includes refactor gauges/counters.
- Confirm lane behavior in sampled synthesized records (`synth_metadata.publication`).

Suggested checks:

```bash
curl -sS "$ORCH_URL/runtime-config" | jq '.owner_overrides'
curl -sS "$ORCH_URL/metrics" | grep -E "published_verified_share|published_total_"
```

## 12) Rollback Triggers

Execute rollback immediately when any is true:

- Verified-share drops below agreed floor for sustained window.
- Promotion-failure counters spike above expected baseline.
- Unintended lane behavior appears in sampled records.
- Sev1/Sev2 quality incident is active.

## 13) Evidence to Attach to Ticket

- Validation request/response JSON.
- Apply/rollback response JSON with version IDs.
- Before/after `owner_overrides` snapshots.
- Metrics snapshots for verified share and lane totals.

Recommended verification command bundle:

```bash
pytest -q \
  tests/unit/test_workflow_orchestrator_runtime_control_plane_endpoints.py \
  tests/unit/test_workflow_orchestrator_runtime_overrides.py \
  tests/unit/test_workflow_orchestrator_lane_metadata.py
```
