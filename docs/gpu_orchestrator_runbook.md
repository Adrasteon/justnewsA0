# GPU Orchestrator Operator Runbook

This runbook provides operational procedures for managing the GPU Orchestrator in production environments.

## Emergency Procedures

### Force-Evict Worker Pools

**When to use:** When a worker pool is unresponsive, consuming excessive resources, or needs immediate termination.

**Procedure:**

1. Identify the problematic pool ID from metrics or logs

1. Use the API endpoint: `POST /pools/{pool_id}/stop`

1. Or via direct engine call: `engine.stop_worker_pool(pool_id)`

1. Monitor logs for cleanup confirmation

1. Check metrics to confirm pool removal

**Fallback (if API unavailable):**

```bash

## Connect to orchestrator process

kill -TERM <pool_worker_pid>  # Graceful shutdown

## Wait 30s, then force kill if needed

kill -KILL <pool_worker_pid>

```bash

### Drain Cluster

**When to use:** Planned maintenance, rolling updates, or emergency shutdown.

**Procedure:**

1. Set orchestrator to maintenance mode (if available)

1. Stop accepting new jobs: Update Redis stream consumer group to pause

1. Wait for active jobs to complete (monitor pending count → 0)

1. Stop all worker pools: `POST /pools/stop-all`

1. Verify no running processes remain

1. Shutdown orchestrator service

**Drain command sequence:**

```bash

## Pause consumer group

redis-cli XGROUP SETID stream:orchestrator:inference_jobs cg:inference 0

## Stop all pools via API

curl -X POST <http://localhost:8008/pools/stop-all>

## Verify cleanup

redis-cli XPENDING stream:orchestrator:inference_jobs cg:inference

```

### Recover from Dead Leader

**When to use:** Leader election failure, network partition, or leader process crash.

**Automatic recovery:**

- The orchestrator runs leader election every 2 seconds

- New leader automatically reconciles state from database

- Worker pools are rehydrated from persistent storage

**Manual intervention (if automatic fails):**

1. Check current leader status: `GET /status/leader`

1. Force leader election: Restart orchestrator process

1. Verify leader lock in database:

```sql SELECT * FROM mysql.locks WHERE lock_name = 'gpu_orchestrator_leader';

```bash

1. If lock stuck, manually release:

```
sql SELECT RELEASE_LOCK('gpu_orchestrator_leader');
```

**Symptoms of dead leader:**

- Pool lifecycle policies not enforced

- Metrics not updating

- New pools not starting

- Log messages: "Leader DB connection lost"

### Emergency OOM Handling

**When to use:** Out of memory conditions detected in GPU or system memory.

**Immediate actions:**

1. **Identify culprit:** Check GPU memory usage via `nvidia-smi`

1. **Stop largest pools first:**

```bash
# Find pools by memory usage (requires custom metric)
curl <http://localhost:8008/metrics> | grep worker_pool
```

1. **Force evict high-memory pools:**

```python
   # Via Python console
from agents.gpu_orchestrator.gpu_orchestrator_engine import engine pools =
engine.list_worker_pools()
   # Sort by estimated memory and evict largest

```

**OOM Prevention:**

- Monitor `gpu_orchestrator_nvml_mem_util_pct` > 90%

- Set `GPU_POOL_MAX_TOTAL` appropriately

- Enable `kill_on_oom` policy for automatic cleanup

**Post-OOM recovery:**

1. Clear any stuck processes

1. Restart orchestrator with reduced pool limits

1. Monitor for memory leaks in worker processes

## Monitoring and Alerts

### Key Metrics to Monitor

- `gpu_orchestrator_pending_jobs` > 100 (queue backlog)

- `gpu_orchestrator_stream_length` growing rapidly

- `gpu_orchestrator_worker_pool_evictions_total` increasing

- GPU memory utilization > 85%

- Leader election failures

Also ensure Prometheus alert rules from `monitoring/alerts/gpu_orchestrator_reclaimer_rules.yml` are loaded into the
monitoring stack. These rules notify on reclaimer errors, DLQ growth and elevated job retries.

### Log Patterns to Watch

- "XAUTOCLAIM not available" → Redis version issue

- "Failed to acquire leader lock" → DB connectivity

- "Pool eviction" → Resource pressure

- "Job retry" → Processing failures

## Maintenance Procedures

### Regular Cleanup

```bash

## Clean old completed jobs (older than 7 days)

DELETE FROM orchestrator_jobs WHERE status IN ('done', 'dead_letter') AND updated_at < DATE_SUB(NOW(), INTERVAL 7 DAY);

## Clean empty streams

redis-cli DEL stream:orchestrator:inference_jobs:dlq  # Only if empty

```

