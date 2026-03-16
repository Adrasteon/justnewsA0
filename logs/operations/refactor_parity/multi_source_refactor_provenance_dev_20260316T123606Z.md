# Multi-Source Refactor - Provenance Sample Evidence

Date: 2026-03-16T12:36:06.102556Z
Environment: dev
Owner: Ops/QA

## 1) Sample Set Definition
- Query/source used: SELECT story_id, updated_at, synth_metadata FROM synthesized_articles WHERE is_published = 1 ORDER BY updated_at DESC LIMIT N
- Time window: 2026-03-15 18:17:44 to 2026-03-15 18:20:51
- Sample size: 10
- Selection method: most-recent-published

## 2) Required Fields Checklist
- publication_lane
- source_count
- unique_domain_count
- confidence_tier
- provenance_trace_id
- decision_reason_codes
- policy_version
- policy_enabled
- policy_thresholds

## 3) Record-by-Record Evidence
| Record ID | publication_lane | source_count | unique_domain_count | confidence_tier | provenance_trace_id | reason_codes | policy_version | policy_enabled | policy_thresholds | Pass/Fail | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STORY-7765b86a | verified_story | 1 | 1 | low | cluster:CL-c4c93b74:123a999feadac2aa | single_article_cluster,insufficient_source_count,insufficient_domain_diversity,lane2_disabled_bounced_to_lane1 | v-focus-lane1 | True | {"min_article_count": 2, "min_source_count": 2, "min_unique_domains": 2} | pass | ok |
| STORY-89d175b5 | verified_story | 1 | 1 | low | cluster:CL-50a9984b:892cdff2d3d3f619 | single_article_cluster,insufficient_source_count,insufficient_domain_diversity,lane2_disabled_bounced_to_lane1 | v-focus-lane1 | True | {"min_article_count": 2, "min_source_count": 2, "min_unique_domains": 2} | pass | ok |
| STORY-a218cd51 | verified_story | 1 | 1 | low | cluster:CL-72192f33:fd36d80fe16f0daa | single_article_cluster,insufficient_source_count,insufficient_domain_diversity,lane2_disabled_bounced_to_lane1 | v-focus-lane1 | True | {"min_article_count": 2, "min_source_count": 2, "min_unique_domains": 2} | pass | ok |
| STORY-4f3b2170 | verified_story | 1 | 1 | low | cluster:CL-fd493be5:d4e2501734145318 | single_article_cluster,insufficient_source_count,insufficient_domain_diversity,lane2_disabled_bounced_to_lane1 | v-focus-lane1 | True | {"min_article_count": 2, "min_source_count": 2, "min_unique_domains": 2} | pass | ok |
| STORY-7d7a3b57 | verified_story | 1 | 1 | low | cluster:CL-350606a1:ec8b19be39eb32ee | single_article_cluster,insufficient_source_count,insufficient_domain_diversity,lane2_disabled_bounced_to_lane1 | v-focus-lane1 | True | {"min_article_count": 2, "min_source_count": 2, "min_unique_domains": 2} | pass | ok |
| STORY-86d7d91b | verified_story | 1 | 1 | low | cluster:CL-f875bc62:a2730bca63eff586 | single_article_cluster,insufficient_source_count,insufficient_domain_diversity,lane2_disabled_bounced_to_lane1 | v-focus-lane1 | True | {"min_article_count": 2, "min_source_count": 2, "min_unique_domains": 2} | pass | ok |
| STORY-07a760e5 | verified_story | 1 | 1 | low | cluster:CL-0ced9716:b7d7b92afabba562 | single_article_cluster,insufficient_source_count,insufficient_domain_diversity,lane2_disabled_bounced_to_lane1 | v-focus-lane1 | True | {"min_article_count": 2, "min_source_count": 2, "min_unique_domains": 2} | pass | ok |
| STORY-7bddad82 | verified_story | 1 | 1 | low | cluster:CL-0991e222:c13b38201136ca38 | single_article_cluster,insufficient_source_count,insufficient_domain_diversity,lane2_disabled_bounced_to_lane1 | v-focus-lane1 | True | {"min_article_count": 2, "min_source_count": 2, "min_unique_domains": 2} | pass | ok |
| STORY-ed7dbb69 | verified_story | 1 | 1 | low | cluster:CL-557e75bd:c43804ea600ae2f1 | single_article_cluster,insufficient_source_count,insufficient_domain_diversity,lane2_disabled_bounced_to_lane1 | v-focus-lane1 | True | {"min_article_count": 2, "min_source_count": 2, "min_unique_domains": 2} | pass | ok |
| STORY-0a33b239 | verified_story | 1 | 1 | low | cluster:CL-f8e43980:b06fa6f096dd29d0 | single_article_cluster,insufficient_source_count,insufficient_domain_diversity,lane2_disabled_bounced_to_lane1 | v-focus-lane1 | True | {"min_article_count": 2, "min_source_count": 2, "min_unique_domains": 2} | pass | ok |

