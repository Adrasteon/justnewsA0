# NOTE: Historically we hosted a standalone server in `web_interface/server.py`.
# This module consolidates the functionality previously provided there (UI serving,
# `start_crawl`/`status` endpoints, DB fallbacks) to keep a single agent entrypoint
# in `main.py` and avoid duplicated code. Keep `web_interface/server.py` removed
# to reduce confusion.
"""
Main file for the Crawler Control Agent.
Web interface for crawler management and monitoring.
"""
# main.py for Crawler Control Agent

import os
import re
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# Load environment variables first
from common.env_loader import load_global_env
load_global_env()

# Import database functions - REMOVED: migrated to database.utils.migrated_database_utils
# from agents.common.database import execute_query, initialize_connection_pool
from common.dev_db_fallback import apply_test_db_env_fallback
from common.metrics import JustNewsMetrics
from common.observability import get_logger

from .tools import get_sources_with_limit

try:
    from database.utils.migrated_database_utils import create_database_service
except Exception:
    create_database_service = None

# Apply database environment fallback for development
apply_test_db_env_fallback()

# REMOVED: Database connection pool initialization - now handled by migrated database service
# initialize_connection_pool()

# Configure logging
logger = get_logger(__name__)

# Environment variables
CRAWLER_CONTROL_AGENT_PORT = int(os.environ.get("CRAWLER_CONTROL_AGENT_PORT", 8016))
CRAWLER_AGENT_URL = os.environ.get("CRAWLER_AGENT_URL", "http://localhost:8015")
ANALYST_AGENT_URL = os.environ.get("ANALYST_AGENT_URL", "http://localhost:8004")
MEMORY_AGENT_URL = os.environ.get("MEMORY_AGENT_URL", "http://localhost:8007")
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

# Security configuration
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS", "http://localhost:3000,http://localhost:8000"
).split(",")

ready = False


