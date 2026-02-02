"""Live ChromaDB integration tests.

These tests are optional and require a fully configured MariaDB + ChromaDB
stack along with access to the canonical ModelStore. Enable them by exporting
`ENABLE_CHROMADB_LIVE_TESTS=1` and run via `scripts/run_with_env.sh` so the
standard `global.env` variables (MODEL_STORE_ROOT, CHROMADB_*, etc.) are
available to pytest.
"""

from __future__ import annotations

import os
import uuid

import pytest

from agents.synthesizer.model_adapter import SynthesizerModelAdapter
from database.utils.migrated_database_utils import create_database_service

requires_live_chroma = pytest.mark.skipif(
    os.environ.get("ENABLE_CHROMADB_LIVE_TESTS") != "1",
    reason=(
        "Set ENABLE_CHROMADB_LIVE_TESTS=1 and invoke pytest via scripts/run_with_env.sh "
        "to run live ChromaDB integration tests"
    ),
)


def _require_model_store() -> None:
    if not os.environ.get("MODEL_STORE_ROOT"):
        pytest.skip(
            "MODEL_STORE_ROOT is not set. Run with scripts/run_with_env.sh or export the"
            " canonical model store location before executing this test."
        )


@requires_live_chroma
@pytest.mark.integration
@pytest.mark.chroma
def test_chromadb_embedding_round_trip():
    """Ensure SentenceTransformer embeddings can be persisted and fetched from Chroma."""
    svc = create_database_service()
    doc_id = f"chromatest-{uuid.uuid4()}"
    try:
        collection = getattr(svc, "collection", None)
        if collection is None:
            pytest.skip("ChromaDB collection not available; check CHROMADB_* env vars.")

        embedder = getattr(svc, "embedding_model", None)
        if embedder is None:
            pytest.skip(
                "Embedding model not loaded; ensure EMBEDDING_MODEL is configured."
            )

        body = "Live Chroma round-trip verification."
        embedding = embedder.encode(body).tolist()
        metadata = {
            "source": "pytest",
            "kind": "embedding-round-trip",
        }

        collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[body],
            metadatas=[metadata],
        )

        fetched = collection.get(ids=[doc_id], include=["documents", "metadatas"])
        assert fetched["ids"], "Chroma returned empty result set"
        assert fetched["documents"][0] == body
        assert fetched["metadatas"][0]["kind"] == "embedding-round-trip"
    finally:
        try:
            if getattr(svc, "collection", None):
                svc.collection.delete(ids=[doc_id])
        except Exception:
            pass
        svc.close()


@requires_live_chroma
@pytest.mark.integration
@pytest.mark.chroma
def test_chromadb_entry_records_mistral_metadata(monkeypatch):
    """Store synthesized content tagged with the adapter metadata."""
    _require_model_store()

    svc = create_database_service()
    doc_id = f"chromatest-mistral-{uuid.uuid4()}"
    try:
        collection = getattr(svc, "collection", None)
        if collection is None:
            pytest.skip("ChromaDB collection not available; check CHROMADB_* env vars.")

        embedder = getattr(svc, "embedding_model", None)
        if embedder is None:
            pytest.skip(
                "Embedding model not loaded; ensure EMBEDDING_MODEL is configured."
            )

        adapter = SynthesizerModelAdapter()

        def _fake_chat_json(_messages):
            return {
                "summary": "Adapter-driven synthesis integration sample.",
                "narrative_voice": "neutral",
                "key_points": ["point-a", "point-b"],
            }

        monkeypatch.setattr(adapter, "_chat_json", _fake_chat_json)
        payload = adapter.summarize_cluster(
            [
                "Article One contents for integration coverage.",
                "Article Two contents for integration coverage.",
            ],
            context="Live Chroma smoke test",
        )
        assert payload is not None
        summary = payload["summary"]

        embedding = embedder.encode(summary).tolist()
        metadata = {
            "source": "pytest",
            "adapter": adapter.adapter_name,
            "method": "model_adapter",
            "is_synthesized": True,
        }

        collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[summary],
            metadatas=[metadata],
        )

        fetched = collection.get(ids=[doc_id], include=["metadatas", "documents"])
        assert fetched["metadatas"][0]["adapter"] == adapter.adapter_name
        assert fetched["metadatas"][0]["is_synthesized"] is True
        assert fetched["documents"][0] == summary
    finally:
        try:
            if getattr(svc, "collection", None):
                svc.collection.delete(ids=[doc_id])
        except Exception:
            pass
        svc.close()