## 4) Raw Sample Artifact
```json
[
  {
    "confidence_tier": "low",
    "decision_reason_codes": [
      "single_article_cluster",
      "insufficient_source_count",
      "insufficient_domain_diversity",
      "lane2_disabled_bounced_to_lane1"
    ],
    "missing_fields": [],
    "pass": true,
    "policy_enabled": true,
    "policy_thresholds": {
      "min_article_count": 2,
      "min_source_count": 2,
      "min_unique_domains": 2
    },
    "policy_version": "v-focus-lane1",
    "provenance_trace_id": "cluster:CL-c4c93b74:123a999feadac2aa",
    "publication_lane": "verified_story",
    "record_id": "STORY-7765b86a",
    "source_count": 1,
    "unique_domain_count": 1,
    "updated_at": "2026-03-15 18:20:51"
  },
  {
    "confidence_tier": "low",
    "decision_reason_codes": [
      "single_article_cluster",
      "insufficient_source_count",
      "insufficient_domain_diversity",
      "lane2_disabled_bounced_to_lane1"
    ],
    "missing_fields": [],
    "pass": true,
    "policy_enabled": true,
    "policy_thresholds": {
      "min_article_count": 2,
      "min_source_count": 2,
      "min_unique_domains": 2
    },
    "policy_version": "v-focus-lane1",
    "provenance_trace_id": "cluster:CL-50a9984b:892cdff2d3d3f619",
    "publication_lane": "verified_story",
    "record_id": "STORY-89d175b5",
    "source_count": 1,
    "unique_domain_count": 1,
    "updated_at": "2026-03-15 18:20:34"
  },
  {
    "confidence_tier": "low",
    "decision_reason_codes": [
      "single_article_cluster",
      "insufficient_source_count",
      "insufficient_domain_diversity",
      "lane2_disabled_bounced_to_lane1"
    ],
    "missing_fields": [],
    "pass": true,
    "policy_enabled": true,
    "policy_thresholds": {
      "min_article_count": 2,
      "min_source_count": 2,
      "min_unique_domains": 2
    },
    "policy_version": "v-focus-lane1",
    "provenance_trace_id": "cluster:CL-72192f33:fd36d80fe16f0daa",
    "publication_lane": "verified_story",
    "record_id": "STORY-a218cd51",
    "source_count": 1,
    "unique_domain_count": 1,
    "updated_at": "2026-03-15 18:20:34"
  },
  {
    "confidence_tier": "low",
    "decision_reason_codes": [
      "single_article_cluster",
      "insufficient_source_count",
      "insufficient_domain_diversity",
      "lane2_disabled_bounced_to_lane1"
    ],
    "missing_fields": [],
    "pass": true,
    "policy_enabled": true,
    "policy_thresholds": {
      "min_article_count": 2,
      "min_source_count": 2,
      "min_unique_domains": 2
    },
    "policy_version": "v-focus-lane1",
    "provenance_trace_id": "cluster:CL-fd493be5:d4e2501734145318",
    "publication_lane": "verified_story",
    "record_id": "STORY-4f3b2170",
    "source_count": 1,
    "unique_domain_count": 1,
    "updated_at": "2026-03-15 18:20:33"
  },
  {
    "confidence_tier": "low",
    "decision_reason_codes": [
      "single_article_cluster",
      "insufficient_source_count",
      "insufficient_domain_diversity",
      "lane2_disabled_bounced_to_lane1"
    ],
    "missing_fields": [],
    "pass": true,
    "policy_enabled": true,
    "policy_thresholds": {
      "min_article_count": 2,
      "min_source_count": 2,
      "min_unique_domains": 2
    },
    "policy_version": "v-focus-lane1",
    "provenance_trace_id": "cluster:CL-350606a1:ec8b19be39eb32ee",
    "publication_lane": "verified_story",
    "record_id": "STORY-7d7a3b57",
    "source_count": 1,
    "unique_domain_count": 1,
    "updated_at": "2026-03-15 18:20:32"
  },
  {
    "confidence_tier": "low",
    "decision_reason_codes": [
      "single_article_cluster",
      "insufficient_source_count",
      "insufficient_domain_diversity",
      "lane2_disabled_bounced_to_lane1"
    ],
    "missing_fields": [],
    "pass": true,
    "policy_enabled": true,
    "policy_thresholds": {
      "min_article_count": 2,
      "min_source_count": 2,
      "min_unique_domains": 2
    },
    "policy_version": "v-focus-lane1",
    "provenance_trace_id": "cluster:CL-f875bc62:a2730bca63eff586",
    "publication_lane": "verified_story",
    "record_id": "STORY-86d7d91b",
    "source_count": 1,
    "unique_domain_count": 1,
    "updated_at": "2026-03-15 18:19:18"
  },
  {
    "confidence_tier": "low",
    "decision_reason_codes": [
      "single_article_cluster",
      "insufficient_source_count",
      "insufficient_domain_diversity",
      "lane2_disabled_bounced_to_lane1"
    ],
    "missing_fields": [],
    "pass": true,
    "policy_enabled": true,
    "policy_thresholds": {
      "min_article_count": 2,
      "min_source_count": 2,
      "min_unique_domains": 2
    },
    "policy_version": "v-focus-lane1",
    "provenance_trace_id": "cluster:CL-0ced9716:b7d7b92afabba562",
    "publication_lane": "verified_story",
    "record_id": "STORY-07a760e5",
    "source_count": 1,
    "unique_domain_count": 1,
    "updated_at": "2026-03-15 18:19:18"
  },
  {
    "confidence_tier": "low",
    "decision_reason_codes": [
      "single_article_cluster",
      "insufficient_source_count",
      "insufficient_domain_diversity",
      "lane2_disabled_bounced_to_lane1"
    ],
    "missing_fields": [],
    "pass": true,
    "policy_enabled": true,
    "policy_thresholds": {
      "min_article_count": 2,
      "min_source_count": 2,
      "min_unique_domains": 2
    },
    "policy_version": "v-focus-lane1",
    "provenance_trace_id": "cluster:CL-0991e222:c13b38201136ca38",
    "publication_lane": "verified_story",
    "record_id": "STORY-7bddad82",
    "source_count": 1,
    "unique_domain_count": 1,
    "updated_at": "2026-03-15 18:19:17"
  },
  {
    "confidence_tier": "low",
    "decision_reason_codes": [
      "single_article_cluster",
      "insufficient_source_count",
      "insufficient_domain_diversity",
      "lane2_disabled_bounced_to_lane1"
    ],
    "missing_fields": [],
    "pass": true,
    "policy_enabled": true,
    "policy_thresholds": {
      "min_article_count": 2,
      "min_source_count": 2,
      "min_unique_domains": 2
    },
    "policy_version": "v-focus-lane1",
    "provenance_trace_id": "cluster:CL-557e75bd:c43804ea600ae2f1",
    "publication_lane": "verified_story",
    "record_id": "STORY-ed7dbb69",
    "source_count": 1,
    "unique_domain_count": 1,
    "updated_at": "2026-03-15 18:19:17"
  },
  {
    "confidence_tier": "low",
    "decision_reason_codes": [
      "single_article_cluster",
      "insufficient_source_count",
      "insufficient_domain_diversity",
      "lane2_disabled_bounced_to_lane1"
    ],
    "missing_fields": [],
    "pass": true,
    "policy_enabled": true,
    "policy_thresholds": {
      "min_article_count": 2,
      "min_source_count": 2,
      "min_unique_domains": 2
    },
    "policy_version": "v-focus-lane1",
    "provenance_trace_id": "cluster:CL-f8e43980:b06fa6f096dd29d0",
    "publication_lane": "verified_story",
    "record_id": "STORY-0a33b239",
    "source_count": 1,
    "unique_domain_count": 1,
    "updated_at": "2026-03-15 18:17:44"
  }
]
```

## 5) Aggregated Summary
- Total sampled: 10
- Complete/valid: 10
- Incomplete/invalid: 0
- Completeness rate: 100.00%
- Target threshold: 100% for new records in M2 gate checks

## 6) Exceptions and Remediation
- Exception IDs: none
- Root-cause notes: n/a
- Remediation owner: n/a
- ETA: n/a

## 7) Sign-off
- Reviewer: Ops/QA
- Decision: pass
- Timestamp (UTC): 2026-03-16T12:36:06.102556Z
