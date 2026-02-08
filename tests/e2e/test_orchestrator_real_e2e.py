import json
import os
import time

import pytest

from agents.gpu_orchestrator.gpu_orchestrator_engine import GPUOrchestratorEngine
from agents.gpu_orchestrator.worker import Worker

# These tests require real Redis + MariaDB running locally (used by CI). Skip by
# default for developer runs unless the caller explicitly opts in by setting
# RUN_REAL_E2E=1 in the environment.
requires_real_e2e = pytest.mark.skipif(
    os.environ.get("RUN_REAL_E2E", "") != "1",
    reason="Real E2E tests require RUN_REAL_E2E=1",
)


def test_e2e_job_submission_and_processing():
    """Submit a job to the real Redis + MariaDB and verify a Worker processing pass completes the job.

    This test requires a running MariaDB and Redis on localhost (containerized by CI or systemd-nspawn).
    """
    print("Starting test...")
    engine = GPUOrchestratorEngine()

    # configure to use local redis/mariadb (these env vars are set in the CI job)
    try:
        import redis as _redis

        engine.redis_client = _redis.Redis(
            host="127.0.0.1", port=6379, decode_responses=False
        )
        print("Redis client created")
    except Exception as e:
        print(f"Redis client failed: {e}")
        pytest.skip("redis client not available")

    # Initialize DB service if not already done
    if engine.db_service is None:
        try:
            from database.utils.migrated_database_utils import create_database_service

            engine.db_service = create_database_service()
            print("DB service created")
        except Exception as e:
            print(f"DB service failed: {e}")
            pytest.skip("database service not available")

    # deterministic lease allocation
    engine._allocate_gpu = lambda req: (True, 0)

    job_id = f"e2e-job-{int(time.time())}"
    res = engine.submit_job(job_id, "inference_jobs", {"message": "hello-e2e"})
    assert res["job_id"] == job_id

    # Ensure consumer group exists
    stream = "stream:orchestrator:inference_jobs"
    try:
        engine.redis_client.xgroup_create(stream, "cg:inference", id="0", mkstream=True)
    except Exception:
        # group may already exist
        pass

    # run a single worker pass to pick the message
    worker = Worker(engine, redis_client=engine.redis_client, agent_name="e2e-worker")
    processed = worker.run_once()
    assert processed is True

    # verify DB updated to done
    cur = engine.db_service.mb_conn.cursor()
    cur.execute("SELECT status FROM orchestrator_jobs WHERE job_id=%s", (job_id,))
    r = cur.fetchone()
    assert r is not None and r[0] == "done"


@requires_real_e2e
def test_e2e_reclaimer_moves_to_dlq_when_max_attempts_reached():
    engine = GPUOrchestratorEngine()
    try:
        import redis as _redis

        engine.redis_client = _redis.Redis(
            host="127.0.0.1", port=6379, decode_responses=False
        )
    except Exception:
        pytest.skip("redis client not available")

    cur = engine.db_service.mb_conn.cursor()

    # create a job with attempts = 1 and persist
    job_id = f"e2e-dlq-{int(time.time())}"
    cur.execute(
        "INSERT INTO orchestrator_jobs (job_id, type, payload, status, attempts) VALUES (%s,%s,%s,%s,%s)",
        (job_id, "inference_jobs", json.dumps({"x": 1}), "pending", 1),
    )
    engine.db_service.mb_conn.commit()

    stream = "stream:orchestrator:inference_jobs"
    # ensure consumer group
    try:
        engine.redis_client.xgroup_create(stream, "cg:inference", id="$", mkstream=True)
    except Exception:
        # group may exist
        pass

    # add to stream
    _mid = engine.redis_client.xadd(
        stream, {"job_id": job_id, "payload": json.dumps({"x": 1})}
    )

    # claim the message with a consumer so it becomes pending
    engine.redis_client.xreadgroup(
        "cg:inference", "consumer-1", {stream: ">"}, count=1, block=100
    )

    # set reclaim thresholds low for quick test
    engine._claim_idle_ms = 10
    engine._job_retry_max = 2

    # wait a small time so idle increases
    time.sleep(0.02)

    # run reclaimer pass
    engine._reclaimer_pass()

    # verify job marked dead_letter or attempts updated depending on timing
    cur.execute(
        "SELECT attempts, status FROM orchestrator_jobs WHERE job_id=%s", (job_id,)
    )
    r = cur.fetchone()
    assert r is not None
    assert r[0] >= 2 or r[1] == "dead_letter"

    # if DLQ path taken, there should be an entry in stream:orchestrator:inference_jobs:dlq
    dlq = stream + ":dlq"
    entries = engine.redis_client.xrange(dlq, "-", "+")
    # either DLQ entry present or attempts bumped
    assert (len(entries) > 0) or (r[0] >= 2)


