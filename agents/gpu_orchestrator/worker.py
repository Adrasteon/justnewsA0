"""GPU Orchestrator worker process helpers.

The Worker class implements a minimal consumer that reads jobs from the
orchestrator's Redis stream, claims a GPU lease, runs the job handler
logic (here represented as a callable), updates persistent job status
and releases the lease.

This implementation is intentionally simple to keep test coverage small
and understandable. Production implementations should implement robust
XCLAIM/XAUTOCLAIM handling, idempotency guarantees, timeouts and retries.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from common.tracing import extract_trace_context, get_tracer


class Worker:
    def __init__(
        self,
        engine,
        redis_client=None,
        group="cg:inference",
        consumer="worker-1",
        agent_name: str = "worker",
    ):
        self.engine = engine
        self.redis = redis_client or getattr(engine, "redis_client", None)
        self.group = group
        self.consumer = consumer
        self.agent_name = agent_name
        self.stream = (
            os.environ.get("ORCH_STREAM_PREFIX", "stream:orchestrator:")
            + "inference_jobs"
        )

    def _decode_field(self, v: Any):
        if v is None:
            return None
        if isinstance(v, bytes):
            try:
                return v.decode("utf-8")
            except Exception:
                return v
        return v

    def run_once(self, handler=None) -> bool:
        """Perform one consumption & processing pass.

        Handler is a callable(payload) -> result. If omitted, we simulate work
        by sleeping briefly.
        Returns True if a job was processed, False otherwise.
        """
        if not self.redis:
            return False

        # read one message (best-effort—xreadgroup may not be available in tests)
        entries = []
        try:
            # Prefer xreadgroup if available
            if hasattr(self.redis, "xreadgroup"):
                msgs = self.redis.xreadgroup(
                    self.group, self.consumer, {self.stream: ">"}, count=1, block=100
                )
                for _stream, pairs in msgs:
                    for mid, fields in pairs:
                        entries.append((mid, fields))
            else:
                # fallback to xrange to get available messages
                pairs = self.redis.xrange(self.stream, "-", "+")
                if pairs:
                    entries.append(pairs[0])
        except Exception:
            # not available or empty
            return False

        if not entries:
            return False

        msg_id, fields = entries[0]

        # decode fields
        job_id = None
        payload = None
        t = None
        if isinstance(fields, dict):
            job_id_val = fields.get(b"job_id") or fields.get("job_id")
            if job_id_val is not None:
                job_id = self._decode_field(job_id_val)
                # job_id may be stored as a JSON string in tests (e.g. '"wjob1"'),
                # attempt to normalize by JSON-loading if possible.
                try:
                    if (
                        isinstance(job_id, str)
                        and job_id.startswith('"')
                        and job_id.endswith('"')
                    ):
                        job_id = json.loads(job_id)
                except Exception:
                    pass
            p = fields.get(b"payload") or fields.get("payload")
            if p is not None:
                try:
                    if isinstance(p, bytes):
                        payload = json.loads(p.decode("utf-8"))
                    else:
                        payload = json.loads(p)
                except Exception:
                    payload = self._decode_field(p)
            t = fields.get(b"type") or fields.get("type")
            if t is not None:
                t = self._decode_field(t)

        # Attempt to claim the job and obtain a lease atomically if DB-backed engine
        try:
            print(f"DEBUG: Worker picked job_id={job_id} msg_id={msg_id}")
        except Exception:
            pass

        lease_token = None
        if job_id and getattr(self.engine, "db_service", None):
            try:
                # Use engine helper that performs an atomic claim + lease transaction
                claim_resp = self.engine.claim_job_and_lease(
                    job_id,
                    self.agent_name,
                    payload.get("min_memory_mb") if isinstance(payload, dict) else 0,
                )
                if claim_resp.get("claimed"):
                    lease_token = claim_resp.get("token")
                else:
                    # couldn't claim (not pending / already claimed) — treat as processed
                    try:
                        self.engine.logger.debug(
                            f"Worker could not claim job_id={job_id}: {claim_resp}"
                        )
                    except Exception:
                        pass
                    # ack & return to avoid re-processing the message repeatedly
                    try:
                        self.redis.xack(self.stream, self.group, msg_id)
                    except Exception:
                        pass
                    return True
            except Exception:
                # fall back to previous best-effort claim path
                lease_token = None

        # acquire lease (best-effort)
        lease_token = None
        try:
            lease_resp = self.engine.lease_gpu(
                self.agent_name,
                payload.get("min_memory_mb") if isinstance(payload, dict) else 0,
            )
            if lease_resp.get("granted"):
                lease_token = lease_resp.get("token")
        except Exception:
            lease_token = None

        # run handler
        try:
            # Extract trace context
            trace_ctx = extract_trace_context(fields if isinstance(fields, dict) else {})
            tracer = get_tracer("gpu_worker")

            with tracer.start_as_current_span(
                "worker.process_job",
                context=trace_ctx,
                attributes={
                    "job_id": job_id or "unknown",
                    "agent": self.agent_name,
                    "group": self.group,
                }
            ) as span:
                start_time = time.time()
                if handler:
                    handler(payload)
                else:
                    # light simulation of doing the work
                    time.sleep(0.01)
                duration = time.time() - start_time
                span.set_attribute("duration_seconds", duration)

            # Record processing duration
            if hasattr(self.engine, "job_processing_duration_histogram"):
                job_type = t or "unknown"
                self.engine.job_processing_duration_histogram.labels(
                    job_type=job_type
                ).observe(duration)

            # mark running -> done
            if job_id and getattr(self.engine, "db_service", None):
                try:
                    cursor, conn = self.engine.db_service.get_safe_cursor(
                        per_call=True, buffered=True
                    )
                    try:
                        print(f"DEBUG: marking done for job_id={job_id}")
                        cursor.execute(
                            "UPDATE orchestrator_jobs SET status=%s, updated_at=CURRENT_TIMESTAMP WHERE job_id=%s",
                            ("done", job_id),
                        )
                        conn.commit()
                    finally:
                        try:
                            cursor.close()
                        except Exception:
                            pass
                        try:
                            conn.close()
                        except Exception:
                            pass
                    try:
                        self.engine.logger.debug(
                            f"Worker finished job_id={job_id}, updated DB to done"
                        )
                    except Exception:
                        pass
                except Exception:
                    pass

        except Exception as e:
            # Record retry
            if hasattr(self.engine, "job_retry_counter"):
                job_type = t or "unknown"
                self.engine.job_retry_counter.labels(job_type=job_type).inc()

            # mark failed
            if job_id and getattr(self.engine, "db_service", None):
                try:
                    cursor, conn = self.engine.db_service.get_safe_cursor(
                        per_call=True, buffered=True
                    )
                    try:
                        cursor.execute(
                            "UPDATE orchestrator_jobs SET status=%s, last_error=%s, updated_at=CURRENT_TIMESTAMP WHERE job_id=%s",
                            ("failed", str(e), job_id),
                        )
                        conn.commit()
                    finally:
                        try:
                            cursor.close()
                        except Exception:
                            pass
                        try:
                            conn.close()
                        except Exception:
                            pass
                except Exception:
                    pass
            # ensure lease released if one held
            if lease_token:
                try:
                    self.engine.release_gpu_lease(lease_token)
                except Exception:
                    pass
            return True

        # done: release lease if acquired
        if lease_token:
            try:
                self.engine.release_gpu_lease(lease_token)
            except Exception:
                pass

        # ACK message in stream
        try:
            self.redis.xack(self.stream, self.group, msg_id)
        except Exception:
            pass

        return True
