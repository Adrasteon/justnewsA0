
import os
from agents.common.openai_adapter import OpenAIAdapter
from common.observability import get_logger

# Manually load env for this test script so it matches what the agent sees
from dotenv import load_dotenv
load_dotenv("/home/adra/justnewsA0/global.env")

logger = get_logger("debug_adapter")

def debug_adapter():
    key = os.environ.get("VLLM_API_KEY", "unused")
    print(f"DEBUG: VLLM_API_KEY env var is: '{key}'")
    

    adapter = OpenAIAdapter(
        name="test_adapter",
        model=os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ"),
        base_url=os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8010/v1"),
        api_key=key,
        timeout=10.0
    )
    adapter.load() # Load the client
    
    print(f"DEBUG: Adapter configured with api_key: '{adapter._client.api_key}'")
    print("DEBUG: Attempting infer...")
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url=os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8010/v1"),
            api_key=key,
        )
        resp = client.chat.completions.create(
            model=os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ"),
            messages=[{"role": "user", "content": "Hello"}],
        )
        print(f"DEBUG: Success! Response: {resp.choices[0].message.content[:50]}...")
    except Exception as e:
        print(f"DEBUG: Failed! {e}")

if __name__ == "__main__":
    debug_adapter()