@requires_real_e2e
def test_e2e_leader_takeover_between_two_engines():
    # validate GET_LOCK style leadership handoff
    e1 = GPUOrchestratorEngine()
    e2 = GPUOrchestratorEngine()

    # try acquire in e1 and ensure it becomes leader
    got1 = e1.try_acquire_leader_lock(timeout=1)
    assert got1 is True
    assert e1.is_leader is True

    # e2 should not be leader while e1 holds lock
    got2 = e2.try_acquire_leader_lock(timeout=1)
    assert got2 is False

    # release lock on e1 and allow e2 to acquire
    e1.release_leader_lock()
    got2_after = e2.try_acquire_leader_lock(timeout=1)
    assert got2_after is True
    assert e2.is_leader is True


@requires_real_e2e
def test_e2e_lease_heartbeat_and_release():
    engine = GPUOrchestratorEngine()
    # ensure we can talk to redis
    try:
        import redis as _redis

        engine.redis_client = _redis.Redis(
            host="127.0.0.1", port=6379, decode_responses=False
        )
    except Exception:
        pytest.skip("redis client not available")

    # deterministic allocator
    engine._allocate_gpu = lambda req: (True, 0)
    token_resp = engine.lease_gpu("e2e-agent", 0)
    assert token_resp.get("granted")
    token = token_resp.get("token")

    # heartbeat updates DB
    ok = engine.heartbeat_lease(token)
    assert ok is True

    # verify DB last_heartbeat present
    cur = engine.db_service.mb_conn.cursor()
    cur.execute(
        "SELECT last_heartbeat FROM orchestrator_leases WHERE token=%s", (token,)
    )
    r = cur.fetchone()
    assert r is not None

    # release should delete row
    engine.release_gpu_lease(token)
    cur.execute("SELECT token FROM orchestrator_leases WHERE token=%s", (token,))
    r2 = cur.fetchone()
    assert r2 is None


@requires_real_e2e
def test_e2e_worker_pool_rehydrate():
    engine = GPUOrchestratorEngine()
    cur = engine.db_service.mb_conn.cursor()

    pool_id = f"e2e-pool-{int(time.time())}"
    cur.execute(
        "INSERT INTO worker_pools (pool_id, agent_name, model_id, desired_workers, spawned_workers, status, metadata) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (pool_id, "e2e-agent", "e2e-model", 2, 0, "running", '{"variant":"fp16"}'),
    )
    engine.db_service.mb_conn.commit()

    # new engine should rehydrate
    e2 = GPUOrchestratorEngine()
    assert pool_id in e2._WORKER_POOLS