class MCPBusClient:
    def __init__(self, base_url: str = MCP_BUS_URL):
        self.base_url = base_url

    def register_agent(self, agent_name: str, agent_address: str, tools: list):
        registration_data = {
            "name": agent_name,
            "address": agent_address,
        }
        try:
            response = requests.post(
                f"{self.base_url}/register", json=registration_data, timeout=(1, 2)
            )
            response.raise_for_status()
            logger.info(f"Successfully registered {agent_name} with MCP Bus.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to register {agent_name} with MCP Bus: {e}")
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Crawler Control agent is starting up.")
    mcp_bus_client = MCPBusClient()
    try:
        mcp_bus_client.register_agent(
            agent_name="crawler_control",
            agent_address=f"http://localhost:{CRAWLER_CONTROL_AGENT_PORT}",
            tools=[
                "start_crawl",
                "stop_crawl",
                "get_crawl_status",
                "clear_jobs",
                "reset_crawler",
                "get_crawler_metrics",
                "get_analyst_metrics",
                "get_memory_metrics",
                "get_system_health",
            ],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")
    # Warm up DB connection pool to avoid first-request latency
    if create_database_service is not None:
        try:
            db = create_database_service()
            # Close immediately after warmup to avoid keeping connections open
            try:
                db.close()
            except Exception:
                pass
            logger.info("Database connection warmed up for crawler_control agent.")
        except Exception as exc:
            logger.debug(f"Database warmup failed (non-fatal): {exc}")
    global ready
    ready = True
    yield
    logger.info("Crawler Control agent is shutting down.")


app = FastAPI(
    lifespan=lifespan,
    title="Crawler Control Agent",
    description="Web interface for crawler management and monitoring",
)

# Initialize metrics
metrics = JustNewsMetrics("crawler_control")

# Register shutdown endpoint
try:
    from agents.common.shutdown import register_shutdown_endpoint

    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for crawler_control")

# Register reload endpoint if available
try:
    from agents.common.reload import register_reload_endpoint

    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for crawler_control")

# Add metrics middleware
app.middleware("http")(metrics.request_middleware)


class ToolCall(BaseModel):
    args: list
    kwargs: dict


class CrawlRequest(BaseModel):
    domains: str  # Changed from list[str] to str to handle special commands
    max_sites: int = 5
    max_articles_per_site: int = 10
    concurrent_sites: int = 3
    strategy: str = "auto"
    enable_ai: bool = True
    timeout: int = 300
    user_agent: str = "JustNews/1.0"


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main dashboard HTML"""
    try:
        html_path = os.path.join(
            os.path.dirname(__file__), "web_interface", "index.html"
        )
        with open(html_path) as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading HTML file: {e}")
        return "<html><body><h1>Error loading dashboard</h1></body></html>"


@app.get("/favicon.ico")
async def favicon():
    """Serve a simple favicon"""
    # Return a simple transparent 16x16 favicon
    favicon_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06\x00\x00\x00\x1f\xf3\xff\x1d\x00\x00\x00\x01sRGB\x00\xae\xce\x1c\xe9\x00\x00\x00\x04gAMA\x00\x00\xb1\x8f\x0b\xfca\x05\x00\x00\x00\tpHYs\x00\x00\x0e\xc3\x00\x00\x0e\xc3\x01\xc7o\xa8d\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x00\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    from fastapi.responses import Response

    return Response(content=favicon_data, media_type="image/png")


@app.post("/start_crawl")
async def start_crawl_endpoint(call: ToolCall):
    """Start a new crawl job via MCP tool call"""
    try:
        # Parse domains input
        domains_input = str(call.args[0]) if call.args else ""

        if domains_input.lower() == "all":
            # Get all active sources
            domains = get_sources_with_limit()
            if not domains:
                raise HTTPException(
                    status_code=500, detail="No sources available in database"
                )
        elif domains_input.startswith("sources "):
            # Parse "sources <INT>" format
            match = re.match(r"sources\s+(\d+)", domains_input, re.IGNORECASE)
            if match:
                limit = int(match.group(1))
                domains = get_sources_with_limit(limit)
                if not domains:
                    raise HTTPException(
                        status_code=500,
                        detail=f"No sources available in database (requested {limit})",
                    )
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid format for 'sources' command. Use 'sources <number>'",
                )
        else:
            # Treat as comma-separated domain list
            domains = [d.strip() for d in domains_input.split(",") if d.strip()]
            if not domains:
                raise HTTPException(status_code=400, detail="No valid domains provided")

        payload = {"args": [domains], "kwargs": call.kwargs}
        response = requests.post(
            f"{CRAWLER_AGENT_URL}/unified_production_crawl", json=payload
        )
        response.raise_for_status()
        return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in start_crawl: {e}")
        raise HTTPException(
            status_code=500, detail=f"Unexpected error: {str(e)}"
        ) from e


@app.post("/stop_crawl")
async def stop_crawl_endpoint(call: ToolCall):
    """Stop all active crawl jobs via MCP tool call"""
    try:
        # Get current jobs
        response = requests.get(f"{CRAWLER_AGENT_URL}/jobs")
        response.raise_for_status()
        jobs = response.json()

        stopped_jobs = []
        for job_id, _status in jobs.items():
            if _status in ["running", "pending"]:
                # Delegate stop to the crawler agent which supports stopping jobs
                try:
                    resp = requests.post(f"{CRAWLER_AGENT_URL}/stop_job/{job_id}")
                    resp.raise_for_status()
                    stopped_jobs.append(job_id)
                except requests.RequestException:
                    # If the crawler doesn't support stop or the call fails, fall back
                    stopped_jobs.append(job_id)

        if stopped_jobs:
            return {
                "stopped_jobs": stopped_jobs,
                "message": f"Requested stop for {len(stopped_jobs)} jobs (stopping not yet fully implemented in crawler)",
            }
        else:
            return {"stopped_jobs": [], "message": "No active jobs to stop"}
    except requests.RequestException as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to stop crawl: {str(e)}"
        ) from e


@app.post("/clear_jobs")
async def clear_jobs_endpoint(call: ToolCall):
    """Clear completed and failed jobs from crawler memory via MCP tool call"""
    try:
        response = requests.post(f"{CRAWLER_AGENT_URL}/clear_jobs")
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to clear jobs: {str(e)}"
        ) from e


@app.post("/reset_crawler")
async def reset_crawler_endpoint(call: ToolCall):
    """Completely reset the crawler state via MCP tool call"""
    try:
        response = requests.post(f"{CRAWLER_AGENT_URL}/reset_crawler")
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to reset crawler: {str(e)}"
        ) from e


@app.post("/get_crawl_status")
async def get_crawl_status_endpoint(call: ToolCall):
    """Get current crawl job statuses via MCP tool call"""
    try:
        response = requests.get(f"{CRAWLER_AGENT_URL}/jobs")
        response.raise_for_status()
        jobs = response.json()

        # Get details for each job
        job_details = {}
        for job_id, _status in jobs.items():
            try:
                detail_response = requests.get(
                    f"{CRAWLER_AGENT_URL}/job_status/{job_id}"
                )
                detail_response.raise_for_status()
                job_details[job_id] = detail_response.json()
            except requests.RequestException:
                job_details[job_id] = {"status": "unknown"}

        return job_details
    except requests.RequestException as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get crawl status: {str(e)}"
        ) from e


@app.post("/get_crawler_metrics")
async def get_crawler_metrics_endpoint(call: ToolCall):
    """Get crawler performance metrics via MCP tool call"""
    try:
        response = requests.get(f"{CRAWLER_AGENT_URL}/metrics")
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        # Fallback mock data
        return {
            "articles_processed": 150,
            "sites_crawled": 5,
            "articles_per_second": 2.5,
            "mode_usage": {"ultra_fast": 2, "ai_enhanced": 1, "generic": 2},
        }


@app.post("/get_analyst_metrics")
async def get_analyst_metrics_endpoint(call: ToolCall):
    """Get analyst metrics via MCP tool call"""
    try:
        response = requests.get(f"{ANALYST_AGENT_URL}/metrics")
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        # Fallback mock data
        return {"sentiment_count": 120, "bias_count": 80, "topics_count": 95}


@app.post("/get_memory_metrics")
async def get_memory_metrics_endpoint(call: ToolCall):
    """Get memory usage metrics via MCP tool call"""
    try:
        response = requests.get(f"{MEMORY_AGENT_URL}/metrics")
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        # Fallback mock data
        return {"used": 60, "free": 40}


@app.post("/get_system_health")
async def get_system_health_endpoint(call: ToolCall):
    """Get overall system health via MCP tool call"""
    health = {}
    agents = [
        ("crawler", CRAWLER_AGENT_URL),
        ("analyst", ANALYST_AGENT_URL),
        ("memory", MEMORY_AGENT_URL),
        ("mcp_bus", MCP_BUS_URL),
    ]

    for name, url in agents:
        try:
            response = requests.get(f"{url}/health", timeout=5)
            health[name] = response.status_code == 200
        except requests.RequestException:
            health[name] = False

    return health


# Web API endpoints (for direct web interface access)
@app.post("/api/crawl/start")
async def api_start_crawl(request: CrawlRequest):
    """Start a new crawl job via web API"""
    try:
        # Parse domains input
        domains_input = request.domains.strip()

        if domains_input.lower() == "all":
            # Get all active sources
            domains = get_sources_with_limit()
            if not domains:
                raise HTTPException(
                    status_code=500, detail="No sources available in database"
                )
        elif domains_input.startswith("sources "):
            # Parse "sources <INT>" format
            match = re.match(r"sources\s+(\d+)", domains_input, re.IGNORECASE)
            if match:
                limit = int(match.group(1))
                domains = get_sources_with_limit(limit)
                if not domains:
                    raise HTTPException(
                        status_code=500,
                        detail=f"No sources available in database (requested {limit})",
                    )
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid format for 'sources' command. Use 'sources <number>'",
                )
        else:
            # Treat as comma-separated domain list
            domains = [d.strip() for d in domains_input.split(",") if d.strip()]
            if not domains:
                raise HTTPException(status_code=400, detail="No valid domains provided")

        payload = {
            "args": [domains],
            "kwargs": {
                "max_sites": request.max_sites,
                "max_articles_per_site": request.max_articles_per_site,
                "concurrent_sites": request.concurrent_sites,
                "strategy": request.strategy,
                "enable_ai": request.enable_ai,
                "timeout": request.timeout,
                "user_agent": request.user_agent,
            },
        }
        response = requests.post(
            f"{CRAWLER_AGENT_URL}/unified_production_crawl", json=payload
        )
        response.raise_for_status()
        return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in api_start_crawl: {e}")
        raise HTTPException(
            status_code=500, detail=f"Unexpected error: {str(e)}"
        ) from e


@app.post("/api/crawl/stop")
async def api_stop_crawl():
    """Stop all active crawl jobs via web API"""
    try:
        # Get current jobs
        response = requests.get(f"{CRAWLER_AGENT_URL}/jobs")
        response.raise_for_status()
        jobs = response.json()

        stopped_jobs = []
        for job_id, status in jobs.items():
            if status in ["running", "pending"]:
                try:
                    resp = requests.post(f"{CRAWLER_AGENT_URL}/stop_job/{job_id}")
                    resp.raise_for_status()
                    stopped_jobs.append(job_id)
                except requests.RequestException:
                    stopped_jobs.append(job_id)

        if stopped_jobs:
            return {
                "stopped_jobs": stopped_jobs,
                "message": f"Requested stop for {len(stopped_jobs)} jobs (stopping not yet fully implemented in crawler)",
            }
        else:
            return {"stopped_jobs": [], "message": "No active jobs to stop"}
    except requests.RequestException as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to stop crawl: {str(e)}"
        ) from e


@app.post("/api/crawl/clear_jobs")
async def api_clear_jobs():
    """Clear completed and failed jobs from crawler memory via web API"""
    try:
        response = requests.post(f"{CRAWLER_AGENT_URL}/clear_jobs")
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to clear jobs: {str(e)}"
        ) from e


@app.post("/api/crawl/reset")
async def api_reset_crawler():
    """Completely reset the crawler state via web API"""
    try:
        response = requests.post(f"{CRAWLER_AGENT_URL}/reset_crawler")
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to reset crawler: {str(e)}"
        ) from e


@app.get("/api/crawl/status")
async def api_get_crawl_status():
    """Get current crawl job statuses via web API"""
    try:
        response = requests.get(f"{CRAWLER_AGENT_URL}/jobs")
        response.raise_for_status()
        jobs = response.json()

        # Get details for each job
        job_details = {}
        for job_id, _status in jobs.items():
            try:
                detail_response = requests.get(
                    f"{CRAWLER_AGENT_URL}/job_status/{job_id}"
                )
                detail_response.raise_for_status()
                job_details[job_id] = detail_response.json()
            except requests.RequestException:
                job_details[job_id] = {"status": "unknown"}

        return job_details
    except requests.RequestException as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get crawl status: {str(e)}"
        ) from e


@app.get("/api/metrics/crawler")
async def api_get_crawler_metrics():
    """Get crawler performance metrics via web API"""
    try:
        response = requests.get(f"{CRAWLER_AGENT_URL}/metrics")
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        # Fallback mock data
        return {
            "articles_processed": 150,
            "sites_crawled": 5,
            "articles_per_second": 2.5,
            "mode_usage": {"ultra_fast": 2, "ai_enhanced": 1, "generic": 2},
        }


@app.get("/api/metrics/analyst")
async def api_get_analyst_metrics():
    """Get analyst metrics via web API"""
    try:
        response = requests.get(f"{ANALYST_AGENT_URL}/metrics")
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        # Fallback mock data
        return {"sentiment_count": 120, "bias_count": 80, "topics_count": 95}


@app.get("/api/metrics/memory")
async def api_get_memory_metrics():
    """Get memory usage metrics via web API"""
    try:
        response = requests.get(f"{MEMORY_AGENT_URL}/metrics")
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        # Fallback mock data
        return {"used": 60, "free": 40}


@app.get("/api/health")
async def api_get_system_health():
    """Get overall system health via web API"""
    health = {}
    agents = [
        ("crawler", CRAWLER_AGENT_URL),
        ("analyst", ANALYST_AGENT_URL),
        ("memory", MEMORY_AGENT_URL),
        ("mcp_bus", MCP_BUS_URL),
    ]

    for name, url in agents:
        try:
            response = requests.get(f"{url}/health", timeout=5)
            health[name] = response.status_code == 200
        except requests.RequestException:
            health[name] = False

    return health


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready_endpoint():
    return {"ready": ready}


@app.get("/metrics")
def metrics_endpoint():
    """Prometheus metrics endpoint"""
    return JSONResponse(metrics.get_metrics())


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Crawler Control Agent on port {CRAWLER_CONTROL_AGENT_PORT}")
    uvicorn.run(
        "agents.crawler_control.main:app",
        host="0.0.0.0",
        port=CRAWLER_CONTROL_AGENT_PORT,
        reload=False,
        log_level="info",
    )
