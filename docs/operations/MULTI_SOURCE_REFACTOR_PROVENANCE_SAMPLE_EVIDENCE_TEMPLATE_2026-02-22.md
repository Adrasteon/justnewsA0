# Multi-Source Refactor — Provenance Sample Evidence Template

**Date:** 2026-02-22  
**Scope:** Validate required lane/provenance fields in publication metadata  
**Owner:** `<owner>`  
**Environment:** `<dev|canary|staging>`

## 1) Sample Set Definition

- Query/source used: `<query or extraction command>`
- Time window: `<start/end UTC>`
- Sample size: `<n>`
- Selection method: `<random|stratified|targeted>`

## 2) Required Fields Checklist

For each sampled record, verify these fields are present and semantically valid:

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
| `<id>` | `<value>` | `<value>` | `<value>` | `<value>` | `<value>` | `<value>` | `<value>` | `<value>` | `<value>` | `<pass|fail>` | `<notes>` |

## 4) Raw Sample Artifact

Attach or link raw record payload extract:

```json
[
  {}
]
```

## 5) Aggregated Summary

- Total sampled: `<n>`
- Complete/valid: `<n>`
- Incomplete/invalid: `<n>`
- Completeness rate: `<percent>%`
- Target threshold: `100%` for new records in M2 gate checks

## 6) Exceptions and Remediation

- Exception IDs: `<ids>`
- Root-cause notes: `<notes>`
- Remediation owner: `<owner>`
- ETA: `<date>`

## 7) Sign-off

- Reviewer: `<name>`
- Decision: `<pass|conditional|fail>`
- Timestamp (UTC): `<timestamp>`
