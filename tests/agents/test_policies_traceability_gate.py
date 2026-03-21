from agents.workflow_orchestrator import policies
from agents.critic import tools as critic_tools


def test_upsert_living_story_applies_traceability_gate(monkeypatch):
    class Cursor:
        def __init__(self):
            self.fetch_result = None

        def execute(self, _query, _params=None):
            return None

        def fetchone(self):
            return self.fetch_result

        def close(self):
            return None

    class Conn:
        def __init__(self):
            self.cursor_obj = Cursor()

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            return None

    class Service:
        def __init__(self):
            self.mb_conn = Conn()

        def ensure_conn(self):
            return None

    db_service = Service()

    monkeypatch.setattr(policies, '_fetch_article_context_metrics', lambda *_args, **_kwargs: {
        'source_count': 3,
        'unique_domain_count': 3,
        'fact_quality_score': 0.8,
        'source_diversity_score': 0.8,
        'recency_score': 0.8,
    })

    monkeypatch.setattr(
        critic_tools,
        'evaluate_traceability_balance',
        lambda *_args, **_kwargs: {'gate_result': 'fail', 'missing_reasons': ['insufficient_distinct_sides']},
    )

    result = policies.upsert_living_story_record(
        db_service=db_service,
        cluster_id='cluster-1',
        article_ids=[1, 2, 3],
        title_text='Title',
        body_text='Body',
        generation_audit={'analysis_report': {}},
    )

    assert result['publication_lane'] == 'developing_brief'


def test_upsert_living_story_traceability_gate_not_weakened_by_runtime_toggles(monkeypatch):
    class Cursor:
        def __init__(self):
            self.fetch_result = None

        def execute(self, _query, _params=None):
            return None

        def fetchone(self):
            return self.fetch_result

        def close(self):
            return None

    class Conn:
        def __init__(self):
            self.cursor_obj = Cursor()

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            return None

    class Service:
        def __init__(self):
            self.mb_conn = Conn()

        def ensure_conn(self):
            return None

    db_service = Service()

    monkeypatch.setattr(policies, '_fetch_article_context_metrics', lambda *_args, **_kwargs: {
        'source_count': 5,
        'unique_domain_count': 5,
        'fact_quality_score': 0.95,
        'source_diversity_score': 0.9,
        'recency_score': 0.8,
    })

    monkeypatch.setattr(
        critic_tools,
        'evaluate_traceability_balance',
        lambda *_args, **_kwargs: {'gate_result': 'fail', 'missing_reasons': ['missing_factual_corroboration']},
    )

    # Simulate permissive runtime toggles that would otherwise allow verified lane.
    monkeypatch.setenv('MULTI_SOURCE_LANE_POLICY_ENABLED', '1')
    monkeypatch.setenv('MULTI_SOURCE_LANE1_ENABLED', '1')
    monkeypatch.setenv('MULTI_SOURCE_LANE2_ENABLED', '0')
    monkeypatch.setenv('UNIFIED_CRAWLER_DISCOVERY_ENABLED', '1')
    monkeypatch.setenv('UNIFIED_CRAWLER_WHITELIST_ONLY_MODE', '0')

    result = policies.upsert_living_story_record(
        db_service=db_service,
        cluster_id='cluster-2',
        article_ids=[1, 2, 3, 4, 5],
        title_text='Title',
        body_text='Body',
        generation_audit={'analysis_report': {}},
    )

    assert result['publication_lane'] == 'developing_brief'
    assert 'traceability_balance_gate_failed' in result.get('publication_reason_codes', [])
