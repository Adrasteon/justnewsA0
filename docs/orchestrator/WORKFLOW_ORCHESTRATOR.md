# Workflow Orchestrator

The **Workflow Orchestrator** (`agents/workflow_orchestrator`) is the central brain of the JustNews pipelne. Unlike the GPU Orchestrator (which manages hardware resources), the Workflow Orchestrator manages the **business logic** of moving news data through the pipeline.

## Architecture

The Orchestrator runs a continuous loop that executes a series of **Policies**. Each policy looks for items in the database that match a specific condition (e.g., "Article is analyzed but not summarized") and triggers an agent action (e.g., "Call Synthesizer").

### Core Policies

1.  **IngestionToAnalysisPolicy**: Picks up new raw articles and sends them to the Analyst.
2.  **AnalysisToEmbeddingPolicy**: Sends analyzed articles to Memory for embedding/indexing.
3.  **AnalysisToSummaryPolicy**: Sends analyzed articles to Synthesizer for individual summarization.
4.  **SummaryToFactCheckPolicy**: Triggers Fact Checker (currently a stub/pass-through in some configs).
5.  **FactCheckToClusterPolicy**: Groups verified stories into Clusters.
6.  **ClusterToSynthesisPolicy**: The final step. Takes a cluster of articles and asks the Synthesizer to write a full report.

## Heavy Cluster Management

Some news clusters can become extremely large (20-100+ articles). Processing these requires significant GPU time (~2-5 minutes) and context window management.

### The Problem
During peak load, a single massive cluster can block the pipeline or trigger timeouts, causing the Orchestrator to retry infinitely and clog the system.

### HeavyClusterRetryPolicy

To solve this, we introduced the `HeavyClusterRetryPolicy` (v3.0).

**How it works:**
1.  **Detection**: If `ClusterToSynthesisPolicy` encounters a timeout (>300s) or error, it logs the Cluster ID to `heavy_clusters.log` in the root directory and **moves on**.
2.  **Deferral**: The cluster is skipped during normal processing rounds.
3.  **Retry**: The `HeavyClusterRetryPolicy` runs continuously but only activates when:
    *   **System Load is Low**: Load average < 6.0 (on 16-core system).
    *   **Queue is Empty**: Fewer than 10 pending regular items.
    *   **Log Exists**: Entries are present in `heavy_clusters.log`.

**Manual Intervention**:
If automatic retry fails repeatedly, you can inspect `heavy_clusters.log`.
To force a retry manually, you can use the diagnostic script:
```bash
python scripts/analyze_cluster.py --cluster-id CL-XXXX --force
```
(Note: `analyze_cluster.py` needs to be implemented/adapted if specific debugging is required).

## Configuration

Polices are loaded in `agents/workflow_orchestrator/engine.py`.
Timeouts are configured in `agents/workflow_orchestrator/policies.py` (Default: 300s).
