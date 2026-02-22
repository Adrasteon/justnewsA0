# Multi-Source Refactor — Rollback Drill Artifact (Local Harness)

**Date:** 2026-02-22  
**Scope:** Runtime apply/rollback and lane-behavior reversion evidence  
**Owner:** Refactor implementation stream  
**Environment:** Local stubbed orchestrator harness (same harness pattern as control-plane endpoint tests)

## 1) Drill Metadata

- Start Time (UTC): 2026-02-22T16:37:49Z
- Runtime key subset tested: `orchestrator.lane_policy.*`
- Scenario: singleton `breaking` candidate with baseline thresholds `2/2/2`, then topic override apply, then rollback to version `0`

## 2) Baseline Snapshot (Before Apply)

```json
{
  "config_version": 0,
  "owner_overrides": {},
  "available_versions": [0]
}
```

Baseline lane decision (`before`): `developing_brief`

## 3) Apply Payload + Response

### Apply Request

```json
{
  "patch": {
    "orchestrator.lane_policy.enabled": true,
    "orchestrator.lane_policy.topic_overrides_json": "{\"breaking\":{\"min_article_count\":1,\"min_source_count\":1,\"min_unique_domains\":1}}"
  },
  "reason": "rollback drill apply",
  "actor": "ops"
}
```

### Apply Response

```json
{
  "status": "ok",
  "version": 1,
  "previous_version": 0,
  "owner": "workflow_orchestrator",
  "applied": {
    "orchestrator.lane_policy.enabled": true,
    "orchestrator.lane_policy.topic_overrides_json": "{\"breaking\":{\"min_article_count\":1,\"min_source_count\":1,\"min_unique_domains\":1}}"
  },
  "owner_apply_result": {
    "applied": {
      "orchestrator.lane_policy.enabled": true,
      "orchestrator.lane_policy.topic_overrides_json": "{\"breaking\":{\"min_article_count\":1,\"min_source_count\":1,\"min_unique_domains\":1}}"
    },
    "ignored": {}
  }
}
```

### Apply Latency

- Measured latency (seconds): `0.005099`
- Bound: `<= 3.0s`
- Result: `pass`

## 4) Post-Apply Verification

Runtime snapshot (`after_apply_runtime`):

```json
{
  "config_version": 1,
  "owner_overrides": {
    "orchestrator.lane_policy.enabled": true,
    "orchestrator.lane_policy.topic_overrides_json": "{\"breaking\":{\"min_article_count\":1,\"min_source_count\":1,\"min_unique_domains\":1}}"
  }
}
```

Lane decision after apply (`after_apply`): `verified_story`

## 5) Rollback Payload + Response

### Rollback Request

```json
{
  "target_version": 0,
  "reason": "rollback drill revert",
  "actor": "ops"
}
```

### Rollback Response

```json
{
  "status": "ok",
  "version": 2,
  "previous_version": 1,
  "rollback_target_version": 0,
  "owner": "workflow_orchestrator",
  "owner_apply_result": {
    "applied": {},
    "ignored": {}
  }
}
```

### Rollback Latency

- Measured latency (seconds): `0.004928`
- Bound: `<= 3.0s`
- Result: `pass`

## 6) Post-Rollback Verification

Runtime snapshot (`after_rollback_runtime`):

```json
{
  "config_version": 2,
  "owner_overrides": {}
}
```

Lane decision after rollback (`after_rollback`): `developing_brief`

## 7) Outcome

- Reversion path observed end-to-end: `developing_brief -> verified_story -> developing_brief`
- Stale override prevention validated: `owner_overrides` empty post-rollback
- Overall result: `pass` for local harness drill

## 8) Notes

This artifact is local pre-prod evidence captured via the same stubbed integration harness used in unit-level control-plane endpoint tests. Attach a real dev environment run artifact to close the M2 Ops sign-off item.
