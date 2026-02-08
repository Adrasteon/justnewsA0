from unittest.mock import MagicMock

from agents.synthesizer import persistence


def make_fake_db_service():
    class Fake:
        def __init__(self):
            self.mb_conn = MagicMock()
            # simulate cursor with lastrowid
            fake_cursor = MagicMock()
            fake_cursor.lastrowid = 123
            self._cursor = fake_cursor
            self.mb_conn.cursor.return_value = fake_cursor
            self.collection = MagicMock()

        def close(self):
            pass

    return Fake()


def test_save_synthesized_draft_option_a(monkeypatch):
    fake = make_fake_db_service()
    monkeypatch.setattr(
        "database.utils.migrated_database_utils.create_database_service", lambda: fake
    )

    res = persistence.save_synthesized_draft(
        story_id="s1",
        title="Title A",
        body="Body text",
        summary="Summary",
        synth_metadata={"model": "gpt-test"},
        persistence_mode="extend",
        embedding=[0.1, 0.2, 0.3],
    )

    assert res["status"] == "success"
    assert res["id"] == 123
    fake.collection.add.assert_called_once()


def test_save_synthesized_draft_option_b(monkeypatch):
    fake = make_fake_db_service()
    monkeypatch.setattr(
        "database.utils.migrated_database_utils.create_database_service", lambda: fake
    )

    res = persistence.save_synthesized_draft(
        story_id="s2",
        title="Title B",
        body="Body text",
        summary="Summary",
        synth_metadata={"model": "gpt-test"},
        persistence_mode="synthesized_articles",
        embedding=[0.1, 0.2, 0.3],
    )

    assert res["status"] == "success"
    assert res["id"] == 123
    fake.collection.add.assert_called_once()
