from agents.analyst.schemas import (
    AnalysisReport,
    AttributedQuote,
    AttributedStatement,
    AttributionSpan,
    BalanceAssessment,
    PerArticleAnalysis,
)


def test_attributed_statement_to_dict_includes_span():
    statement = AttributedStatement(
        statement_text='A statement',
        confidence=0.88,
        span=AttributionSpan(start=3, end=12, evidence_text='source evidence'),
    )

    payload = statement.to_dict()

    assert payload['statement_text'] == 'A statement'
    assert payload['confidence'] == 0.88
    assert payload['span']['start'] == 3


def test_analysis_report_serializes_traceability_fields():
    report = AnalysisReport(
        cluster_id='cluster-1',
        attributed_statements=[AttributedStatement(statement_text='S1')],
        attributed_quotes=[AttributedQuote(quote_text='Q1')],
        balance_assessment=BalanceAssessment(disputed_topic=True, policy_result='pass'),
        per_article=[
            PerArticleAnalysis(
                article_id='a1',
                statements=[AttributedStatement(statement_text='S2')],
                quotes=[AttributedQuote(quote_text='Q2')],
            )
        ],
    )

    payload = report.to_dict()

    assert payload['attributed_statements'][0]['statement_text'] == 'S1'
    assert payload['attributed_quotes'][0]['quote_text'] == 'Q1'
    assert payload['balance_assessment']['policy_result'] == 'pass'
    assert payload['per_article'][0]['statements'][0]['statement_text'] == 'S2'
