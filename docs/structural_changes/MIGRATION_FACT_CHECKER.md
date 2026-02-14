# Fact Checker Migration: Shim & Port Change

**Date:** 2026-02-10
**Status:** MIGRATED
**Effected Services:** Fact Checker Agent, Dashboard, Analyst Agent

## Overview

Due to persistent zombie processes and heavy resource consumption in the original Fact Checker implementation (running on port 8003), the service has been migrated to a lightweight **Shim** architecture running on **Port 8018**.

## Changes

### 1. Port Reassignment
- **Old Port:** `8003` (Now deprecated and marked as "ZOMBIE/AVOID" in canonical mapping).
- **New Port:** `8018` (Fact Checker Shim).

### 1.1 Current Runtime Wiring
- Shim endpoint: `http://localhost:8018`
- External backend target: `FACT_CHECKER_EXTERNAL_URL=http://localhost:8003`
- `start_agents_devcontainer.sh` runs the shim on `8018` and forwards `fact_check` requests to the backend on `8003`.

### 2. File Structure
- **Active Implementation:** `agents/fact_checker/shim.py`
  - A lightweight FastAPI proxy that executes real verification paths.
  - `verify_article` now performs DB load → backend verification → DB persistence (`fact_check_status`, `factual_accuracy_score`, `fact_check_details`).
  - Active MCP tool surface is intentionally minimal: `verify_article`, `verify_claim`, `fact_check`.
- **Archived Implementation:** `fact_checker_deprecation_archive/`
  - The original heavy implementation (`main.py`, `fact_checker_engine.py`, etc.) has been moved here.
  - This preserves the logic for future reference or reinstatement without polluting the active namespace.

### 3. Client Updates
- `agents/analyst/audit.py` now defaults to `localhost:8018`.
- Integration tests (`tests/test_integration.py`, etc.) now target `8018`.
- `start_agents_devcontainer.sh` serves the shim on `8018`.

### 4. MCP Bus Recovery Behavior
- MCP Bus startup performs discovery across known ports and can register `fact_checker` on `8018`.
- MCP Bus now supports periodic missing-agent discovery using:
  - `MCP_BUS_MISSING_AGENT_POLL_INTERVAL_SEC` (default `30` seconds; `0` disables polling).

## How to Run

The existing startup script handles the new configuration automatically:

```bash
./start_agents_devcontainer.sh
```

This will launch the `fact_checker` service using `agents.fact_checker.shim:app` on port `8018`.

## Reversion Strategy

If the full Fact Checker logic needs to be restored:
1. Ensure the zombie process on port 8003 is fully killed (requires root/host intervention if stuck in container overlay).
2. Move files from `fact_checker_deprecation_archive/` back to `agents/fact_checker/`.
3. Update `start_agents_devcontainer.sh` to point back to `main:app` and port `8003`.
4. Revert port changes in `audit.py` and tests.
