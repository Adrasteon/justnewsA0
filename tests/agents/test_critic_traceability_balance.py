from agents.critic.tools import evaluate_traceability_balance


def test_traceability_balance_fails_hard_gate_when_sides_missing():
    report = {
        'attributed_statements': [
            {
                'statement_text': 'Policy is necessary',
                'speaker_name': 'Minister A',
                'perspective_label': 'pro',
                'counts_as_factual_corroboration': True,
            }
        ],
        'attributed_quotes': [],
    }

    result = evaluate_traceability_balance(
        report,
        min_distinct_sides=2,
        disputed_topic_hard_gate=True,
    )

    assert result['gate_result'] == 'fail'
    assert 'insufficient_distinct_sides' in result['missing_reasons']


def test_traceability_balance_passes_with_two_sides_and_attribution():
    report = {
        'attributed_statements': [
            {
                'statement_text': 'Policy is necessary',
                'speaker_name': 'Minister A',
                'perspective_label': 'pro',
                'counts_as_factual_corroboration': True,
            },
            {
                'statement_text': 'Policy harms jobs',
                'speaker_name': 'Union B',
                'perspective_label': 'con',
                'counts_as_factual_corroboration': True,
            },
        ],
        'attributed_quotes': [
            {
                'quote_text': 'We disagree',
                'attribution_text': 'Union B said',
                'perspective_label': 'con',
                'counts_as_factual_corroboration': True,
            }
        ],
    }

    result = evaluate_traceability_balance(
        report,
        min_distinct_sides=2,
        disputed_topic_hard_gate=True,
    )

    assert result['gate_result'] == 'pass'
    assert result['metrics']['distinct_sides_found'] == 2
