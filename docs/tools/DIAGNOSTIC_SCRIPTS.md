# Diagnostic Tools

This directory contains utility scripts to help operators diagnose pipeline issues, check progress, and debug agent interactions.

## Core Scripts

### `check_cluster_counts.py`
**Purpose**: Primary status dashboard for the "Cluster Synthesis" phase.
**Location**: Root directory.
**Usage**:
```bash
python check_cluster_counts.py
```
**Output**:
- Total Clusters found.
- Completed (Synthesized) count.
- Remaining count.
- Statistics on remaining backlog (Avg/Max cluster size).

Use this to track the progress of a long-running batch job.

### `diagnose_workflow.py`
**Purpose**: Comprehensive health check of the `workflow_orchestrator`.
**Location**: Root directory.
**Usage**:
```bash
python diagnose_workflow.py
```
**Functionality**:
- Checks DB connectivity.
- Verifies if Orchestrator process is running.
- Checks `heavy_clusters.log` for stuck items.
- Samples recent logs for errors.

### `debug_metrics.py`
**Purpose**: Low-level metrics validation.
**Location**: Root directory.
**Usage**:
```bash
python debug_metrics.py
```
**Functionality**:
- Connects to Prometheus/Grafana ports to ensure metrics are being scraped.
- Debugs `common/metrics.py` integration.

### `debug_vllm_auth.py`
**Purpose**: Verify connectivity to the VLLM inference engine.
**Location**: Root directory.
**Usage**:
```bash
python debug_vllm_auth.py
```
**Functionality**:
- Sends a test prompt to `localhost:8010/v1/chat/completions`.
- Validates that API Keys (or lack thereof) are configured correctly.
- Useful if you see `401 Unauthorized` in logs.

## Log Files

- **`heavy_clusters.log`**: JSONL file containing clusters that timed out or failed. Processed automatically by `HeavyClusterRetryPolicy` when system is idle.
