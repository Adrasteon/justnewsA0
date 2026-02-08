import asyncio
import os

import pytest

from agents.archive.knowledge_graph import KnowledgeGraphManager
from agents.synthesizer import persistence as synth_persistence
from database.utils.migrated_database_utils import (
    create_database_service,
    get_article_entities,
)

requires_live_db = pytest.mark.skipif(
    os.environ.get("ENABLE_DB_INTEGRATION_TESTS") != "1",
    reason="Requires live MariaDB/Chroma deployment",
)


def test_make_chroma_metadata_includes_embedding_model_env():
    # Ensure environment-driven embedding metadata is attached
    os.environ["EMBEDDING_MODEL"] = "test-embed-model"
    os.environ["EMBEDDING_DIMENSIONS"] = "42"
    m = synth_persistence._make_chroma_metadata_safe({"story_id": "s1", "title": "t1"})
    assert m.get("embedding_model") == "test-embed-model"
    assert m.get("embedding_dimensions") == 42


@requires_live_db
def test_db_backed_kg_can_store_and_retrieve():
    svc = create_database_service()
    cursor = svc.mb_conn.cursor()

    # Find a sample article with a url_hash
    cursor.execute(
        "SELECT id, url_hash FROM articles WHERE url_hash IS NOT NULL LIMIT 1"
    )
    row = cursor.fetchone()
    assert row is not None, "No article available for KG test"
    article_id, url_hash = row[0], row[1]

    kg = KnowledgeGraphManager(backend="db")

    # Async store via event loop
    entities = ["OpenAI", "TestEntity"]
    relationships = [{"source": "OpenAI", "target": "TestEntity", "type": "cooccurs"}]

    asyncio.run(
        kg.store_article_entities({"url_hash": url_hash}, entities, relationships)
    )

    # Use DB helper to confirm entities are linked
    linked = get_article_entities(svc, article_id)
    assert isinstance(linked, list)
    # Ensure at least one of our new entities appears
    names = {e["name"] for e in linked}
    assert "OpenAI" in names or "TestEntity" in names

    cursor.close()
    svc.close()


@requires_live_db
def test_synthesized_draft_adds_embedding_metadata_to_chroma():
    # ensure env set
    import os

    os.environ["EMBEDDING_MODEL"] = os.environ.get(
        "EMBEDDING_MODEL", "all-MiniLM-L6-v2"
    )

    from agents.synthesizer.persistence import save_synthesized_draft
    from database.utils.migrated_database_utils import create_database_service

    emb = [0.0] * 384
    res = save_synthesized_draft(
        "test-story-embed",
        "Test title embed",
        "body",
        "summary",
        analysis_summary={"x": 1},
        synth_metadata={"from": "test"},
        persistence_mode="synthesized_articles",
        embedding=emb,
    )
    assert res.get("status") == "success"
    svc = create_database_service()
    try:
        if svc.collection:
            out = svc.collection.get(ids=[str(res["id"])], include=["metadatas"])
            metas = out.get("metadatas", [])
            if metas:
                md = metas[0]
                assert "embedding_model" in md
    finally:
        svc.close()
