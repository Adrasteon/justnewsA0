
import os
import sys
import time

import requests

from agents.common.mistral_adapter import MistralAdapter

# Set Env
os.environ["VLLM_BASE_URL"] = "http://localhost:8010/v1"
os.environ["VLLM_MODEL"] = "Qwen/Qwen2.5-14B-Instruct-AWQ"
# Need to set this to ensure OpenAIAdapter picks it up if not passed explicitly in shim (though shim does now)
# os.environ["OPENAI_API_BASE"] = "http://localhost:8010/v1"

def wait_for_server():
    print("Waiting for vLLM to be ready...")
    url = "http://localhost:8010/v1/models"
    for i in range(120):
        try:
            resp = requests.get(url)
            if resp.status_code == 200:
                print("Server is READY!")
                return True
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
        if i % 10 == 0:
            print(f"Waiting... {i}s")
    return False

def test_shim():
    if not wait_for_server():
        print("Server failed to start.")
        sys.exit(1)

    print("Initializing MistralAdapter (Shim)...")
    adapter = MistralAdapter(agent="shim_tester", adapter_name="test_shim")

    print("Loading...")
    adapter.load()

    print("Inferring...")
    try:
        response = adapter.infer("Hello Qwen, are you there? Reply 'Yes'.")
        print("Response:", response)
        if "text" in response and response["text"]:
            print("SUCCESS: Received text response.")
        else:
            print("FAILURE: Response format unexpected:", response)
    except Exception as e:
        print(f"FAILURE: Inference error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_shim()
