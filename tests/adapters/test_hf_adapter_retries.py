import pytest

from agents.common.adapter_base import AdapterError
from agents.common.hf_adapter import HFAdapter


class FakeTokenizer:
    def __call__(self, prompt, return_tensors=None):
        return {"input_ids": [[1, 2, 3]]}

    def decode(self, arr, skip_special_tokens=True):
        return "decoded text"


class FakeModel:
    def __init__(self, fail_times=1):
        self.calls = 0
        self.fail_times = fail_times

    def generate(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("transient-hf-error")
        return [[1, 2, 3]]


def test_hf_adapter_retries_succeeds(monkeypatch):
    a = HFAdapter(
        model_name="gpt-test",
        name="test-hf",
        timeout=1.0,
        max_retries=3,
        backoff_base=0.01,
    )
    # simulate as if adapter was loaded
    a.mark_loaded()
    a._tokenizer = FakeTokenizer()
    a._model = FakeModel(fail_times=1)

    out = a.infer("hello world")
    assert isinstance(out, dict)
    assert out["text"] == "decoded text"


def test_hf_adapter_retries_exhaust(monkeypatch):
    a = HFAdapter(
        model_name="gpt-test",
        name="test-hf",
        timeout=1.0,
        max_retries=2,
        backoff_base=0.01,
    )
    a.mark_loaded()
    a._tokenizer = FakeTokenizer()
    a._model = FakeModel(fail_times=5)  # will keep failing

    with pytest.raises(AdapterError):
        a.infer("hello world")
