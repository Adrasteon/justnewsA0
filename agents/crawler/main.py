"""
Main file for the Crawler Agent.
Unified production crawling agent with MCP integration.
"""
# main.py for Crawler Agent

import asyncio
import concurrent.futures
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from agents.common.mcp_bus_client import MCPBusClient
from common.metrics import JustNewsMetrics
from common.observability import bootstrap_observability, get_logger
from common.otel import init_telemetry, instrument_fastapi

# Compatibility: expose create_database_service for tests that patch agent modules
try:
    from database.utils.migrated_database_utils import (
        create_database_service,  # type: ignore
    )
except Exception:
    create_database_service = None

from .crawler_engine import CrawlerEngine
from .job_store import (
    clear_all,
    create_job,
    get_job,
    recover_running_jobs,
    set_error,
    set_result,
)
from .job_store import list_jobs as jobstore_list_jobs
from .tools import get_crawler_info

# Configure logging
# logger = get_logger(__name__) # Replaced by bootstrap
bootstrap_observability("crawler", level=20) # INFO
logger = get_logger(__name__)

ready = False
# In-memory storage of crawl job statuses
crawl_jobs: dict[str, Any] = {}

# Map job_id -> asyncio.Task for running background crawl jobs so they can be cancelled
crawl_task_map: dict[str, asyncio.Task] = {}
cancel_requested_jobs: set[str] = set()

# Environment variables
CRAWLER_AGENT_PORT = int(os.environ.get("CRAWLER_AGENT_PORT", 8015))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")


def require_api_token(
    authorization: str | None = Header(None), x_api_token: str | None = Header(None)
):
    """Require an API token if `CRAWLER_API_TOKEN` is set; accept Authorization Bearer or X-Api-Token.

    If the env var is not set, no auth is required (backwards compatible).
    """
    expected = os.environ.get("CRAWLER_API_TOKEN")
    if not expected:
        return None
    token = None
    if authorization:
        if authorization.lower().startswith("bearer "):
            token = authorization.split(None, 1)[1].strip()
        else:
            token = authorization.strip()
    if not token and x_api_token:
        token = x_api_token.strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing API token")
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid API token")
    return None


# Security configuration
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS", "http://localhost:3000,http://localhost:8000"
).split(",")


async def run_crawl_background(
    job_id: str,
    domains: list[str],
    max_articles: int,
    concurrent: int,
    profile_overrides: dict[str, dict[str, Any]] | None,
):
    """Background task to execute a crawl job."""
    try:
        cancel_requested_jobs.discard(job_id)
        crawl_jobs[job_id]["status"] = "running"
        logger.info(f"Starting background crawl task {job_id} for domains: {domains}")
        async with CrawlerEngine() as crawler:
            await crawler._load_ai_models()
            result = await crawler.run_unified_crawl(
                domains,
                max_articles,
                concurrent,
                profile_overrides=profile_overrides,
            )
        if job_id in cancel_requested_jobs:
            crawl_jobs[job_id] = {"status": "cancelled"}
            try:
                set_error(job_id, "cancelled by user")
            except Exception:
                pass
            return
        # Store result in job status
        try:
            set_result(job_id, result)
            crawl_jobs[job_id] = {"status": "completed"}
        except Exception:
            # best-effort fallback to memory for visibility
            crawl_jobs[job_id] = {"status": "completed", "result": result}
        logger.info(
            f"Background crawl {job_id} complete. Articles: {len(result.get('articles', []))}"
        )
    except Exception as e:
        if job_id in cancel_requested_jobs:
            crawl_jobs[job_id] = {"status": "cancelled"}
            try:
                set_error(job_id, "cancelled by user")
            except Exception:
                pass
            return
        try:
            set_error(job_id, str(e))
        except Exception:
            crawl_jobs[job_id] = {"status": "failed", "error": str(e)}
        logger.error(f"Background crawl {job_id} failed: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")


def run_crawl_background_thread(
    job_id: str,
    domains: list[str],
    max_articles: int,
    concurrent: int,
    profile_overrides: dict[str, dict[str, Any]] | None,
):
    """Run crawl in a dedicated thread event loop to keep API handlers responsive."""
    asyncio.run(
        run_crawl_background(
            job_id, domains, max_articles, concurrent, profile_overrides
        )
    )


