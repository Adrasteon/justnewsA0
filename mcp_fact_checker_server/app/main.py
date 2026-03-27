import os
import uuid
from datetime import UTC, datetime

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Load global environment variables
load_dotenv("/app/global.env")

from .models import FactCheckRequest, FactCheckResult, JobRecord, JobStatus
from .service import service

app = FastAPI(
    title="MCP Fact Checker Server",
    description="Enterprise-grade autonomous fact checking service",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

jobs = {}

def verify_api_key(x_api_key: str | None = Header(None)):
    expected_key = os.getenv("FACT_CHECKER_API_KEY")
    if not expected_key:
        # If no key is configured, allow public access (or deny all, but defaulting to allow for dev convenience if var is missing)
        return
    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "mcp_fact_checker"}

@app.post("/fact_check", response_model=FactCheckResult)
async def check_fact_sync(request: FactCheckRequest, api_key: str = Depends(verify_api_key)):
    try:
        result = await service.verify_fact(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/fact_check/async")
async def check_fact_async(request: FactCheckRequest, background_tasks: BackgroundTasks, api_key: str = Depends(verify_api_key)):
    job_id = str(uuid.uuid4())
    jobs[job_id] = JobRecord(job_id=job_id, status=JobStatus.PENDING, created_at=datetime.now(UTC))
    background_tasks.add_task(process_job, job_id, request)
    return {"job_id": job_id, "status": "pending"}

@app.get("/fact_check/{job_id}", response_model=JobRecord)
async def get_job_status(job_id: str, api_key: str = Depends(verify_api_key)):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]

@app.get("/metrics/domains")
async def get_domain_metrics(api_key: str = Depends(verify_api_key)):
    """Retrieve historical reliability metrics for crawled domains."""
    return await service.get_domain_metrics_summary()

async def process_job(job_id: str, request: FactCheckRequest):
    jobs[job_id].status = JobStatus.PROCESSING
    try:
        result = await service.verify_fact(request)
        jobs[job_id].result = result
        jobs[job_id].status = JobStatus.COMPLETED
    except Exception as e:
        jobs[job_id].error = str(e)
        jobs[job_id].status = JobStatus.FAILED
