import sys
import types

from fastapi.testclient import TestClient


def make_fake_crawl4ai():
    mod = types.SimpleNamespace()

    class BrowserConfig:
        def __init__(self, **kwargs):
            # expose kwargs as attributes for downstream use
            for k, v in kwargs.items():
                try:
                    setattr(self, k, v)
                except Exception:
                    pass

    class AsyncWebCrawler:
        def __init__(self, config=None):
            self.config = config

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def arun(self, url, config=None):
            # simulate a crawl result that reflects the passed config
            class Res:
                pass

            res = Res()
            ua = getattr(self.config, "user_agent", None)
            proxy = getattr(self.config, "proxy", None)
            res.url = url
            res.title = "Mock Title"
            # html includes UA and proxy markers so tests can assert they were used
            res.html = f"HTML_BODY UA={ua} PROXY={proxy}"
            res.markdown = "# mock"
            res.links = []
            res.status_code = 200
            res.success = True
            return res

    mod.BrowserConfig = BrowserConfig
    mod.AsyncWebCrawler = AsyncWebCrawler
    # CacheMode and CrawlerRunConfig are not needed by the fake but present for imports
    mod.CacheMode = types.SimpleNamespace(BYPASS=object())

    class CrawlerRunConfig:
        def __init__(self, **kwargs):
            pass

    mod.CrawlerRunConfig = CrawlerRunConfig
    return mod


def test_crawl_includes_ua_proxy_and_modal(monkeypatch):
    # Prepare fake crawl4ai module
    fake_crawl4ai = make_fake_crawl4ai()
    monkeypatch.setitem(sys.modules, "crawl4ai", fake_crawl4ai)

    # Provide a fake UA rotation module
    ua_mod = types.SimpleNamespace()

    class UserAgentConfig:
        def __init__(self, pool=None, per_domain_overrides=None, default=None):
            self.pool = pool or []

    class UserAgentProvider:
        def __init__(self, cfg):
            self.cfg = cfg

        def choose(self, **kwargs):
            return "MOCK-UA/1.0"

    ua_mod.UserAgentConfig = UserAgentConfig
    ua_mod.UserAgentProvider = UserAgentProvider
    monkeypatch.setitem(sys.modules, "agents.crawler.enhancements.ua_rotation", ua_mod)

    # Provide a fake proxy manager
    proxy_mod = types.SimpleNamespace()

    class Proxy:
        def __init__(self, url):
            self.url = url

        def __str__(self):
            return self.url

    class ProxyManager:
        def next_proxy(self):
            return Proxy("socks5://1.2.3.4:1080")

    proxy_mod.ProxyManager = ProxyManager
    monkeypatch.setitem(
        sys.modules, "agents.crawler.enhancements.proxy_manager", proxy_mod
    )

    # Provide a fake modal handler that marks HTML as cleaned
    modal_mod = types.SimpleNamespace()

    class ModalHandler:
        def process(self, html):
            class R:
                def __init__(self, cleaned_html):
                    self.cleaned_html = cleaned_html

            return R(cleaned_html=html + "<!--MODAL_CLEANED-->")

    modal_mod.ModalHandler = ModalHandler
    monkeypatch.setitem(
        sys.modules, "agents.crawler.enhancements.modal_handler", modal_mod
    )

    # Fake paywall detector returning no paywall
    pw_mod = types.SimpleNamespace()

    class PaywallDetector:
        async def analyze(self, url, html, text=None):
            class R:
                is_paywall = False
                confidence = 0.0
                reasons = []
                should_skip = False

            return R()

    pw_mod.PaywallDetector = PaywallDetector
    monkeypatch.setitem(
        sys.modules, "agents.crawler.enhancements.paywall_detector", pw_mod
    )

    # Provide crawler utils (record_paywall_detection, RobotsChecker, RateLimiter)
    utils_mod = types.SimpleNamespace()

    def record_paywall_detection(*args, **kwargs):
        # noop for test
        return None

    class RobotsChecker:
        def is_allowed(self, url):
            return True

    class RateLimiter:
        def acquire(self, domain):
            return None

    utils_mod.record_paywall_detection = record_paywall_detection
    utils_mod.RobotsChecker = RobotsChecker
    utils_mod.RateLimiter = RateLimiter
    monkeypatch.setitem(sys.modules, "agents.crawler.crawler_utils", utils_mod)

    # Provide a noop paywall aggregator so server takes the aggregator branch but does nothing
    agg_mod = types.SimpleNamespace()

    def increment_and_check(domain, threshold=3):
        return (1, False)

    agg_mod.increment_and_check = increment_and_check
    monkeypatch.setitem(sys.modules, "agents.crawler.paywall_aggregator", agg_mod)

    # Now import the app and run the client
    from agents.c4ai import server

    client = TestClient(server.app)

    resp = client.post(
        "/crawl",
        json={
            "urls": ["http://example.com/article"],
            "mode": "standard",
            "use_llm": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "results" in data and len(data["results"]) == 1
    res = data["results"][0]

    # The fake crawler's html contains the UA and PROXY markers
    assert "UA=MOCK-UA/1.0" in res["html"]
    assert "PROXY=socks5://1.2.3.4:1080" in res["html"]

    # The modal handler appends the marker <!--MODAL_CLEANED--> to html
    assert "<!--MODAL_CLEANED-->" in res["html"]