def get_job_fast(job_id: str, timeout_seconds: float = 0.35):
    """Best-effort persisted job lookup with timeout to avoid API hangs."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(get_job, job_id)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            logger.warning("Timed out loading persisted job status for %s", job_id)
            return None
        except Exception:
            return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Crawler agent is starting up.")

    # Initialize OpenTelemetry
    init_telemetry("crawler-agent")
    instrument_fastapi(app)

    mcp_bus_client = MCPBusClient(base_url=MCP_BUS_URL)
    try:
        mcp_bus_client.register_agent(
            agent_name="crawler",
            agent_address=f"http://localhost:{CRAWLER_AGENT_PORT}",
            tools=[
                "unified_production_crawl",
                "get_crawler_info",
                "get_performance_metrics",
                "get_jobs",
                "get_job_status",
            ],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")
    global ready
    # Recover any jobs left in 'running' state after a previous service restart
    try:
        recovered = recover_running_jobs("service restart")
        if recovered > 0:
            logger.info(
                "Recovered %s interrupted running jobs during startup", recovered
            )
    except Exception as e:
        logger.debug("Job recovery step failed: %s", e)
    ready = True
    yield
    logger.info("Crawler agent is shutting down.")


app = FastAPI(
    lifespan=lifespan,
    title="Crawler Agent",
    description="Unified production crawling agent",
)

# Initialize metrics
metrics = JustNewsMetrics("crawler")

# Security middleware
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Metrics middleware (must be added after CORS middleware)
app.middleware("http")(metrics.request_middleware)


class ToolCall(BaseModel):
    args: list[Any]
    kwargs: dict[str, Any]


@app.post("/unified_production_crawl")
async def unified_production_crawl_endpoint(
    call: ToolCall,
    background_tasks: BackgroundTasks,
    token_ok: None = Depends(require_api_token),
):
    """
    Enqueue a background unified production crawl job and return immediately with a job ID.
    """
    # Generate a unique job identifier
    job_id = uuid.uuid4().hex
    # Initialize job status
    try:
        create_job(job_id, status="pending")
    except Exception as e:
        logger.debug("Failed to persist job creation: %s", e)
    crawl_jobs[job_id] = {"status": "pending"}
    # Extract parameters
    domains = call.args[0] if call.args else call.kwargs.get("domains", [])
    max_articles = call.kwargs.get("max_articles_per_site", 25)
    concurrent = call.kwargs.get("concurrent_sites", 3)
    logger.info(f"Enqueueing background crawl job {job_id} for {len(domains)} domains")
    profile_overrides = call.kwargs.get("profile_overrides")

    # Enqueue background task by creating an asyncio.Task so it can be cancelled later
    task = asyncio.create_task(
        asyncio.to_thread(
            run_crawl_background_thread,
            job_id, domains, max_articles, concurrent, profile_overrides
        )
    )
    crawl_task_map[job_id] = task

    # When the background task completes, remove it from the task map
    def _on_task_done(t: asyncio.Task, jid: str = job_id):
        try:
            # Observe exception to avoid "Task exception was never retrieved"
            _ = t.exception()
        except Exception:
            pass
        crawl_task_map.pop(jid, None)

    task.add_done_callback(_on_task_done)

    # Return accepted status with job ID
    return JSONResponse(
        status_code=202, content={"status": "accepted", "job_id": job_id}
    )


@app.post("/stop_job/{job_id}")
async def stop_job(job_id: str):
    """Stop a single active crawl job by id. Cancels running tasks and updates job store.

    Returns 200 if a cancellation was requested, 404 if the job id is unknown.
    """
    # Try to cancel a running task
    if job_id in crawl_task_map:
        task = crawl_task_map[job_id]
        cancel_requested_jobs.add(job_id)
        logger.info(f"Cancelling running crawl job {job_id}")
        task.cancel()
        try:
            # Allow a short grace period for cleanup
            await asyncio.wait_for(task, timeout=5)
        except TimeoutError:
            logger.debug(
                f"Timed out waiting for job {job_id} to cancel; task may still be cleaning up"
            )
        except asyncio.CancelledError:
            logger.debug(f"Task for job {job_id} cancelled")

        try:
            set_error(job_id, "cancelled by user")
        except Exception:
            # Best-effort fallback to in-memory status
            if job_id in crawl_jobs:
                crawl_jobs[job_id]["status"] = "cancelled"

        return {"status": "cancelled", "job_id": job_id}

    # If there's no active task, but a persisted job exists, mark it cancelled
    try:
        job = get_job(job_id)
        if job is not None:
            # Only update if job is not already completed/failed
            current = job.get("status")
            if current in {"pending", "running"}:
                set_error(job_id, "cancelled by user")
                return {"status": "cancelled", "job_id": job_id}
            return {"status": current, "job_id": job_id}
    except Exception:
        pass

    # Lastly check in-memory tracking
    if job_id in crawl_jobs:
        status = crawl_jobs[job_id].get("status")
        if status in ["running", "pending"]:
            crawl_jobs[job_id]["status"] = "cancelled"
            try:
                set_error(job_id, "cancelled by user")
            except Exception:
                pass
            return {"status": "cancelled", "job_id": job_id}

    raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")


@app.get("/job_status/{job_id}")
def job_status(job_id: str, token_ok: None = Depends(require_api_token)):
    """Retrieve status and result (if completed) for a crawl job."""
    cached = crawl_jobs.get(job_id)
    if isinstance(cached, dict):
        cached_status = str(cached.get("status", "")).strip().lower()
        cached_has_result = cached.get("result") is not None
        if cached_status in {"running", "pending"} or cached_has_result:
            return cached

    # Prefer persisted job view
    job = get_job_fast(job_id)
    if job is not None:
        return job

    if cached is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return cached


@app.get("/jobs")
def list_jobs(token_ok: None = Depends(require_api_token)):
    """List all current crawl job IDs with their status (without full results)."""
    # Return a mapping of job_id to status only for brevity
    try:
        return jobstore_list_jobs()  # use job_store list_jobs
    except Exception:
        return {job_id: info.get("status") for job_id, info in crawl_jobs.items()}


@app.post("/clear_jobs")
def clear_jobs(token_ok: None = Depends(require_api_token)):
    """Clear completed and failed jobs from memory."""
    global crawl_jobs
    try:
        removed = clear_all()
    except Exception:
        # Fallback: clear in-memory only
        removed = len(crawl_jobs)
        crawl_jobs.clear()
    return {"cleared_jobs": [], "message": f"Cleared {removed} jobs"}


@app.post("/reset_crawler")
def reset_crawler(token_ok: None = Depends(require_api_token)):
    """Completely reset the crawler state - clear all jobs and reset performance metrics."""
    global crawl_jobs

    # Clear all jobs
    cleared_jobs = list(crawl_jobs.keys())
    crawl_jobs.clear()

    # Reset performance metrics if they exist
    try:
        from .tools import reset_performance_metrics

        reset_performance_metrics()
    except ImportError:
        pass  # Performance monitoring might not be available

    return {
        "cleared_jobs": cleared_jobs,
        "message": f"Completely reset crawler: cleared {len(cleared_jobs)} jobs and reset metrics",
    }


@app.post("/get_crawler_info")
def get_crawler_info_endpoint(call: ToolCall):
    try:
        logger.info(
            f"Calling get_crawler_info with args: {call.args} and kwargs: {call.kwargs}"
        )
        return get_crawler_info(*call.args, **call.kwargs)
    except Exception as e:
        logger.error(f"An error occurred in get_crawler_info: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/get_jobs")
def get_jobs_tool(call: ToolCall, token_ok: None = Depends(require_api_token)):
    """Tool wrapper for list_jobs"""
    return list_jobs()


@app.post("/get_job_status")
def get_job_status_tool(call: ToolCall, token_ok: None = Depends(require_api_token)):
    """Tool wrapper for job_status. returns 200 even if not found to avoid bus circuit breaker."""
    job_id = call.args[0] if call.args else call.kwargs.get("job_id")
    include_results = call.kwargs.get("include_results", False)
    if not job_id:
        return {"status": "error", "message": "Missing job_id"}
    try:
        status = job_status(job_id)
        if not include_results and "result" in status:
            # Create a shallow copy and remove big results
            status = dict(status)
            if isinstance(status["result"], dict) and "articles" in status["result"]:
                # Keep article count but remove full list
                status["result"] = dict(status["result"])
                status["result"]["article_count"] = len(status["result"]["articles"])
                status["result"]["articles"] = [] # Clear the list
            else:
                status["result"] = "omitted (use include_results=true to fetch)"
        return status
    except HTTPException as e:
        if e.status_code == 404:
            return {"status": "unknown", "job_id": job_id}
        raise e
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/get_performance_metrics")
def get_performance_metrics_endpoint(call: ToolCall):
    try:
        from .tools import get_performance_monitor

        monitor = get_performance_monitor()
        logger.info(
            f"Calling get_performance_metrics with args: {call.args} and kwargs: {call.kwargs}"
        )
        return monitor.get_current_metrics()
    except Exception as e:
        logger.error(f"An error occurred in get_performance_metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready_endpoint():
    return {"ready": ready}


@app.get("/metrics")
def metrics_endpoint():
    """Prometheus metrics endpoint"""
    return Response(metrics.get_metrics(), media_type="text/plain; charset=utf-8")


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Crawler Agent on port {CRAWLER_AGENT_PORT}")
    uvicorn.run(
        "agents.crawler.main:app",
        host="0.0.0.0",
        port=CRAWLER_AGENT_PORT,
        reload=False,
        log_level="info",
    )


def execute_crawl(
    domains: list[str],
    max_articles_per_site: int = 25,
    concurrent_sites: int = 3,
    profile_overrides: dict | None = None,
):
    """Compatibility wrapper for programmatic crawling calls used in tests.

    Runs the unified crawl synchronously by executing the async engine via asyncio.run.
    Tests often patch this function, so keeping a well-behaved wrapper makes tests stable.
    """
    import asyncio

    async def _run():
        async with CrawlerEngine() as crawler:
            await crawler._load_ai_models()
            return await crawler.run_unified_crawl(
                domains,
                max_articles_per_site,
                concurrent_sites,
                profile_overrides=profile_overrides,
            )

    return asyncio.run(_run())
