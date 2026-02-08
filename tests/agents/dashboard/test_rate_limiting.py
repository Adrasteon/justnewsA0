import importlib
from types import SimpleNamespace


def test_in_memory_rate_limiter(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    rate = importlib.import_module("agents.dashboard.rate_limit")

    class DummyRequest:
        def __init__(self, host):
            self.client = SimpleNamespace(host=host)

    req = DummyRequest("1.2.3.4")
    # ensure in-memory cleaned
    rate._windows.clear()
    # limit 3 requests
    for _i in range(3):
        assert rate.allow_request(req, max_requests=3, window_seconds=60)
    # fourth should fail
    assert not rate.allow_request(req, max_requests=3, window_seconds=60)


def test_redis_rate_limiter(monkeypatch):
    rate = importlib.import_module("agents.dashboard.rate_limit")

    class DummyRequest:
        def __init__(self, host):
            self.client = SimpleNamespace(host=host)

    class FakeRedis:
        def __init__(self):
            self._c = {}

        def incr(self, key):
            self._c[key] = self._c.get(key, 0) + 1
            return self._c[key]

        def expire(self, key, ttl):
            # No-op for fake
            return True

    # Monkeypatch _get_redis_client to return our fake redis
    monkeypatch.setattr(
        "agents.dashboard.rate_limit._get_redis_client", lambda: FakeRedis()
    )

    req = DummyRequest("2.2.2.2")
    # limit 2 requests
    assert rate.allow_request_redis(req, max_requests=2, window_seconds=60)
    assert rate.allow_request_redis(req, max_requests=2, window_seconds=60)
    assert not rate.allow_request_redis(req, max_requests=2, window_seconds=60)
