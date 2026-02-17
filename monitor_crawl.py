import httpx
import asyncio
import json
import sys

AGENT_URL = "http://localhost:8022/get_job_status"
JOB_ID = sys.argv[1] if len(sys.argv) > 1 else ""

async def check_status():
    if not JOB_ID:
        print("Please provide a Job ID.")
        return

    print(f"Checking status for Job {JOB_ID}...")
    
    payload = {
        "args": [],
        "kwargs": {
            "job_id": JOB_ID
        }
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(AGENT_URL, json=payload)
            print(f"Status: {resp.status_code}")
            try:
                data = resp.json()
                status = data.get("status")
                result = data.get("result", {})
                sites_crawled = result.get("sites_crawled", 0)
                articles = result.get("total_articles", 0)
                
                print(f"Job Status: {status}")
                print(f"Sites Crawled: {sites_crawled}")
                print(f"Articles Found: {articles}")
                # print(f"Full Body: {json.dumps(data, indent=2)}") 
            except Exception:
                print(f"Body: {resp.text}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_status())
