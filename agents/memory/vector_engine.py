"""
Vector Engine - Embedding and Vector Search Orchestration
=========================================================

Responsibilities:
- Manage the shared embedding model lifecycle
- Provide local vector search facilities for the memory agent
- Coordinate model reloads triggered at runtime

Architecture:
- Lazy initialization of the embedding model via shared helper
- Async-friendly reload logic using executor offloading
- Thin wrapper around legacy vector search utilities
"""

from __future__ import annotations

import asyncio
from threading import Lock

from agents.memory import tools as memory_tools
from common.observability import get_logger

logger = get_logger(__name__)


class VectorEngine:
    """Manages embedding model lifecycle and vector search helpers."""

    def __init__(self) -> None:
        self._embedding_model = None
        self._model_lock = Lock()

    @property
    def embedding_model(self):
        with self._model_lock:
            return self._embedding_model

    async def initialize(self) -> None:
        """Load the embedding model at startup."""
        await self._load_model(reason="startup")

    async def shutdown(self) -> None:
        """Release references to heavy resources."""
        with self._model_lock:
            self._embedding_model = None
        logger.info("Vector engine shut down")

    async def reload_model(self) -> None:
        """Reload the embedding model; used by the hot-reload endpoint."""
        await self._load_model(reason="reload")

    def vector_search_articles_local(self, query: str, top_k: int = 5) -> list[dict]:
        """Delegate to legacy helper with the cached embedding model."""
        try:
            embedding_model = self.embedding_model
            if embedding_model is None:
                logger.debug("Vector engine missing model; loading synchronously")
                embedding_model = memory_tools.get_embedding_model()
                if embedding_model is None:
                    return []
                with self._model_lock:
                    self._embedding_model = embedding_model

            results = memory_tools.vector_search_articles_local(
                query,
                top_k,
                embedding_model=embedding_model,
            )
            return results or []
        except Exception as exc:
            logger.warning("Vector search failed: %s", exc)
            return []

    async def _load_model(self, reason: str) -> None:
        """Internal helper that (re)loads the embedding model safely."""
        loop = asyncio.get_running_loop()
        try:
            model = await loop.run_in_executor(None, memory_tools.get_embedding_model)
        except Exception as exc:
            logger.error("Embedding model load failed during %s: %s", reason, exc)
            with self._model_lock:
                self._embedding_model = None
            raise

        if model is None:
            logger.error(
                "Vector engine could not load embedding model during %s", reason
            )
            with self._model_lock:
                self._embedding_model = None
            return

        with self._model_lock:
            self._embedding_model = model
        logger.info("Vector engine loaded embedding model during %s", reason)
