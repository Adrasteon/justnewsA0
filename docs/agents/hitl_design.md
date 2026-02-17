# HITL Service — Design and Interfaces

Purpose

- The HITL service stages candidate articles for human or programmatic labelling, stores label history, and forwards
  accepted labels to ingestion.

Files of interest

- `agents/hitl_service/app.py` — FastAPI application and endpoints

- `agents/hitl_service/migrations/` — DB migrations (SQLite staging schema)

- `agents/hitl_service/staging_bus.py` — helper for programmatic forwarders

Core responsibilities

- Receive candidate submissions from crawler (HTTP POST) and validate payload shape.

- Persist candidate rows and label actions to `hitl_staging.db`.

- Expose QA and training endpoints for human operators (review queues, label submission, comment metadata).

- Implement forwarding logic: retries, backoff, and deterministic ingestion-status transitions (`pending`→`forwarding`→`forwarded`|`error`).

Database schema (high level)

- `hitl_candidates` table: id, site_id, url, payload_json, created_at, status

- `hitl_labels` table: id, candidate_id, label, user, ingestion_status, created_at

API endpoints (examples)

- `POST /candidates` — Accept candidate payloads. Returns candidate id.

- `GET /candidates/{id}` — Retrieve stored payload and metadata.

- `POST /labels` — Submit label for a candidate (user or programmatic).

- `POST /forward/{label_id}` — Trigger forward attempt (used by automated forwarders/tests).

Forwarding workflow

1. On label creation, the service attempts to forward to the configured downstream endpoint (MCP or HTTP RPC) if
   `forward_on_label` enabled.

1. Forwarding uses staged backoff: immediate attempt, then exponential backoff with jitter, limited retries.

1. On success, `ingestion_status`is set to`forwarded`. On repeated failure, set to`error` and surface to QA.

Operational notes

- Healthchecks: implement `/-/health` endpoint returning DB access and last-forward timestamp.

- Start by default in system startup; operators can disable via env var `HITL_ENABLED=false`.

- Provide a staging-only mock forwarder for CI that accepts forwards without touching production services.

Tests

- Unit tests: payload validation, DB writes, label lifecycle transitions.

- Integration: end-to-end candidate → label → forward using mocked `memory`or`archive` services.
