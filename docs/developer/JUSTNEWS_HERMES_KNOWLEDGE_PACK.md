# JustNews Hermes Knowledge Pack

Purpose:
- Provide a compact, durable knowledge layer Hermes can load repeatedly.
- Keep architecture facts stable and low-noise.

How to use:
- Read this file at session start before major implementation tasks.
- Update only when architecture or operational truth changes.
- Prefer short factual bullets over prose.

## Core System Shape
- JustNews is a multi-agent news workflow with crawler, triage, analysis, fact-checking, synthesis, and editorial stages.
- Runtime orchestration and overrides are controlled via runtime config state and runtime config APIs.
- Retrieval quality depends on local index freshness in .cache/code_index and telemetry in run/indexing_telemetry.jsonl.

## Durable Invariants
- Session start should bootstrap index context and validate autoupdate status.
- Index query should run before broad workspace scans for discovery tasks.
- Production-like behavior should be validated with focused tests when full suite collection is known to fail from legacy dependencies.
- Configuration and secrets are split: structural config in config files, secrets in environment files.

## Retrieval and Indexing Facts
- Build index: make index-build
- Query index: make index-query QUERY='your query'
- Bootstrap context: make index-bootstrap
- Telemetry summary: make index-telemetry-summary
- If systemd user bus is unavailable in container, daemon fallback is expected for autoupdate.

## Operations Facts
- Gateway and long-lived services may require background process fallback in containerized environments when user systemd bus is missing.
- For Hermes messaging gateway in this environment, background run mode with nohup is the reliable default.
- Verify runtime health with status and doctor commands after config changes.

## Codebase Learning Protocol
- Before coding:
  - Query index for target subsystem.
  - Read only top relevant files first.
- After coding:
  - Run targeted tests for changed subsystem.
  - Record durable lesson in repo memory if it generalizes.
- Weekly:
  - Rebuild index fully if drift is suspected.
  - Refresh this knowledge pack from current docs.

## High-Value Source Docs
- DOCUMENTATION_INDEX.md
- docs/DOCUMENTATION_INDEX.md
- docs/developer/CODE_INDEX_MEMORY_PLAYBOOK.md
- scripts/indexing/README.md
- .github/copilot-instructions.md
