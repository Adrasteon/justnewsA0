from agents.crawler.crawler_utils import RobotsChecker


def test_robots_checker_allows_by_default(monkeypatch):
    rc = RobotsChecker(ttl_seconds=1)

    # Monkeypatch `_get_parser_for_domain` to return an allow-all parser
    def fake_parser(domain):
        class FakeParser:
            def can_fetch(self, agent, url):
                return True

        return FakeParser()

    monkeypatch.setattr(
        rc, "_get_parser_for_domain", lambda domain: fake_parser(domain)
    )
    assert rc.is_allowed("https://example.com/some/path") is True


def test_robots_checker_denies(monkeypatch):
    rc = RobotsChecker(ttl_seconds=1)

    def fake_parser(domain):
        class FakeParser:
            def can_fetch(self, agent, url):
                return False

        return FakeParser()

    monkeypatch.setattr(
        rc, "_get_parser_for_domain", lambda domain: fake_parser(domain)
    )
    assert rc.is_allowed("https://example.com/private") is False
