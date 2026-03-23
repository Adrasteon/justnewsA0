from datetime import datetime, timedelta, timezone

from agents.chief_editor.tools import (
    _compute_taxonomy_drift_signal,
    _derive_publish_action,
    _ensure_publish_replacement_schema,
    _extract_publication_lane,
    _taxonomy_drift_threshold_for_lane,
)


class _FakeCursor:
    def __init__(self, columns=None, indexes=None):
        self.columns = columns or []
        self.indexes = indexes or []
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._last_sql = sql

    def fetchall(self):
        if 'SHOW COLUMNS FROM news_article' in self._last_sql:
            return [{'Field': value} for value in self.columns]
        if 'SHOW INDEX FROM news_article' in self._last_sql:
            return [{'Key_name': value} for value in self.indexes]
        return []


def test_derive_publish_action_create_when_no_existing_article():
    source = {
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }
    assert _derive_publish_action(source=source, existing_article=None) == 'create'


def test_derive_publish_action_republished_update_when_source_updated():
    created = datetime.now(timezone.utc) - timedelta(minutes=5)
    updated = created + timedelta(minutes=3)
    source = {'created_at': created, 'updated_at': updated}
    existing = {'id': 1, 'slug': 'example'}

    assert (
        _derive_publish_action(source=source, existing_article=existing)
        == 'republished_update'
    )


def test_derive_publish_action_refresh_when_not_meaningfully_updated():
    created = datetime.now(timezone.utc)
    source = {'created_at': created, 'updated_at': created}
    existing = {'id': 1, 'slug': 'example'}

    assert (
        _derive_publish_action(source=source, existing_article=existing)
        == 'republish_refresh'
    )


def test_ensure_publish_replacement_schema_adds_missing_columns_and_indexes():
    cursor = _FakeCursor(columns=['id', 'slug'], indexes=['PRIMARY', 'slug'])

    _ensure_publish_replacement_schema(cursor)

    executed_sql = '\n'.join(sql for sql, _ in cursor.executed)
    assert 'CREATE TABLE IF NOT EXISTS news_story_republish_events' in executed_sql
    assert 'ADD COLUMN story_id VARCHAR(64) NULL' in executed_sql
    assert 'ADD COLUMN source_cluster_id VARCHAR(64) NULL' in executed_sql
    assert 'CREATE INDEX idx_news_article_story_id ON news_article (story_id)' in executed_sql
    assert (
        'CREATE INDEX idx_news_article_source_cluster_id ON news_article (source_cluster_id)'
        in executed_sql
    )


def test_ensure_publish_replacement_schema_skips_existing_columns_and_indexes():
    cursor = _FakeCursor(
        columns=['id', 'slug', 'story_id', 'source_cluster_id'],
        indexes=['PRIMARY', 'slug', 'idx_news_article_story_id', 'idx_news_article_source_cluster_id'],
    )

    _ensure_publish_replacement_schema(cursor)

    executed_sql = '\n'.join(sql for sql, _ in cursor.executed)
    assert 'ADD COLUMN story_id VARCHAR(64) NULL' not in executed_sql
    assert 'ADD COLUMN source_cluster_id VARCHAR(64) NULL' not in executed_sql
    assert 'CREATE INDEX idx_news_article_story_id ON news_article (story_id)' not in executed_sql
    assert (
        'CREATE INDEX idx_news_article_source_cluster_id ON news_article (source_cluster_id)'
        not in executed_sql
    )


def test_extract_publication_lane_from_synth_metadata():
    source = {
        'synth_metadata': {
            'publication': {
                'publication_lane': 'developing_brief',
            }
        }
    }
    assert _extract_publication_lane(source) == 'developing_brief'


def test_compute_taxonomy_drift_signal_detects_dominant_category_shift():
    source = {
        'synth_metadata': {
            'publish': {
                'history': [
                    {'category': 'science'},
                    {'category': 'science'},
                    {'category': 'science'},
                    {'category': 'science'},
                    {'category': 'health'},
                ]
            }
        }
    }
    signal = _compute_taxonomy_drift_signal(source, observed_category='politics')
    assert signal['expected_category'] == 'science'
    assert signal['sample_size'] == 5
    assert signal['drift_score'] > 0.7


def test_compute_taxonomy_drift_signal_no_drift_without_history():
    source = {'synth_metadata': {}}
    signal = _compute_taxonomy_drift_signal(source, observed_category='science')
    assert signal['expected_category'] is None
    assert signal['drift_score'] == 0.0


def test_taxonomy_drift_threshold_developing_higher(monkeypatch):
    monkeypatch.setenv('LIVING_STORY_DRIFT_THRESHOLD_DEVELOPING', '0.90')
    monkeypatch.setenv('LIVING_STORY_DRIFT_THRESHOLD_STABLE', '0.60')
    assert _taxonomy_drift_threshold_for_lane('developing_brief') == 0.9
    assert _taxonomy_drift_threshold_for_lane('verified_story') == 0.6
