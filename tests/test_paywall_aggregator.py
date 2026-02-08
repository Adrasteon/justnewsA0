import os

from agents.crawler.paywall_aggregator import increment_and_check, reset_counts


def test_aggregator_threshold(tmp_path):
    dbfile = str(tmp_path / "paywall.db")
    # ensure clean
    reset_counts(dbfile)
    # monkeypatch environment to point at this test DB
    os.environ["CRAWL4AI_PAYWALL_AGG_DB"] = dbfile

    domain = "example.com"
    # threshold 3 -> only after 3 increments reached
    for i in range(1, 4):
        count, reached = increment_and_check(domain, threshold=3)
        assert count == i
        if i < 3:
            assert reached is False
        else:
            assert reached is True
