from agents.crawler.crawler_engine import CrawlerEngine


def test_build_lane1_expansion_candidates_dedupes_and_keeps_provenance(monkeypatch):
    monkeypatch.setenv('UNIFIED_CRAWLER_LANE1_EXPANSION_MAX_CANDIDATES', '10')
    engine = CrawlerEngine.__new__(CrawlerEngine)

    lane1_plan = {
        'seed_runs': [
            {
                'seed_source': {'article_id': 42, 'source_domain': 'bbc.com'},
                'queries': ['q1'],
                'results': [
                    {'url': 'https://example.com/a', 'title': 'A', 'snippet': 'sa'},
                    {'url': 'https://example.com/a', 'title': 'A-dup', 'snippet': 'sa2'},
                    {'url': 'https://example.com/b', 'title': 'B', 'snippet': 'sb'},
                ],
            }
        ]
    }

    candidates = CrawlerEngine._build_lane1_expansion_candidates(engine, lane1_plan)

    assert len(candidates) == 2
    assert candidates[0]['publisher_meta']['seed_article_id'] == 42
    assert candidates[0]['publisher_meta']['retrieval_mode'] == 'ddg_comparative_expansion'
    assert candidates[1]['url'] == 'https://example.com/b'
