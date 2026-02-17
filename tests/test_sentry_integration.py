import importlib
import sys


def test_init_sentry_no_dsn(monkeypatch):
    # Ensure DSN is not set
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    si = importlib.import_module("common.sentry_integration")
    # When no DSN present, initialization should be a no-op and return False
    assert si.init_sentry("test_service") is False


def test_init_sentry_with_fake_sdk(monkeypatch):
    # Provide a fake DSN and a fake sentry_sdk module to avoid network calls
    monkeypatch.setenv("SENTRY_DSN", "http://example.invalid")

    # Create a fake sentry_sdk module in sys.modules
    class FakeLoggingIntegration:
        def __init__(self, level, event_level):
            pass

    class FakeSDK:
        def __init__(self):
            pass

    def fake_init(*args, **kwargs):
        return None

    import types

    fake_module = types.SimpleNamespace(
        LoggingIntegration=FakeLoggingIntegration, init=fake_init
    )
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_module)
    monkeypatch.setitem(
        sys.modules,
        "sentry_sdk.integrations.logging",
        types.SimpleNamespace(LoggingIntegration=FakeLoggingIntegration),
    )

    si = importlib.reload(importlib.import_module("common.sentry_integration"))
    assert si.init_sentry("test_service", logger=None) is True