### Health Checks

- API endpoint: `GET /health`

- Database connectivity: Check orchestrator_leases table

- Redis connectivity: Ping streams

- GPU availability: `nvidia-smi` output

### Backup Considerations

- Database: Regular backups of orchestrator_jobs, orchestrator_leases, worker_pools

- Redis: AOF persistence enabled for streams

- Logs: Rotate audit logs in logs/audit/

## Operator Playbooks — step-by-step (for drills and incidents)

Below are concise playbooks intended for on-call operators. Each playbook is explicit about checks, commands, and
verification so teams can run drills and follow consistent procedures.

### Playbook: Safe drain + rolling upgrade (no data loss)

Purpose: gracefully drain workloads, perform a rolling upgrade of orchestrator or worker pools, then bring services back
online.

Pre-checks:

- Confirm maintenance window & notify stakeholders

- Verify backups for DB and Redis exist and are recent

- Ensure runbook authorisation and SRE on-call present

Steps:

1. Set maintenance flag (API toggle) so admission controller rejects new GPU jobs.

- POST /control/maintenance {"mode": "drain"}

1. Pause new consumer reads while allowing in-flight jobs to complete.

- redis-cli XGROUP SETID stream:orchestrator:inference_jobs cg:inference >

1. Monitor pending jobs and leases until the running/pending counts drop to 0.

- curl <http://localhost:8008/metrics> | grep gpu_orchestrator_pending_jobs

1. Stop worker pools cleanly via API: POST /pools/stop-all

1. Verify all pools are stopped: GET /pools -> should return empty or status=stopped

1. Upgrade orchestrator binary or configuration.

1. Start orchestrator & ensure leader election completed: GET /status/leader

1. Bring worker pools back up gradually and monitor metrics for stability.

1. Clear maintenance mode: POST /control/maintenance {"mode":"normal"}

Verification:

- No requeued or dead-letter activity during the window

- Prometheus shows healthy queue depth and worker counts

### Playbook: Evict a runaway worker pool (memory spike / rogue process)

Situation: a pool consumes runaway GPU or host memory and needs immediate eviction.

Steps:

1. Identify pool_id and affected hosts via dashboard / metrics

1. Attempt API graceful stop: POST /pools/{pool_id}/stop

1. If pool does not stop within configured grace period, force-stop via orchestrator process:

- engine.stop_worker_pool(pool_id)

- Optionally SSH to host and kill process PID

1. Confirm pool removed and leases released: GET /leases (no entries for pool_id)

Post-incident:

- Run memory health checks on host

- If problem is recurring, mark pool image/configuration for rollback

### Playbook: Leader stuck lock — forced recovery

When locks become stale (rare), clearing them is required carefully.

Steps (manual & with caution):

1. Confirm leader is dead: GET /status/leader OR inspect logs

1. Attempt graceful takeover by restarting orchestrator service on another host

1. If takeover fails and DB lock persists, inspect lock table using DB client and TTL

1. If lock is stale and safe to remove, run: SELECT RELEASE_LOCK('gpu_orchestrator_leader');

- Do NOT release live locks unless you have confirmed the previous leader has fully stopped.

1. Start orchestrator and confirm it becomes leader and rehydrates pools

### Playbook: Recover from DLQ storm

If DLQ grows unexpectedly (many jobs failing), follow:

1. Pause processing: set maintenance mode and pause consumers

1. Inspect sample DLQ messages (XREAD) to find root cause

1. Fix the underlying issue (e.g., missing artifacts, model pull failure)

1. Reprocess a small sample from DLQ: XADD to main stream and observe correct processing

1. Resume normal processing after confidence

---

## Runbook drill checklist (weekly/monthly)

Use this checklist to validate runbook readiness with an operator drill.

1. Execute a safe drain/upgrade in staging and confirm no data loss.

1. Force-evict a test pool and confirm the cluster recovers and restarts other pools.

1. Trigger a reclaimer run and simulate a set of stale messages (make sure DLQ policy works as expected).

1. Simulate leader failure and verify we can succeed in a manual takeover and that worker pools are rehydrated.

1. Validate alerts fire for pending_jobs and lease saturations; confirm on-call receives notification.

### Soak / performance tests

We use `scripts/perf/orchestrator_soak.sh`and the CI workflow`.github/workflows/perf-orchestrator-soak.yml` to run
manual soak tests on self- hosted GPU runners. These runs should be executed in staging before any large production
changes — collect artifacts and review CSV results for latency, retry rates, and DLQ behaviour.
