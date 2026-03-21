from common.ddg_search_service import DdgSearchService


def test_build_seed_queries_deduplicates_and_caps():
    service = DdgSearchService()
    queries = service.build_seed_queries(
        seed_title='BBC headline',
        entities=['London', 'London'],
        claims=['Key claim', 'Key claim'],
        max_queries=3,
    )

    assert queries == ['BBC headline', 'BBC headline London', 'Key claim']


def test_search_related_articles_for_seed_filters_duplicates(monkeypatch):
    service = DdgSearchService()

    def fake_search_web(query, *, max_results=None, excluded_domains=None, required_distinct_domains=None):
        del query, max_results, excluded_domains, required_distinct_domains
        return [
            type('Result', (), {'url': 'https://example.com/a', 'to_dict': lambda self: {'url': self.url}})(),
            type('Result', (), {'url': 'https://example.com/a', 'to_dict': lambda self: {'url': self.url}})(),
            type('Result', (), {'url': 'https://example.com/b', 'to_dict': lambda self: {'url': self.url}})(),
        ]

    monkeypatch.setattr(service, 'search_web', fake_search_web)

    payload = service.search_related_articles_for_seed(
        {'article_id': 1, 'title': 'Seed title'},
        max_results=5,
    )

    assert payload['seed_article_id'] == 1
    assert len(payload['results']) == 2
    assert {item['url'] for item in payload['results']} == {
        'https://example.com/a',
        'https://example.com/b',
    }


def test_search_web_filters_low_quality_domains(monkeypatch):
    service = DdgSearchService(max_results_default=10)

    def fake_run_ddg_text(query, max_results):
        del query, max_results
        return [
            {'href': 'https://forumgratuit.org/topic/abc', 'title': 'forum'},
            {'href': 'https://eu.forums.blizzard.com/t/topic/123', 'title': 'blizzard forum'},
            {'href': 'https://www.reuters.com/world/europe/story', 'title': 'reuters'},
            {'href': 'https://apnews.com/article/abc', 'title': 'ap'},
        ]

    monkeypatch.setattr(service, '_run_ddg_text', fake_run_ddg_text)

    results = service.search_web('seed query', max_results=10)
    urls = [item.url for item in results]

    assert 'https://forumgratuit.org/topic/abc' not in urls
    assert 'https://eu.forums.blizzard.com/t/topic/123' not in urls
    assert 'https://www.reuters.com/world/europe/story' in urls
    assert 'https://apnews.com/article/abc' in urls


def test_search_web_requires_news_like_domains(monkeypatch):
    service = DdgSearchService(max_results_default=10)

    def fake_run_ddg_text(query, max_results):
        del query, max_results
        return [
            {'href': 'https://apps.apple.com/us/app/something', 'title': 'app store'},
            {'href': 'https://www.open.ac.uk/research', 'title': 'open university'},
            {'href': 'https://www.reuters.com/world/story', 'title': 'reuters'},
            {'href': 'https://apnews.com/article/xyz', 'title': 'ap'},
        ]

    monkeypatch.setattr(service, '_run_ddg_text', fake_run_ddg_text)

    results = service.search_web('seed query', max_results=10)
    urls = [item.url for item in results]

    assert 'https://apps.apple.com/us/app/something' not in urls
    assert 'https://www.open.ac.uk/research' not in urls
    assert 'https://www.reuters.com/world/story' in urls
    assert 'https://apnews.com/article/xyz' in urls
