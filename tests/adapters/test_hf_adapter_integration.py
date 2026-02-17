import os

import pytest

from agents.common.hf_adapter import HFAdapter

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_PROVIDER_TESTS") != "1",
    reason="HF integration tests are gated; set RUN_PROVIDER_TESTS=1 to run",
)


def test_hf_adapter_integration_real_call():
    model = os.environ.get("HF_TEST_MODEL", "sshleifer/tiny-random-gpt2")
    a = HFAdapter(model_name=model, name="hf-int", timeout=60.0, max_retries=2)
    a.load(None)
    out = a.infer("Hello from hf integration test")
    assert isinstance(out, dict) and isinstance(out.get("text"), str)
