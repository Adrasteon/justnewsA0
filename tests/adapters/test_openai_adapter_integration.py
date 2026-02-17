import os

import pytest

from agents.common.openai_adapter import OpenAIAdapter

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY") or os.environ.get("RUN_PROVIDER_TESTS") != "1",
    reason="OpenAI integration tests are gated; set OPENAI_API_KEY and RUN_PROVIDER_TESTS=1 to run",
)


def test_openai_adapter_integration_real_call():
    api_key = os.environ.get("OPENAI_API_KEY")
    a = OpenAIAdapter(
        api_key=api_key,
        name="openai-int",
        model=os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo"),
        timeout=20.0,
        max_retries=2,
    )
    a.load(None)
    out = a.infer("Hello from integration test — short ping")
    assert (
        isinstance(out, dict)
        and isinstance(out.get("text"), str)
        and len(out.get("text")) > 0
    )
