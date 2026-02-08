"""Simple job consumer skeleton for orchestrator (Redis Streams consumer).

This module provides a basic consumer pattern used by workers to read
jobs from Redis Streams, claim them and process them. It's intentionally
minimal — production consumers should handle XCLAIM/ACK, IDLE detection,
DLQ handling, and robust retry/backoff.
"""

from __future__ import annotations

import json
import os
import time


class JobConsumer:
    def __init__(self, redis_client=None, group="cg:inference", consumer="consumer-1"):
        self.redis = redis_client
        self.group = group
        self.consumer = consumer
        self.stream = (
            os.environ.get("ORCH_STREAM_PREFIX", "stream:orchestrator:")
            + "inference_jobs"
        )

    def poll(self, block_ms=2000, count=1):
        if not self.redis:
            return []
        try:
            msgs = self.redis.xreadgroup(
                self.group,
                self.consumer,
                {self.stream: ">"},
                count=count,
                block=block_ms,
            )
            # messages returned as list of (stream, [(id, {k:v})])
            out = []
            for _stream, entries in msgs:
                for id, fields in entries:
                    payload = fields.get(b"payload") or fields.get("payload")
                    if isinstance(payload, bytes):
                        try:
                            payload = json.loads(payload.decode("utf-8"))
                        except Exception:
                            payload = payload.decode("utf-8")
                    out.append({"id": id, "payload": payload, "raw": fields})
            return out
        except Exception:
            return []

    def ack(self, message_id: str):
        if self.redis:
            try:
                self.redis.xack(self.stream, self.group, message_id)
            except Exception:
                pass

    def run_forever(self, handler):
        while True:
            messages = self.poll()
            for m in messages:
                try:
                    # handler should be idempotent and accept dict payload
                    handler(m["payload"])
                    self.ack(m["id"])
                except Exception:
                    # consumer should implement retry / DLQ logic; keep simple here
                    pass
            time.sleep(0.1)
