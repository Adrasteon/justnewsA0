import asyncio

import pytest

from agents.memory.memory_engine import MemoryEngine


def test_memory_engine_init_fails_on_chroma_validation(monkeypatch):
    from database.utils.chromadb_utils import ChromaCanonicalValidationError

    def fake_create_db_service():
        raise ChromaCanonicalValidationError("canonical mismatch")

    # Monkeypatch the function **where it is used** (MemoryEngine imports it
    # at module level), otherwise the monkeypatch won't affect the already
    # imported reference inside the `agents.memory.memory_engine` module.
    monkeypatch.setattr(
        "agents.memory.memory_engine.create_database_service", fake_create_db_service
    )

    m = MemoryEngine()
    # Run the async initializer using asyncio.run to avoid loop warnings
    with pytest.raises(ChromaCanonicalValidationError):
        asyncio.run(m.initialize())
