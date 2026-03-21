from agents.workflow_orchestrator.lane1_workflow import Lane1Config, Lane1Workflow


class StubDdg:
    def search_related_articles_for_seed(self, seed_article, *, max_results, max_queries_per_seed, excluded_domains=None):
        del excluded_domains
        return {
            'seed_article_id': seed_article.get('article_id'),
            'queries': ['q1'],
            'results': [{'url': f"https://r.example/{seed_article.get('article_id')}"}][:max_results],
            'max_queries': max_queries_per_seed,
        }


def test_lane1_workflow_prefers_bbc_sources():
    workflow = Lane1Workflow(
        ddg_service=StubDdg(),
        config=Lane1Config(seed_count=2, max_related_per_seed=2, require_bbc_first=True),
    )

    articles = [
        {'article_id': 1, 'source_domain': 'cnn.com', 'source_url': 'https://cnn.com/a'},
        {'article_id': 2, 'source_domain': 'bbc.com', 'source_url': 'https://www.bbc.com/b'},
        {'article_id': 3, 'source_domain': 'bbc.co.uk', 'source_url': 'https://www.bbc.co.uk/c'},
    ]

    seeds = workflow.select_seed_articles(articles)
    assert [item['article_id'] for item in seeds] == [2, 3]


def test_lane1_workflow_builds_seed_expansion_plan():
    workflow = Lane1Workflow(
        ddg_service=StubDdg(),
        config=Lane1Config(seed_count=1, max_related_per_seed=3, ddg_max_queries_per_seed=2),
    )

    plan = workflow.build_seed_expansion_plan(
        [{'article_id': 10, 'source_domain': 'bbc.com', 'source_url': 'https://bbc.com/x'}]
    )

    assert plan['lane'] == 'lane1'
    assert plan['seed_count'] == 1
    assert plan['total_related_candidates'] == 1
    assert plan['seed_runs'][0]['seed_article_id'] == 10


def test_lane1_workflow_supports_crawler_article_keys_for_bbc_selection_and_seed_source():
    workflow = Lane1Workflow(
        ddg_service=StubDdg(),
        config=Lane1Config(seed_count=1, max_related_per_seed=2, require_bbc_first=True),
    )

    # Crawler payloads commonly provide url/domain/id keys.
    articles = [
        {'id': 11, 'domain': 'cnn.com', 'url': 'https://cnn.com/a'},
        {'id': 12, 'domain': 'bbc.com', 'url': 'https://www.bbc.com/news/world'},
    ]

    seeds = workflow.select_seed_articles(articles)
    assert [item['id'] for item in seeds] == [12]

    plan = workflow.build_seed_expansion_plan(articles)
    seed_source = plan['seed_runs'][0]['seed_source']
    assert seed_source['article_id'] == 12
    assert seed_source['source_domain'] == 'bbc.com'
    assert seed_source['source_url'] == 'https://www.bbc.com/news/world'
