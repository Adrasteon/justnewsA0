# GPU Orchestrator — Developer Guide

This document explains the `GPU Orchestrator` implementation and how to run and test it locally. The implementation
lives under `agents/gpu_orchestrator`and includes the core engine (`gpu_orchestrator_engine.py`), a FastAPI front-end
(`main.py`), a Redis stream consumer skeleton (`job_consumer.py`), and a`Worker`process implementation (`worker.py`).

Purpose

- Provide persistent GPU leases, worker pool lifecycle management, and durable job processing using MariaDB and Redis
  Streams.

- Provide leader election and reconciliation for HA and safe policy enforcement.

Key implementation points

- Persistence: `orchestrator_leases`,`worker_pools`,`orchestrator_jobs`tables. DDL is
  in`scripts/init_database.py`and`scripts/deploy/init_database.py`.

- Streams: messages read/written to `stream:orchestrator:inference_jobs`and`stream:orchestrator:preloads` — DLQ suffix
  used for dead-letter.

- Leader election: implemented using MariaDB GET_LOCK semantics in `GPUOrchestratorEngine._leader_election_loop`.

- Reclaimer: `_reclaimer_pass`and`_reclaimer_loop` in the engine reclaims stale pending messages and moves messages to
  DLQ or requeues them.

- Worker lifecycle: `Worker.run_once()` implements claiming DB status updates, lease requests via engine.lease_gpu, run
  handler, updating DB and releasing lease.

Local quickstart

1. Unit & integration tests default to in-memory sqlite and in-memory Redis emulators — these are the recommended quick
   path during development. See `tests/integration` for samples.

1. To spin the engine locally using the persisted DB (MariaDB) and a real Redis, set appropriate `JUSTNEWS_GLOBAL_ENV`or
   environment variables so`create_database_service()` returns a real connection.

FastAPI endpoints (developer view)

- See `agents/gpu_orchestrator/main.py` for the exposed endpoints and request/response shapes. Typical endpoints
  include:

- POST /leases — request a lease

- POST /leases/{token}/heartbeat — heartbeat a lease

- POST /leases/{token}/release — release a lease

- POST /jobs/submit — persist and submit a job to the stream

- GET /jobs/{job_id} — get job status

- POST /control/reclaim — invoke reclaimer pass (admin)

Testing harnesses & notes

- Integration tests in `tests/integration`intentionally use sqlite + in-memory Redis adapters
  (see`create_sqlite_service()` helpers in the tests) so CI remains fast and deterministic.

- The repo includes `tests/unit/test_gpu_orchestrator_reclaimer.py`,`tests/unit/test_gpu_orchestrator_persistent_leases.
  py`,`tests/integration/test_worker_flow.py` and others for coverage.

Where to look in code

- Implementation & logic: `agents/gpu_orchestrator/gpu_orchestrator_engine.py`

- API surface: `agents/gpu_orchestrator/main.py`

- Worker consumer: `agents/gpu_orchestrator/worker.py`and`job_consumer.py`

- Tests: `tests/unit/`and`tests/integration/`

Operational notes

- In production, prefer running the engine on dedicated nodes where MariaDB and Redis are reliable. The engine will
  attempt best-effort operations when persistence isn't available; tests intentionally use best-effort fallbacks in some
  paths for robustness.

- Monitor `gpu_orchestrator_lease_expired_total`and`gpu_orchestrator_job_queue_depth` metrics exposed in the engine for
  autoscaling and safety.

If you need a deeper guide for manually bringing a MariaDB+Redis dev environment up without Docker, see
`docs/dev/systemd-nspawn.md`(systemd container helper) and the`scripts/dev/run_systemd_nspawn_env.sh` script.
