# Monitoring Scripts Reference

This guide documents the script-level monitoring checks used for day-to-day JustNews operations.

## Scope

These scripts are lightweight operational diagnostics. They are not replacements for full integration tests.

## Prerequisites

Run from /app so relative imports and env loading behave consistently:

```bash
cd /app
set -a && source /app/global.env && set +a
```

Then run a script with the project venv (path depends on environment):

```bash
/app/.venv/bin/python <script_name>.py
# or, in devcontainer layouts that place the env under /deps:
/deps/.venv/bin/python <script_name>.py
```

## Core Workflow Monitoring

| Script | Purpose | Primary Signals | When To Use |
|---|---|---|---|
| [check_workflow_progress.py](../../check_workflow_progress.py) | Fast workflow snapshot for crawl/ingest/analyze/embed/fact-check progression. | `articles` totals, `analyzed`, `embedded`, `fact_check_status`, `fact_check_details`, 60m deltas, and recent row sample. | Every 5-15 minutes during active pipeline runs. |
| [final_pipeline_status.py](../../final_pipeline_status.py) | Final run summary by phase for reporting and gate decisions. | Crawl task proxy counts, source coverage, ingestion conversion, embedding totals, fact-check totals and 60m activity, schema-readiness signal. | End of each monitoring window or before keep/rollback decisions. |
| [full_pipeline_check.py](../../full_pipeline_check.py) | One-screen cross-phase summary including synthesis and publication progression. | `analyzed`, `summary`, fact-check status breakdown, synthesis/publication counts, 60m fact-check activity. | Quick status before/after runtime tuning changes. |

## System and Service Health

| Script | Purpose | Primary Signals | When To Use |
|---|---|---|---|
| [canonical_status_check.py](../../canonical_status_check.py) | Canonical fast health gate for infrastructure and key dependencies. | Container/port checks, MariaDB connectivity, Chroma API, vLLM API/model, schema/migration checks, environment checks, exit code status. | First check after startup, restart, or deployment changes. |
| [check_db_status_v2.py](../../check_db_status_v2.py) | Combined MariaDB + Chroma inventory and counts. | Table list/counts, source/article totals, Chroma heartbeat, collection list and counts. | Validate both storage backends from one command. |
| [check_mariadb_status.py](../../check_mariadb_status.py) | Minimal MariaDB pulse for crawler jobs and article totals. | `crawler_jobs` status distribution, article count. | Quick DB sanity probe when queue appears stuck. |
| [check_db_status.py](../../check_db_status.py) | Legacy DB structure/status check with table column introspection. | `articles` count, table columns, analyzed/status distribution if available. | Backward-compat schema debugging. |

## Crawl and Ingestion Diagnostics

| Script | Purpose | Primary Signals | When To Use |
|---|---|---|---|
| [check_crawl_queue.py](../../check_crawl_queue.py) | Inspect latest crawler jobs plus current source/article coverage. | Latest jobs with dynamic columns, active job count, source crawl progress, source coverage in articles. | Diagnose crawl throughput or queue stalling. |
| [check_latest_ingestion.py](../../check_latest_ingestion.py) | Verify recency of ingestion writes. | `MAX(articles.created_at)` vs current system time. | Confirm ingestion freshness in near-real time. |

## Embedding and Vector Diagnostics

| Script | Purpose | Primary Signals | When To Use |
|---|---|---|---|
| [check_embedding_loop.py](../../check_embedding_loop.py) | Embedding backlog check and oldest pending sample. | `articles` where `analyzed=1 AND embedded=0/1`, oldest pending records. | Determine whether embedding loop is draining or stuck. |
| [check_chroma_final.py](../../check_chroma_final.py) | Chroma collection inventory with dimensions and metadata. | Collection names, counts, metadata, sample embedding dimensions. | Validate vector store state after embedding changes. |
| [check_chroma_detailed.py](../../check_chroma_detailed.py) | Chroma target-collection presence check. | Tenant collections and explicit checks for expected collection names. | Confirm expected collections are present in target tenant. |
| [check_collections_detail.py](../../check_collections_detail.py) | Compact Chroma list/count/metadata inspection. | Collection names, counts, metadata. | Fast manual verification of vector collections. |

## Clustering and Synthesis Readiness

| Script | Purpose | Primary Signals | When To Use |
|---|---|---|---|
| [check_clustering_status.py](../../check_clustering_status.py) | Cluster readiness from fact-checked but unclustered article pool. | Ready-for-clustering count over configurable date range, clustered-but-unsynthesized count. | Check if clustering input lane is fed correctly. |
| [check_clustering_progress.py](../../check_clustering_progress.py) | Distribution and size profile of generated clusters. | Clustered article count, pending count, top cluster sizes, singleton/multi-article split. | Inspect clustering quality and shape. |
| [check_cluster_counts.py](../../check_cluster_counts.py) | End-to-end cluster completion delta to synthesis. | Unique cluster IDs in articles vs `synthesized_articles`, remaining clusters, size stats. | Quantify remaining synthesis backlog by cluster. |
| [check_ready_clusters.py](../../check_ready_clusters.py) | Maturity-window readiness check for unsynthesized clusters. | Per-cluster count, newest-article age, READY/WAITING status under 20-minute maturity heuristic. | Triage whether clusters are waiting on age threshold or volume. |
| [check_ready_clusters_v2.py](../../check_ready_clusters_v2.py) | Debug-focused readiness variant with target cluster tracing. | Same as above plus explicit debug output for target cluster IDs. | Deep dive on specific cluster anomalies. |

## Utility File-Based Status Scripts

| Script | Purpose | Output Artifact | Notes |
|---|---|---|---|
| [check_count.py](../../check_count.py) | Writes total article count to a local file. | [current_count.txt](../../current_count.txt) | Very lightweight external polling hook. |
| [check_status_file.py](../../check_status_file.py) | Writes analyzed count to a local file. | [status.txt](../../status.txt) | Lightweight compatibility status output. |

## Canary Scorecards

| Script | Purpose | Primary Signals | When To Use |
|---|---|---|---|
| [scripts/ops/canary_scorecard.py](../../scripts/ops/canary_scorecard.py) | Summarize gate checkpoint deltas and emit GO/NO_GO verdicts. | `analyzed_delta`, `backlog_drain`, analyst request delta, MySQL disconnect delta, analyst 500 delta, scheduler mode snapshot. | After each 15-minute or 60-minute canary window to standardize promotion decisions. |

Example:

```bash
cd /app
/deps/.venv/bin/python scripts/ops/canary_scorecard.py --dir /tmp/aw4_gate --start baseline --end t15m
```

## Metric Interpretation Notes

1. For fact-check progression, article-level fields in `articles` are the authoritative operational signal:
- `fact_check_status`
- `fact_check_details`

2. The `fact_checks` table should be treated as legacy/reference in current shim flow. It can remain flat while article-level fact-check progression continues.

3. For gate windows, use both totals and 60-minute deltas. A flat total can be expected if the monitored metric is not the active write path.

## Recommended Operational Sequence

1. Run [canonical_status_check.py](../../canonical_status_check.py) after startup/restart.
2. Use [check_workflow_progress.py](../../check_workflow_progress.py) for rolling snapshots.
3. Use [check_crawl_queue.py](../../check_crawl_queue.py) when crawl input appears slow.
4. Use [check_embedding_loop.py](../../check_embedding_loop.py) and Chroma checks for vector-path triage.
5. Use clustering checks when synthesis throughput is lagging.
6. End each monitoring window with [final_pipeline_status.py](../../final_pipeline_status.py).
