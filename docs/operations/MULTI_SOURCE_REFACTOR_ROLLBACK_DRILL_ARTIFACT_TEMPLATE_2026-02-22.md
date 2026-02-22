# Multi-Source Refactor — Rollback Drill Artifact Template

**Date:** 2026-02-22  
**Scope:** Capture evidence for runtime apply/rollback drill and behavior reversion  
**Owner:** `<owner>`  
**Environment:** `<dev|canary|staging>`

## 1) Drill Metadata

- Ticket/Issue: `<link>`
- Operator: `<name>`
- Start Time (UTC): `<timestamp>`
- End Time (UTC): `<timestamp>`
- Orchestrator Base URL: `<url>`
- Runtime key subset tested: `orchestrator.lane_policy.*`

## 2) Baseline Snapshot (Before Apply)

### 2.1 Runtime Config

```bash
curl -sS "$ORCH_URL/runtime-config" | jq '{config_version, owner_overrides, available_versions}'
```

Paste output (or link artifact):

```json
{}
```

### 2.2 Baseline Lane Decision Sample

- Scenario ID: `<id>`
- Expected baseline lane: `developing_brief`

```json
{}
```

## 3) Apply Payload + Response

### 3.1 Apply Request

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

### 3.2 Apply Response

```json
{}
```

### 3.3 Apply Latency

- Measured latency (seconds): `<value>`
- SLO bound used: `<= 3.0s` (or env-specific bound)
- Pass/Fail: `<pass|fail>`

## 4) Post-Apply Verification

### 4.1 Runtime Snapshot

```json
{}
```

### 4.2 Lane Behavior After Apply

- Expected lane: `verified_story`

```json
{}
```

### 4.3 Metrics Snapshot (Optional but recommended)

```bash
curl -sS "$ORCH_URL/metrics" | grep -E "published_verified_share|published_total_"
```

Captured output/link: `<artifact link>`

## 5) Rollback Payload + Response

### 5.1 Rollback Request

```json
{
  "target_version": 0,
  "reason": "rollback drill revert",
  "actor": "ops"
}
```

### 5.2 Rollback Response

```json
{}
```

### 5.3 Rollback Latency

- Measured latency (seconds): `<value>`
- SLO bound used: `<= 3.0s` (or env-specific bound)
- Pass/Fail: `<pass|fail>`

## 6) Post-Rollback Verification

### 6.1 Runtime Snapshot (No stale override)

- Confirm removed keys are absent from `owner_overrides`.

```json
{}
```

### 6.2 Lane Behavior Reversion

- Expected lane: `developing_brief`

```json
{}
```

## 7) Outcome

- Drill result: `<pass|fail>`
- Issues found: `<none|summary>`
- Follow-up actions: `<actions>`
- Sign-off: `<name + timestamp>`
