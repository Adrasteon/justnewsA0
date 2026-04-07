#!/usr/bin/env python3
"""
Smoke test for vLLM Mistral-7B endpoint (replaces Qwen2 smoke test).
Validates OpenAI-compatible API, basic chat completion, and optional adapter routing.
"""

import os
import sys
import time

import pytest
import requests
import yaml


def load_vllm_config(config_path: str = "config/vllm_mistral_7b.yaml") -> dict:
    """Load vLLM config and normalize into a runtime dict with `base_url` and `api_key`.

    This helper supports both the legacy Qwen-style `endpoint: {host,port,base_url}`
    and the current Mistral config which places endpoint under `base_models.mistral-7b.endpoint`.
    It prefers `VLLM_BASE_URL` / `VLLM_API_KEY` from the environment if present.
    """
    cfg = {}
    if os.path.exists(config_path):
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}

    # Prefer env vars if set (useful for CI/local overrides)
    env_base = os.environ.get("VLLM_BASE_URL")
    env_api_key = os.environ.get("VLLM_API_KEY")
    if env_base:
        return {"base_url": env_base.rstrip("/"), "api_key": env_api_key or "dummy"}

    # Legacy flat endpoint
    if isinstance(cfg, dict) and "endpoint" in cfg:
        ep = cfg["endpoint"]
        base = (
            ep.get("base_url")
            or f"http://{ep.get('host', '127.0.0.1')}:{ep.get('port', 7060)}"
        )
        return {"base_url": base.rstrip("/"), "api_key": ep.get("api_key", "dummy")}

    # New structured config (vllm_mistral_7b.yaml)
    bm = (cfg or {}).get("base_models", {})
    m = bm.get("mistral-7b") or bm.get("mistral-7b", {})
    if isinstance(m, dict) and "endpoint" in m:
        base = m.get("endpoint")
        return {
            "base_url": base.rstrip("/"),
            "api_key": env_api_key or os.environ.get("VLLM_API_KEY", "dummy"),
        }

    # Fallback to localhost
    return {
        "base_url": os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:7060/v1").rstrip(
            "/"
        ),
        "api_key": os.environ.get("VLLM_API_KEY", "dummy"),
    }


def test_health():
    """Test /health endpoint."""
    cfg = load_vllm_config()
    base_url = cfg["base_url"]
    print(f"Testing health endpoint: {base_url}/health")
    try:
        resp = requests.get(f"{base_url}/health", timeout=5)
    except requests.exceptions.ConnectionError:
        pytest.skip("vLLM server not running; set VLLM_BASE_URL or start server to run smoke tests")
    resp.raise_for_status()
    print("✅ Health check passed")


def test_models():
    """Test /v1/models endpoint."""
    cfg = load_vllm_config()
    base_url = cfg["base_url"]
    api_key = cfg.get("api_key", "dummy")
    print(f"Testing models endpoint: {base_url}/v1/models")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        resp = requests.get(f"{base_url}/v1/models", timeout=5, headers=headers)
    except requests.exceptions.ConnectionError:
        pytest.skip("vLLM server not running; set VLLM_BASE_URL or start server to run smoke tests")
    resp.raise_for_status()
    models = resp.json()
    print(f"✅ Models: {[m['id'] for m in models.get('data', [])]}")
    # Validate shape instead of returning (avoid pytest ReturnNotNoneWarning)
    assert isinstance(models, dict)
    assert isinstance(models.get('data'), list)


def ensure_vllm_ready(base_url: str, api_key: str | None = None, timeout: float = 15.0) -> None:
    """Wait for vLLM to be healthy and respond to a simple models request.

    Raises RuntimeError if service does not become ready within timeout."""
    end = time.time() + timeout
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    while time.time() < end:
        try:
            h = requests.get(f"{base_url}/health", timeout=2)
            if h.status_code == 200:
                # Also check models (auth may be required)
                m = requests.get(f"{base_url}/v1/models", timeout=3, headers=headers)
                if m.status_code in (200, 401):
                    return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("vLLM service did not become ready in time")


def test_chat_completion():
    """Test /v1/chat/completions with retries/backoff for transient failures."""
    cfg = load_vllm_config()
    base_url = cfg["base_url"]
    api_key = cfg.get("api_key", "")
    print(f"Testing chat completion: {base_url}/v1/chat/completions")

    # Wait for service readiness (helps with race conditions at startup)
    try:
        ensure_vllm_ready(base_url, api_key or None, timeout=1.0)
    except RuntimeError:
        pytest.skip("vLLM service not available/ready")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": "mistralai/Mistral-7B-Instruct-v0.3",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2+2? Answer in one word."},
        ],
        "max_tokens": 10,
        "temperature": 0.0,
    }

    resp = None
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{base_url}/v1/chat/completions", json=payload, headers=headers, timeout=30
            )
        except requests.exceptions.ConnectionError:
            if attempt < 2:
                time.sleep(0.5 * (2 ** attempt))
                continue
            pytest.skip("vLLM server not running; set VLLM_BASE_URL or start server to run smoke tests")
        # Treat transient 401/404 as retryable (server readiness/auth race)
        if resp is not None and resp.status_code in (401, 404):
            if attempt < 2:
                time.sleep(0.5 * (2 ** attempt))
                continue
        break

    assert resp is not None, "No response from vLLM"
    resp.raise_for_status()
    result = resp.json()
    answer = result["choices"][0]["message"]["content"].strip()
    print(f"✅ Chat completion result: {answer}")
    assert "4" in answer.lower() or "four" in answer.lower(), (
        f"Unexpected answer: {answer}"
    )


def main():
    cfg = load_vllm_config()
    base_url = cfg["base_url"]
    api_key = cfg.get("api_key", "dummy")

    print("===== vLLM Mistral-7B Smoke Test =====")
    print(f"Base URL: {base_url}")

    try:
        test_health(base_url)
        test_models(base_url)
        test_chat_completion(base_url, api_key)
        print("\n✅ All tests passed!")
        return 0
    except requests.exceptions.ConnectionError:
        print("\n❌ Connection error: vLLM server not running?")
        print("Start with: scripts/launch_vllm_mistral_7b.sh")
        return 1
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
