"""
Worker Engine - Background Task Coordination
===========================================

Responsibilities:
- Provide a lightweight executor for background tasks
- Hold references to core engines for delegated work
- Expose helpers for scheduling asynchronous jobs

Architecture:
- ThreadPoolExecutor with configurable worker count
- Async-friendly initialization and shutdown hooks
"""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from common.observability import get_logger

logger = get_logger(__name__)


class WorkerEngine:
    """Coordinates lightweight background tasks for the memory agent."""

    def __init__(self) -> None:
        self._executor: ThreadPoolExecutor | None = None
        self._memory_engine = None
        self._vector_engine = None
        self._running = False

    async def initialize(self, memory_engine, vector_engine) -> None:
        """Prepare worker resources and capture engine references."""
        if self._running:
            logger.debug("Worker engine already initialized")
            return

        max_workers = int(os.environ.get("MEMORY_WORKER_THREADS", "4"))
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="memory-worker"
        )
        self._memory_engine = memory_engine
        self._vector_engine = vector_engine
        self._running = True
        logger.info("Worker engine started with %s workers", max_workers)

    async def shutdown(self) -> None:
        """Shutdown the executor and clear references."""
        if not self._running:
            return

        self._running = False
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
        self._memory_engine = None
        self._vector_engine = None
        logger.info("Worker engine shut down")

    def submit(self, func: Callable[..., Any], *args, **kwargs) -> None:
        """Submit a callable to run in the worker executor."""
        if not self._running or self._executor is None:
            logger.debug(
                "Worker engine not ready; dropping submitted task %s",
                getattr(func, "__name__", func),
            )
            return
        try:
            self._executor.submit(func, *args, **kwargs)
        except Exception as exc:
            logger.warning("Failed to submit background task: %s", exc)
