# JustNews System Setup - Hardware Safety & Constraints

This document outlines the hardware safety constraints and system memory requirements enforced by the central startup script (`infrastructure/systemd/scripts/enable_all.sh`).

## Overview

To ensure the stability of the development environment (which often runs heavy IDEs like VS Code alongside the agent stack) and to protect hardware longevity, we enforce strict limits at startup.

## 1. GPU Power Limit

*   **Enforcement:** Hard limit of **300W** (configurable in script, defaulted to protect RTX 3090/4090 class cards from spikes).
*   **Mechanism:** `nvidia-smi -pl 300` is executed on all available GPUs during startup.
*   **Why?** Prevents thermal throttling overlap and reduces risk of power supply spikes during heavy inference loads (e.g., vLLM batch processing).

## 2. System Memory (OOM Protection)

*   **Enforcement:** Minimum **4GB (4096MB)** of *available* system RAM is required to start the stack.
*   **Mechanism:** Checks `/proc/meminfo` before launching agents.
*   **Why?** The JustNews agent stack + vLLM can consume 40GB+ of RAM quickly. If system RAM drops too low, the Linux OOM killer is likely to terminate the VS Code Remote Server or the DB connection, causing data loss or work interruption.
*   **Behavior:** The script will warn loudly (and pause) if memory is critical but will currently allow you to proceed with a warning.

## 3. Context Window Limits (vLLM)

*   **Enforcement:** vLLM server configuration.
*   **Tool:** `scripts/perf/stress_test_context_window.py`
*   **Usage:**
    ```bash
    # Test your GPU's capacity to handle large contexts
    python scripts/perf/stress_test_context_window.py --max 16000 --step 1000
    ```
*   **Current Production Setting:**
    *   **Model:** Qwen/Qwen2.5-14B-Instruct-AWQ
    *   **Max Limit:** 8192 tokens
    *   **GPU Utilization:** 0.75 (reserved buffer for adapters/overhead)

## Troubleshooting

If `enable_all.sh start` fails or hangs:

1.  **Check Power Limit:**
    ```bash
    nvidia-smi -q -d POWER
    ```
2.  **Check Memory:**
    ```bash
    free -h
    ```
3.  **Run Stress Test:** (If suspecting VRAM instability)
    ```bash
    python scripts/perf/stress_test_context_window.py
    ```
