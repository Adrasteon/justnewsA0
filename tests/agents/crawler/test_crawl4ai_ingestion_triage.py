import asyncio
import sys
import types

from agents.crawler import crawl4ai_adapter as adapter
from agents.sites.generic_site_crawler import SiteConfig


def test_heuristic_triage_rejects_utility_urls():
    decision = adapter._heuristic_triage_decision(
        url='https://example.com/contact',
        title='Contact Us',
        content='Reach out to our team for support and sales inquiries.' * 8,
    )
    assert decision.decision == 'reject'
    assert 'non_news_utility_url' in decision.reason_codes


def test_heuristic_triage_accepts_article_like_content():
    content = (
        'Published today. By Jane Reporter. '
        'Officials said the measure would take effect immediately after debate. '
        * 30
    )
    decision = adapter._heuristic_triage_decision(
        url='https://example.com/world/policy-update-12345',
        title='Policy update draws mixed response',
        content=content,
    )
    assert decision.decision == 'accept'


def test_apply_ingestion_triage_uses_ai_for_ambiguous(monkeypatch):
    monkeypatch.setenv('CRAWL4AI_INGESTION_TRIAGE_ENABLED', '1')
    monkeypatch.setenv('CRAWL4AI_AI_TRIAGE_ENABLED', '1')
    monkeypatch.setenv('CRAWL4AI_AI_TRIAGE_AMBIGUOUS_ONLY', '1')

    ai_decision = adapter.IngestionTriageDecision(
        decision='reject',
        confidence=0.9,
        reason_codes=['navigation_page'],
        source='ai',
        page_type='index',
    )

    def _fake_ai(*_args, **_kwargs):
        return ai_decision

    monkeypatch.setattr(adapter, '_run_ai_triage', _fake_ai)

    article = {
        'url': 'https://example.com/world/analysis-brief',
        'title': 'Regional developments update',
        'content': 'Officials discussed developments in the region during a briefing. ' * 12,
    }
    site = SiteConfig({'domain': 'example.com', 'url': 'https://example.com'})
    profile = {'profile_slug': 'test'}

    updated = asyncio.run(adapter._apply_ingestion_triage(article, site, profile))

    assert updated.get('skip_ingest') is True
    assert updated.get('ingestion_status') == 'triage_rejected'
    triage = updated.get('extraction_metadata', {}).get('ingestion_triage', {})
    assert triage.get('source') == 'ai'
    assert triage.get('decision') == 'reject'


def test_domain_specific_threshold_prevents_low_confidence_reject(monkeypatch):
    monkeypatch.setenv('CRAWL4AI_INGESTION_TRIAGE_ENABLED', '1')
    monkeypatch.setenv('CRAWL4AI_AI_TRIAGE_ENABLED', '1')
    monkeypatch.setenv('CRAWL4AI_AI_TRIAGE_AMBIGUOUS_ONLY', '1')
    monkeypatch.setenv(
        'CRAWL4AI_AI_TRIAGE_DOMAIN_THRESHOLDS_JSON',
        '{"example.com": 0.95}',
    )

    ai_decision = adapter.IngestionTriageDecision(
        decision='reject',
        confidence=0.9,
        reason_codes=['navigation_page'],
        source='ai',
        page_type='index',
    )

    monkeypatch.setattr(adapter, '_run_ai_triage', lambda *_args, **_kwargs: ai_decision)

    article = {
        'url': 'https://example.com/world/analysis-brief',
        'title': 'Regional developments update',
        'content': 'Officials discussed developments in the region during a briefing. ' * 12,
    }
    site = SiteConfig({'domain': 'example.com', 'url': 'https://example.com'})
    profile = {'profile_slug': 'test'}

    updated = asyncio.run(adapter._apply_ingestion_triage(article, site, profile))

    assert updated.get('skip_ingest') is not True
    triage = updated.get('extraction_metadata', {}).get('ingestion_triage', {})
    assert triage.get('reject_confidence_threshold') == 0.95


def test_quarantine_sets_quarantined_status(monkeypatch):
    monkeypatch.setenv('CRAWL4AI_INGESTION_TRIAGE_ENABLED', '1')
    monkeypatch.setenv('CRAWL4AI_AI_TRIAGE_ENABLED', '1')
    monkeypatch.setenv('CRAWL4AI_AI_TRIAGE_AMBIGUOUS_ONLY', '1')

    ai_decision = adapter.IngestionTriageDecision(
        decision='quarantine',
        confidence=0.99,
        reason_codes=['possible_multi_story_page'],
        source='ai',
        page_type='mixed',
    )

    monkeypatch.setattr(adapter, '_run_ai_triage', lambda *_args, **_kwargs: ai_decision)

    article = {
        'url': 'https://example.com/world/analysis-brief',
        'title': 'Regional developments update',
        'content': 'Officials discussed developments in the region during a briefing. ' * 12,
    }
    site = SiteConfig({'domain': 'example.com', 'url': 'https://example.com'})
    profile = {'profile_slug': 'test'}

    updated = asyncio.run(adapter._apply_ingestion_triage(article, site, profile))

    assert updated.get('skip_ingest') is True
    assert updated.get('ingestion_status') == 'triage_quarantined'
    assert updated.get('skip_reason') == 'ingestion_triage'


def test_forward_triage_prediction_for_training(monkeypatch):
    monkeypatch.setenv('CRAWL4AI_TRIAGE_TRAINING_FEEDBACK_ENABLED', '1')
    monkeypatch.setenv('CRAWL4AI_TRIAGE_TRAINING_SAMPLE_RATE', '1')
    monkeypatch.setenv('CRAWL4AI_TRIAGE_TRAINING_AGENT', 'crawler_triage')

    captured: dict[str, object] = {}

    def _fake_collect_prediction(**kwargs):
        captured.update(kwargs)

    fake_mod = types.SimpleNamespace(collect_prediction=_fake_collect_prediction)
    monkeypatch.setitem(sys.modules, 'training_system.core.system_manager', fake_mod)

    decision = adapter.IngestionTriageDecision(
        decision='reject',
        confidence=0.91,
        reason_codes=['navigation_heavy_text'],
        source='ai',
        page_type='index',
    )

    adapter._forward_triage_prediction_for_training(
        url='https://example.com/latest',
        title='Latest Updates',
        content='A short content block',
        decision=decision,
    )

    assert captured['agent_name'] == 'crawler_triage'
    assert captured['task_type'] == 'ingestion_triage'
    assert captured['confidence'] == 0.91
    assert captured['source_url'] == 'https://example.com/latest'
    prediction = captured['prediction']
    assert isinstance(prediction, dict)
    assert prediction['decision'] == 'reject'
    assert prediction['source'] == 'ai'
