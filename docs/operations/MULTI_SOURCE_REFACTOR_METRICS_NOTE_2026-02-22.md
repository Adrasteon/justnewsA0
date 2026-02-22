# Multi-Source Refactor Metrics Note

**Date:** 2026-02-22  
**Scope:** M1 Instrumentation verification for workflow orchestrator  
**Owner:** Refactor implementation team

## 1) Metric Name Mapping (Current Implementation)

The orchestrator currently emits refactor metrics via `JustNewsMetrics` custom metric helpers, which materialize as `justnews_custom_*` series.

### Published Lane Totals

- `published_total_verified_story` → `justnews_custom_counter_published_total_verified_story`
- `published_total_developing_brief` → `justnews_custom_counter_published_total_developing_brief`

### Lane Quality Gauges

- `published_verified_share` → `justnews_custom_gauge_published_verified_share`
- `median_unique_domains_per_story` → `justnews_custom_gauge_median_unique_domains_per_story`

### Promotion Failure Counters (Reason-coded)

- `cluster_promotion_failures_insufficient_source_count` →
  `justnews_custom_counter_cluster_promotion_failures_insufficient_source_count`
- `cluster_promotion_failures_insufficient_domain_diversity` →
  `justnews_custom_counter_cluster_promotion_failures_insufficient_domain_diversity`

### Conversion Counter

- `singleton_to_verified_conversion_total` →
  `justnews_custom_counter_singleton_to_verified_conversion_total`

## 2) PromQL Queries (Ready to Use)

> Replace `agent="workflow_orchestrator"` selector as needed.

### Lane Throughput (rate)

```promql
sum(rate(justnews_custom_counter_published_total_verified_story_total{agent="workflow_orchestrator"}[5m]))
```

```promql
sum(rate(justnews_custom_counter_published_total_developing_brief_total{agent="workflow_orchestrator"}[5m]))
```

### Verified Share (instant)

```promql
max(justnews_custom_gauge_published_verified_share{agent="workflow_orchestrator"})
```

### Median Unique Domains (instant)

```promql
max(justnews_custom_gauge_median_unique_domains_per_story{agent="workflow_orchestrator"})
```

### Promotion Failures by Reason (rate)

```promql
sum by (__name__) (
  rate({__name__=~"justnews_custom_counter_cluster_promotion_failures_.*_total",agent="workflow_orchestrator"}[5m])
)
```

### Singleton → Verified Conversion (rate)

```promql
sum(rate(justnews_custom_counter_singleton_to_verified_conversion_total_total{agent="workflow_orchestrator"}[15m]))
```

## 3) Validation Checklist

- [ ] `/metrics` endpoint on workflow orchestrator is reachable.
- [ ] Both lane counters increase during synthesis/upsert activity.
- [ ] Verified share gauge remains within `[0,1]`.
- [ ] Failure counters increase only for `developing_brief` decisions.
- [ ] Conversion counter increments only on `developing_brief -> verified_story` transitions.

## 3.1) Automated Contract Coverage (Current)

The `/metrics` contract and control-plane behavior are now covered by targeted tests:

- `tests/unit/test_workflow_orchestrator_runtime_control_plane_endpoints.py`
  - `test_metrics_endpoint_exposes_lane_observability_contract`
  - verifies required metric series are present after lane/failure/conversion emission.
- `tests/unit/test_workflow_orchestrator_lane_metadata.py`
  - verifies lane metric emission semantics and reason-coded failure counters.

Focused local validation command:

```bash
pytest -q \
  tests/unit/test_workflow_orchestrator_runtime_control_plane_endpoints.py \
  tests/unit/test_workflow_orchestrator_runtime_examples.py \
  tests/unit/test_workflow_orchestrator_runtime_examples_endpoint.py \
  tests/unit/test_workflow_orchestrator_runtime_overrides.py \
  tests/unit/test_workflow_orchestrator_lane_metadata.py
```

Latest focused result in this refactor stream: `22 passed` (then `24 passed` after rollback env-clearing fix additions).

## 3.2) CI Enforcement

Runtime control-plane + metrics contract coverage is enforced in CI workflow:

- `.github/workflows/workflow-orchestrator-control-plane-tests.yml`

This workflow runs on `push` and `pull_request` for orchestrator/runtime test paths and executes the focused suite including the metrics endpoint contract test.

## 4) Alert Starter Thresholds (Initial)

- **Low verified share**: `published_verified_share < 0.30` for 30m
- **Failure spike**: promotion failure rate increases > 2x 24h baseline
- **No conversions**: conversion rate == 0 over 24h while developing briefs are being produced

## 5) Rollback Signals

If refactor instrumentation is rolled back, expect:

- Refactor-specific `justnews_custom_*` metrics above stop updating.
- New lane metadata fields in living-story metadata stop being newly populated.
- Existing historical series remain in Prometheus until retention expiry.
