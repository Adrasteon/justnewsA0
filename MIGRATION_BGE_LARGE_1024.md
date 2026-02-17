# Migration Report: BGE-Large (1024) & Robust Fact-Checking

**Date**: February 12, 2026  
**Status**: ACTIVE & VERIFIED

This document details the transition from 384-dimensional `all-MiniLM-L6-v2` embeddings to 1024-dimensional `BAAI/bge-large-en-v1.5` embeddings, alongside the implementation of stateful fact-checking.

## 1. Core Changes

### Embedding Model Upgrade
- **New Model**: `BAAI/bge-large-en-v1.5`
- **Dimensions**: 1,024
- **Motivation**: Significantly improved semantic separation for disinformation detection and better clustering across the JustNews pipeline.
- **Config Primary Source**: `system_config.json` -> `database.embedding`.

### Fact-Checker Architecture (Agent 8003)
The fact-checker has been transformed from a stateless search wrapper into a learning agent:
- **Semantic Cache**: Uses ChromaDB to store and retrieve previously verified facts (`fact_checks_vector` collection).
- **Domain Reliability Ledger**: Tracks `proven_count` and `misinfo_count` for every crawled domain in MariaDB (`source_reliability_metrics`).
- **Chain-of-Thought (CoT)**: Forced reasoning path in LLM prompts focusing on source assessment and logic checks.
- **Stateful Persistence**: All checks and evidence are saved to MariaDB (`fact_checks` and `fact_check_evidence`).

## 2. Updated Files

- `config/system_config.json`: Updated `embedding` block to `BAAI/bge-large-en-v1.5` and `1024`.
- `mcp_fact_checker_server/app/service.py`: Core logic for semantic lookup and metric injection.
- `mcp_fact_checker_server/app/models.py`: Added `trusted_sources` and `misleading_sources` fields.
- `mcp_fact_checker_server/app/main.py`: Added `/metrics/domains` endpoint.
- `mcp_fact_checker_server/Dockerfile`: Updated pre-download step to cache the 1024-dim model.
- `.devcontainer/docker-compose.yaml`: Added environment variables and volume mounts to ensure `fact-checker` can access shared `database` logic.

## 3. Data Integrity & Reset

- **Database Truncated**: All test data in `fact_checks`, `articles`, `sources`, and `source_reliability_metrics` has been cleared to avoid dimensional mismatch errors.
- **ChromaDB Scoping**: The system uses scoped names (`articles__BAAI_bge-large-en-v1_5__1024`) to ensure vectors remain compatible with the active model.

## 4. Troubleshooting & Recovery

### Dimensionality Error
If you see `Chroma Error: Dimension mismatch`:
1. Check `system_config.json` for "dimensions": 1024.
2. Ensure the collection name has the `__1024` suffix.
3. If necessary, delete the collection in ChromaDB and let the service recreate it.

### Module Not Found (database)
The `fact-checker` requires the root `database` folder. Ensure `PYTHONPATH` includes `/app` and the volumes are mounted correctly in `docker-compose.yaml`.

### GPU Under Pressure
The embedding model is configured to run on **CPU** by default to leave the RTX 3090's memory available for the primary vLLM inference and LLM reasoning. Do not force embeddings to GPU unless VRAM usage is < 80%.

---
Verified by AI Assistant. All systems operational.
