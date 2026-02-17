import os

import pytest

from database.utils.migrated_database_utils import create_database_service

requires_live_db = pytest.mark.skipif(
    os.environ.get("ENABLE_DB_INTEGRATION_TESTS") != "1",
    reason="Requires live MariaDB deployment",
)


@pytest.mark.integration
@requires_live_db
def test_persistence_tables_exist_and_smoke_insert():
    """Integration test: verify core persistence tables exist and accept writes.

    This test requires a running MariaDB instance configured for the repo (see
    /etc/justnews/global.env or system_config.json). It verifies entities,
    article_entities, training_examples and model_metrics schemas are present.
    """
    svc = create_database_service()
    cursor = svc.mb_conn.cursor()

    def table_exists(name: str) -> bool:
        cursor.execute("SHOW TABLES LIKE %s", (name,))
        return cursor.fetchone() is not None

    assert table_exists("entities"), "entities table missing"
    assert table_exists("article_entities"), "article_entities table missing"
    assert table_exists("training_examples"), "training_examples table missing"
    assert table_exists("model_metrics"), "model_metrics table missing"
    assert table_exists("synthesized_articles"), "synthesized_articles table missing"
    assert table_exists("synthesizer_jobs"), "synthesizer_jobs table missing"

    # Smoke insert into training_examples and cleanup
    cursor.execute(
        "INSERT INTO training_examples (task, input, output, critique) VALUES (%s,%s,%s,%s)",
        ("pytest_smoke", '{"i":1}', '{"o":1}', "smoke"),
    )
    svc.mb_conn.commit()
    cursor.execute(
        "SELECT id FROM training_examples WHERE task=%s ORDER BY created_at DESC LIMIT 1",
        ("pytest_smoke",),
    )
    row = cursor.fetchone()
    assert row is not None, "Unable to insert into training_examples"
    # cleanup
    cursor.execute("DELETE FROM training_examples WHERE id=%s", (row[0],))
    svc.mb_conn.commit()

    cursor.close()
    svc.close()
