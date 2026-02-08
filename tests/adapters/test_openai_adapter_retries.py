import sys
import types

import pytest

from agents.common.adapter_base import AdapterError
from agents.common.openai_adapter import OpenAIAdapter


def test_openai_adapter_retries_succeeds(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")
    # Inject fake openai module to simulate transient errors
    calls = {"count": 0}

    class FakeChoices:
        def __init__(self, text):
            from types import SimpleNamespace

            self.message = SimpleNamespace(content=text)

    class FakeChat:
        @staticmethod
        def create(**kwargs):
            calls["count"] += 1
            if calls["count"] < 2:
                raise RuntimeError("transient-error")
            return types.SimpleNamespace(choices=[FakeChoices("ok from fake")])

    fake_mod = types.SimpleNamespace(ChatCompletion=FakeChat)
    monkeypatch.setitem(sys.modules, "openai", fake_mod)

    a = OpenAIAdapter(
        api_key="x",
        name="test-openai",
        model="gpt-test",
        timeout=1.0,
        max_retries=3,
        backoff_base=0.01,
    )
    a.load(None)
    out = a.infer("hello")
    assert isinstance(out, dict)
    assert out["text"].startswith("ok from fake")
    assert calls["count"] == 2


def test_openai_adapter_retries_exhaust(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")
    calls = {"count": 0}

    class FakeChat:
        @staticmethod
        def create(**kwargs):
            calls["count"] += 1
            raise RuntimeError("permanent-error")

    fake_mod = types.SimpleNamespace(ChatCompletion=FakeChat)
    monkeypatch.setitem(sys.modules, "openai", fake_mod)

    a = OpenAIAdapter(
        api_key="x",
        name="test-openai",
        model="gpt-test",
        timeout=1.0,
        max_retries=2,
        backoff_base=0.01,
    )
    a.load(None)
    with pytest.raises(AdapterError):
        a.infer("hello")
    assert calls["count"] == 2
