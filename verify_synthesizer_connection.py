
import asyncio
import httpx
import sys

SYNTHESIZER_URL = "http://localhost:8005/summarize_article"

# Mock tool call structure
payload = {
    "args": [123], # Fake article ID
    "kwargs": {}
}

async def test_summary():
    print(f"Testing connection to {SYNTHESIZER_URL}...")
    async with httpx.AsyncClient() as client:
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < 60:
            try:
                # We expect a 500 or 404 because article 123 might not exist, 
                # but we want to fail on TIMEOUT or CONNECTION ERROR.
                response = await client.post(SYNTHESIZER_URL, json=payload, timeout=2.0)
                print(f"Response Status: {response.status_code}")
                # print(f"Response Body: {response.text}")
                
                if response.status_code in [200, 404, 500]:
                    print("SUCCESS: Connection established and server responded.")
                    sys.exit(0)
            except (httpx.ConnectError, httpx.ReadTimeout):
                print(".", end="", flush=True)
                await asyncio.sleep(1)
            except Exception as e:
                print(f"FAILURE: Unexpected error: {e}")
                sys.exit(1)
        print("\nFAILURE: Timed out waiting for service.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_summary())
