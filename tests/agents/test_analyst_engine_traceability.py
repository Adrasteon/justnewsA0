from unittest.mock import patch

from agents.analyst.analyst_engine import AnalystEngine


def test_extract_attributed_speech_returns_coverage():
    with (
        patch('agents.analyst.analyst_engine._import_spacy', return_value=(None, None)),
        patch('agents.analyst.analyst_engine._import_transformers_pipeline', return_value=(None, None)),
        patch('agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst'),
    ):
        engine = AnalystEngine()

    text = 'John Smith said "The policy is urgent" and analysts estimate inflation rose 2% this month.'
    payload = engine.extract_attributed_speech(text)

    assert 'statements' in payload
    assert 'quotes' in payload
    assert 'attribution_coverage' in payload
    assert payload['attribution_coverage']['total_items'] >= 0


def test_generate_analysis_report_contains_traceability_fields():
    with (
        patch('agents.analyst.analyst_engine._import_spacy', return_value=(None, None)),
        patch('agents.analyst.analyst_engine._import_transformers_pipeline', return_value=(None, None)),
        patch('agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst'),
    ):
        engine = AnalystEngine()

    report = engine.generate_analysis_report(
        ['A spokesperson said "We are prepared". The report suggests conditions improved.'],
        article_ids=['article-1'],
        cluster_id='cluster-1',
        enable_fact_check=False,
    )

    assert 'attributed_statements' in report
    assert 'attributed_quotes' in report
    assert 'balance_assessment' in report
    assert 'attribution_summary' in report