@requires_real_e2e
def test_e2e_reclaimer_requeues_when_attempts_lt_max_and_moves_to_dlq_when_exceeded():
    engine = GPUOrchestratorEngine()
    try:
        import redis as _redis

        engine.redis_client = _redis.Redis(
            host="127.0.0.1", port=6379, decode_responses=False
        )
    except Exception:
        pytest.skip("redis client not available")

    cur = engine.db_service.mb_conn.cursor()

    job_id = f"e2e-reclaim-{int(time.time())}"
    # start with attempts=0
    cur.execute(
        "INSERT INTO orchestrator_jobs (job_id, type, payload, status, attempts) VALUES (%s,%s,%s,%s,%s)",
        (job_id, "inference_jobs", json.dumps({"x": 1}), "pending", 0),
    )
    engine.db_service.mb_conn.commit()

    stream = "stream:orchestrator:inference_jobs"
    engine.redis_client.xadd(
        stream, {"job_id": job_id, "payload": json.dumps({"x": 1})}
    )

    # claim entry so it becomes pending
    engine.redis_client.xreadgroup(
        "cg:inference", "consumer-x", {stream: ">"}, count=1, block=100
    )

    # set thresholds low
    engine._claim_idle_ms = 5
    engine._job_retry_max = 3

    # small sleep so idle > claim_idle_ms
    time.sleep(0.01)

    # run reclaimer pass -> should requeue (not DLQ) because attempts < max
    engine._reclaimer_pass()

    # the message should be requeued (a new message in stream) and original pending acked
    entries = engine.redis_client.xrange(stream, "-", "+")
    assert any(
        job_id.encode("utf-8") in (fields.get(b"job_id") or b"")
        for _, fields in entries
    )

    # Now set attempts in DB to max-1 so next reclaim moves to DLQ
    cur.execute(
        "UPDATE orchestrator_jobs SET attempts=%s WHERE job_id=%s",
        (engine._job_retry_max - 1, job_id),
    )
    engine.db_service.mb_conn.commit()

    # mimic another pending entry
    engine.redis_client.xadd(
        stream, {"job_id": job_id, "payload": json.dumps({"x": 1})}
    )
    engine.redis_client.xreadgroup(
        "cg:inference", "consumer-y", {stream: ">"}, count=1, block=100
    )
    time.sleep(0.01)

    engine._reclaimer_pass()

    # entry should be in DLQ
    dlq = stream + ":dlq"
    dlq_entries = engine.redis_client.xrange(dlq, "-", "+")
    assert len(dlq_entries) > 0


@requires_real_e2e
def test_e2e_lease_expiry_and_purge():
    engine = GPUOrchestratorEngine()
    # set small TTL for DB persistence
    os.environ["GPU_ORCHESTRATOR_LEASE_TTL"] = "1"

    engine._allocate_gpu = lambda req: (True, 0)
    resp = engine.lease_gpu("e2e-agent-expire", 0)
    assert resp.get("granted")
    token = resp.get("token")

    # make DB expires_at in the past, so purge should remove it
    cur = engine.db_service.mb_conn.cursor()
    cur.execute(
        "UPDATE orchestrator_leases SET expires_at=DATE_SUB(NOW(), INTERVAL 1 SECOND) WHERE token=%s",
        (token,),
    )
    engine.db_service.mb_conn.commit()

    # ensure ALLOCATIONS timestamp is old so in-memory purge will remove it as well
    try:
        from agents.gpu_orchestrator.gpu_orchestrator_engine import ALLOCATIONS

        if token in ALLOCATIONS:
            ALLOCATIONS[token]["timestamp"] = time.time() - 7200
    except Exception:
        pass

    engine._purge_expired_leases()

    # DB row removed
    cur.execute("SELECT token FROM orchestrator_leases WHERE token=%s", (token,))
    assert cur.fetchone() is None


@requires_real_e2e
def test_e2e_worker_restart_idempotency():
    engine = GPUOrchestratorEngine()
    try:
        import redis as _redis

        engine.redis_client = _redis.Redis(
            host="127.0.0.1", port=6379, decode_responses=False
        )
    except Exception:
        pytest.skip("redis client not available")

    engine._allocate_gpu = lambda req: (True, 0)

    job_id = f"e2e-idemp-{int(time.time())}"
    engine.submit_job(job_id, "inference_jobs", {"x": 1})

    worker = Worker(
        engine, redis_client=engine.redis_client, agent_name="e2e-idempotent"
    )
    processed1 = worker.run_once()
    assert processed1 is True

    # run again -- should not break or change the status away from done
    processed2 = worker.run_once()
    assert processed2 is True

    # check DB status remains done
    cur = engine.db_service.mb_conn.cursor()
    cur.execute("SELECT status FROM orchestrator_jobs WHERE job_id=%s", (job_id,))
    r = cur.fetchone()
    assert r is not None and r[0] == "done"
