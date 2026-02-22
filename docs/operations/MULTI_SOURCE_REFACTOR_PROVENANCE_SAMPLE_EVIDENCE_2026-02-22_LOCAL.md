# Multi-Source Refactor — Provenance Sample Evidence (Local Harness)

**Date:** 2026-02-22  
**Scope:** Validate required lane/provenance fields using local policy metadata harness  
**Owner:** Refactor implementation stream  
**Environment:** Local harness (`_derive_publication_lane_metadata`)

## 1) Sample Set Definition

- Source/method: Synthetic scenario set evaluated through orchestrator lane metadata function
- Time window: 2026-02-22T16:40:48Z (single capture run)
- Sample size: 5 records
- Selection method: Targeted coverage of `breaking`, `active`, and `background` with mixed source/domain diversity

## 2) Required Fields Checklist

Fields validated per sample record:

- `publication_lane`
- `source_count`
- `unique_domain_count`
- `confidence_tier`
- `provenance_trace_id`
- `decision_reason_codes`
- `policy_version`
- `policy_enabled`
- `policy_thresholds`

## 3) Record-by-Record Evidence

| Record ID | publication_lane | source_count | unique_domain_count | confidence_tier | provenance_trace_id | reason_codes | policy_version | policy_enabled | policy_thresholds | Pass/Fail | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REC-001 | verified_story | 1 | 1 | low | cluster:CL-REC-001:rec-001abcdef012 | meets_multi_source_thresholds | v1-dev | true | {min_article_count:1,min_source_count:1,min_unique_domains:1} | pass | breaking override path |
| REC-002 | verified_story | 2 | 2 | medium | cluster:CL-REC-002:rec-002abcdef012 | meets_multi_source_thresholds | v1-dev | true | {min_article_count:2,min_source_count:2,min_unique_domains:2} | pass | baseline threshold path |
| REC-003 | developing_brief | 1 | 1 | low | cluster:CL-REC-003:rec-003abcdef012 | single_article_cluster, insufficient_source_count, insufficient_domain_diversity | v1-dev | true | {min_article_count:2,min_source_count:2,min_unique_domains:2} | pass | expected fallback path |
| REC-004 | verified_story | 3 | 3 | high | cluster:CL-REC-004:rec-004abcdef012 | meets_multi_source_thresholds | v1-dev | true | {min_article_count:2,min_source_count:2,min_unique_domains:2} | pass | high-confidence path |
| REC-005 | verified_story | 2 | 1 | low | cluster:CL-REC-005:rec-005abcdef012 | meets_multi_source_thresholds | v1-dev | true | {min_article_count:1,min_source_count:1,min_unique_domains:1} | pass | breaking override relaxing domain threshold |

## 4) Raw Sample Artifact

```json
{
  "captured_at_utc": "2026-02-22T16:40:48.848183+00:00",
  "environment": "local_harness",
  "sample_count": 5,
  "policy_env": {
    "MULTI_SOURCE_LANE_POLICY_ENABLED": "1",
    "MULTI_SOURCE_MIN_ARTICLE_COUNT": "2",
    "MULTI_SOURCE_MIN_SOURCE_COUNT": "2",
    "MULTI_SOURCE_MIN_UNIQUE_DOMAINS": "2",
    "MULTI_SOURCE_LANE_POLICY_VERSION": "v1-dev",
    "MULTI_SOURCE_LANE_POLICY_TOPIC_OVERRIDES_JSON": "{\"breaking\":{\"min_article_count\":1,\"min_source_count\":1,\"min_unique_domains\":1}}"
  }
}
```

## 5) Aggregated Summary

- Total sampled: 5
- Complete/valid: 5
- Incomplete/invalid: 0
- Completeness rate: 100%
- Gate note: local harness evidence only; attach dev/staging sampled record export for M2 Ops closure

## 6) Exceptions and Remediation

- Exception IDs: none
- Root-cause notes: n/a
- Remediation owner: n/a
- ETA: n/a

## 7) Sign-off

- Reviewer: Refactor implementation stream
- Decision: conditional (local harness pass; dev/staging sample pending)
- Timestamp (UTC): 2026-02-22T16:40:48Z
