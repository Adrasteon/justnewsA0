import sys
import types

from agents.sites.generic_site_crawler import SiteConfig


def make_fake_crawl4ai_with_links(links_internal=None):
    # Build a minimal fake crawl4ai module with AsyncWebCrawler that returns
    # a result object with `.links` property shaped like Crawl4AI output.
    mod = types.SimpleNamespace()

    class AsyncWebCrawler:
        def __init__(self, config=None):
            self.config = config

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def arun(self, url, config=None):
            class Res:
                pass

            res = Res()
            res.url = url
            res.title = "mock"
            res.html = "<html></html>"
            res.markdown = None
            # Provide a `links` object that contains `internal` candidates
            res.links = types.SimpleNamespace(internal=links_internal or [])
            res.status_code = 200
            res.success = True
            return res

    mod.AsyncWebCrawler = AsyncWebCrawler
    # Minimal stub for required classes used by adapter
    mod.CacheMode = types.SimpleNamespace(BYPASS=object())

    class CrawlerRunConfig:
        def __init__(self, **kwargs):
            pass

    mod.CrawlerRunConfig = CrawlerRunConfig
    return mod


def test_select_link_candidates_respects_follow_external(monkeypatch):
    fake_crawl4ai = make_fake_crawl4ai_with_links()
    monkeypatch.setitem(sys.modules, "crawl4ai", fake_crawl4ai)

    from agents.crawler.crawl4ai_adapter import CrawlContext, _select_link_candidates

    # Target site domain
    site_config = SiteConfig(
        {"domain": "example.com", "start_url": "https://example.com/"}
    )

    # Candidates include an internal (same domain) and an external link
    candidates = [
        {"href": "https://example.com/path1", "total_score": 1.0},
        {"href": "https://evil.com/malicious", "total_score": 0.5},
    ]

    # Case: follow_external = False -> only allowed domain should be returned
    ctx = CrawlContext(
        site_config=site_config,
        profile={},
        max_articles=5,
        follow_internal_links=True,
        page_budget=10,
        follow_external=False,
    )
    sel = _select_link_candidates(candidates, ctx, visited=set(), remaining_budget=10)
    assert any("example.com/path1" in u for u in sel)
    assert not any("evil.com" in u for u in sel)

    # Case: follow_external = True -> both links may be returned (subject to budget)
    ctx2 = CrawlContext(
        site_config=site_config,
        profile={},
        max_articles=5,
        follow_internal_links=True,
        page_budget=10,
        follow_external=True,
    )
    sel2 = _select_link_candidates(candidates, ctx2, visited=set(), remaining_budget=10)
    assert any("example.com/path1" in u for u in sel2)
    assert any("evil.com/malicious" in u for u in sel2)
