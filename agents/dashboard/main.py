"""
Dashboard Agent - JustNews Dashboard Service

This module provides the FastAPI application for the dashboard agent,
including web interface, GPU monitoring, and agent management endpoints.
"""

import json
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents.common.auth_models import get_user_by_id
from agents.dashboard.dashboard_engine import dashboard_engine
from agents.dashboard.transparency_router import router as transparency_router
from common.metrics import JustNewsMetrics
from common.observability import bootstrap_observability, get_logger

bootstrap_observability("dashboard")
logger = get_logger(__name__)


def get_search_service():
    """Runtime resolver for the Search service to make tests monkeypatch-friendly.

    Avoid importing `common.semantic_search_service.get_search_service` at module
    import time so tests can patch the implementation in `common.semantic_search_service`.
    """
    from common.semantic_search_service import get_search_service as _get_search_service

    return _get_search_service()


# Compatibility: expose create_database_service for tests that patch agent modules
try:
    from database.utils.migrated_database_utils import (
        create_database_service,  # type: ignore
    )
except Exception:
    create_database_service = None

try:
    from agents.common.gpu_manager_production import get_gpu_manager

    GPU_MANAGER_AVAILABLE = True
except Exception:  # pragma: no cover - GPU manager optional in some environments
    GPU_MANAGER_AVAILABLE = False

    def get_gpu_manager():  # type: ignore[override]
        raise RuntimeError("GPU manager not available in this environment")


try:
    from config import get_config as _get_global_config
    from config import get_config_manager as _get_config_manager
except Exception:  # pragma: no cover - unified config not available in this runtime
    _get_global_config = None  # type: ignore[assignment]
    _get_config_manager = None  # type: ignore[assignment]

logger = get_logger(__name__)

PUBLIC_API_AVAILABLE = os.getenv("JUSTNEWS_ENABLE_PUBLIC_API", "0").lower() in {
    "1",
    "true",
    "yes",
}


def include_public_api(app: FastAPI) -> None:
    """Conditionally register public API routes for the dashboard agent."""
    if not PUBLIC_API_AVAILABLE:
        logger.debug("Public API disabled; skipping registration.")
        return

    try:
        from agents.dashboard import (
            public_api,  # Local import to keep dependency optional
        )

        if hasattr(public_api, "include_public_api"):
            public_api.include_public_api(app)
            logger.info("Public API routes registered for dashboard agent.")
        else:
            logger.warning(
                "Public API module missing include_public_api(); skipping registration."
            )
    except (ModuleNotFoundError, ImportError) as exc:
        # In some test runs PUBLIC_API_AVAILABLE may be enabled but the
        # optional public_api module may not exist or may not export the
        # expected symbol. Treat either case as non-fatal and continue.
        logger.warning(
            "Public API module unavailable or invalid; skipping registration: %s", exc
        )


def load_config() -> dict[str, Any]:
    """Load dashboard configuration from the unified configuration system."""
    if _get_global_config is None:
        logger.debug("Unified configuration unavailable; using dashboard defaults.")
        return {}

    try:
        unified = _get_global_config()
        dashboard_port = getattr(
            getattr(unified.agents, "ports", None), "dashboard", 8014
        )
        mcp_bus = getattr(unified, "mcp_bus", None)

        if mcp_bus is not None:
            base_url = getattr(mcp_bus, "url", None)
            if base_url:
                mcp_bus_url = str(base_url).rstrip("/")
            else:
                host = getattr(mcp_bus, "host", "localhost")
                port = getattr(mcp_bus, "port", 8000)
                mcp_bus_url = f"http://{host}:{port}"
        else:
            mcp_bus_url = "http://localhost:8000"

        return {
            "dashboard_port": dashboard_port,
            "mcp_bus_url": mcp_bus_url,
        }
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Failed to load unified configuration for dashboard: %s", exc)
        return {}


def save_config(updated_config: dict[str, Any]) -> None:
    """Persist dashboard-specific overrides when the unified configuration is available."""
    if _get_config_manager is None:
        logger.debug(
            "No configuration manager available; skipping dashboard config persistence."
        )
        return

    try:
        manager = _get_config_manager()
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Failed to acquire configuration manager: %s", exc)
        return

    if "dashboard_port" in updated_config:
        try:
            manager.set(
                "agents.ports.dashboard",
                int(updated_config["dashboard_port"]),
                persist=True,
            )
            logger.info("Persisted dashboard port override to unified configuration.")
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Unable to persist dashboard port: %s", exc)


# Load configuration
config = load_config()
# Default dashboard port set to 8013 for transparency and public website
DASHBOARD_AGENT_PORT = config.get("dashboard_port", 8013)
MCP_BUS_URL = config.get("mcp_bus_url", "http://localhost:8000")
GPU_ORCHESTRATOR_URL = os.environ.get(
    "GPU_ORCHESTRATOR_URL", "http://localhost:8014"
).rstrip("/")


class MCPBusClient:
    """MCP Bus client for agent registration and communication."""

    def __init__(self, base_url: str = MCP_BUS_URL):
        self.base_url = base_url

    def register_agent(self, agent_name: str, agent_address: str, tools: list):
        """Register agent with MCP Bus."""
        registration_data = {
            "name": agent_name,
            "address": agent_address,
        }
        try:
            response = requests.post(
                f"{self.base_url}/register", json=registration_data
            )
            response.raise_for_status()
            logger.info(f"Successfully registered {agent_name} with MCP Bus.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to register {agent_name} with MCP Bus: {e}")
            raise


class ToolCall(BaseModel):
    """Standard MCP tool call format"""

    args: list
    kwargs: dict[str, Any]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Dashboard agent is starting up.")
    mcp_bus_client = MCPBusClient()
    try:
        mcp_bus_client.register_agent(
            agent_name="dashboard",
            agent_address=f"http://localhost:{DASHBOARD_AGENT_PORT}",
            tools=[
                "get_status",
                "send_command",
                "receive_logs",
                "get_gpu_info",
                "get_gpu_history",
                "get_agent_gpu_usage",
                "get_gpu_config",
                "update_gpu_config",
            ],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")
    global ready
    ready = True
    yield
    logger.info("Dashboard agent is shutting down.")
    save_config(config)


app = FastAPI(lifespan=lifespan)

# Add CORS middleware for public API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/admin/set_publishing_config")
def set_publishing_config(payload: dict, request: Request):
    """Admin endpoint to update publishing configuration at runtime.

    Example payload: {"require_draft_fact_check_pass_for_publish": true, "chief_editor_review_required": false}
    """
    try:
        # Authentication strategy (supports both API key for simple envs and
        # role-based JWT for production). If ADMIN_API_KEY is configured the
        # request may supply it via `Authorization: Bearer <key>` or
        # `X-Admin-API-Key: <key>`. Otherwise a JWT bearer token with admin
        # role is required.
        admin_key = os.environ.get("ADMIN_API_KEY")
        auth_header = (
            request.headers.get("Authorization")
            or request.headers.get("X-Admin-API-Key")
            or ""
        ).strip()
        if admin_key and auth_header:
            # accept either a raw key header or Authorization: Bearer <key>
            if auth_header.lower().startswith("bearer "):
                token = auth_header.split(" ", 1)[1]
            else:
                token = auth_header
            if token != admin_key:
                raise HTTPException(
                    status_code=401, detail="Admin API key missing or invalid"
                )
        else:
            # No API key or header; try JWT bearer token
            if not auth_header:
                raise HTTPException(
                    status_code=401, detail="Admin credentials required"
                )
            if auth_header.lower().startswith("bearer "):
                token = auth_header.split(" ", 1)[1]
            else:
                token = auth_header
            # runtime import so tests can monkeypatch the auth_models module
            import agents.common.auth_models as auth_models

            token_payload = auth_models.verify_token(token)
            if token_payload is None:
                raise HTTPException(
                    status_code=401, detail="Invalid authentication token"
                )
            user = auth_models.get_user_by_id(token_payload.user_id)
            if user is None or user.get("role") != auth_models.UserRole.ADMIN.value:
                raise HTTPException(status_code=403, detail="Admin role required")
        from config.core import get_config_manager

        manager = get_config_manager()
        # Set individual flags
        if "require_draft_fact_check_pass_for_publish" in payload:
            # dot-path
            manager.set(
                "agents.publishing.require_draft_fact_check_pass_for_publish",
                bool(payload["require_draft_fact_check_pass_for_publish"]),
                persist=True,
            )
        if "chief_editor_review_required" in payload:
            manager.set(
                "agents.publishing.chief_editor_review_required",
                bool(payload["chief_editor_review_required"]),
                persist=True,
            )
        if "synthesized_article_storage" in payload:
            manager.set(
                "system.persistence.synthesized_article_storage",
                str(payload["synthesized_article_storage"]),
                persist=True,
            )
        # Audit: persist change to disk for governance
        try:
            audit_dir = Path(os.environ.get("SERVICE_DIR", ".")) / "logs" / "audit"
            audit_dir.mkdir(parents=True, exist_ok=True)
            audit_file = audit_dir / "publishing_config_changes.jsonl"
            audit_entry = {
                "ts": datetime.now(UTC).isoformat(),
                "payload": payload,
            }
            # If admin action was performed with a JWT, record admin identity
            try:
                # `payload` variable above may be set when JWT auth is used
                if (
                    "token_payload" in locals()
                    and locals().get("token_payload")
                    and hasattr(locals().get("token_payload"), "user_id")
                ):
                    token_payload = locals().get("token_payload")
                    admin_user = get_user_by_id(token_payload.user_id)
                    if admin_user:
                        audit_entry["admin_user"] = {
                            "user_id": admin_user.get("user_id"),
                            "username": admin_user.get("username"),
                            "email": admin_user.get("email"),
                        }
            except Exception:
                pass
            with open(audit_file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(audit_entry, default=str) + "\n")
        except Exception:
            logger.exception("Failed to write audit log for publishing config change")
        return {"status": "success"}
    except HTTPException:
        # Preserve explicit FastAPI HTTP errors (401/403 etc.) so callers and
        # tests receive the intended status code rather than a 500.
        raise
    except Exception as e:
        logger.exception("Failed to set publishing config")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/admin/get_publishing_config")
def get_publishing_config(request: Request):
    """Return current publishing configuration values to the UI."""
    try:
        from config.core import get_config

        # This endpoint supports either the legacy ADMIN_API_KEY (header) or
        # an admin JWT Bearer token. If no header is passed and ADMIN_API_KEY
        # isn't set, a valid JWT with admin role is required.
        admin_key = os.environ.get("ADMIN_API_KEY")
        auth_header = (
            request.headers.get("Authorization")
            or request.headers.get("X-Admin-API-Key")
            or ""
        ).strip()
        if admin_key and auth_header:
            if auth_header.lower().startswith("bearer "):
                token = auth_header.split(" ", 1)[1]
            else:
                token = auth_header
            if token != admin_key:
                raise HTTPException(
                    status_code=401, detail="Admin API key missing or invalid"
                )
        else:
            # Jack back to JWT admin role requirement
            if not auth_header:
                raise HTTPException(
                    status_code=401, detail="Admin credentials required"
                )

            # Extract the token or raw API key value when an Authorization header
            # is present; then verify via JWT-based admin role checks.
            if auth_header.lower().startswith("bearer "):
                token = auth_header.split(" ", 1)[1]
            else:
                token = auth_header

            # Use runtime import so tests can monkeypatch agents.common.auth_models
            # and have the patched functions observed by this endpoint.
            import agents.common.auth_models as auth_models

            token_payload = auth_models.verify_token(token)
            if token_payload is None:
                raise HTTPException(
                    status_code=401, detail="Invalid authentication token"
                )
            user = auth_models.get_user_by_id(token_payload.user_id)
            if user is None or user.get("role") != auth_models.UserRole.ADMIN.value:
                raise HTTPException(status_code=403, detail="Admin role required")

        cfg = get_config()
        publishing = getattr(cfg.agents, "publishing", None)
        require_draft = bool(
            getattr(publishing, "require_draft_fact_check_pass_for_publish", False)
        )
        chief_required = bool(
            getattr(publishing, "chief_editor_review_required", False)
        )
        # Persistence storage option
        persistence = getattr(cfg, "persistence", None)
        storage = None
        if persistence is not None:
            storage = getattr(persistence, "synthesized_article_storage", None)
        return {
            "status": "success",
            "require_draft_fact_check_pass_for_publish": require_draft,
            "chief_editor_review_required": chief_required,
            "synthesized_article_storage": storage,
        }
    except HTTPException:
        # Preserve explicit FastAPI HTTP errors (401/403 etc.) so tests and
        # callers receive the intended status code instead of a 500.
        raise
    except Exception as e:
        logger.exception("Failed to read publishing config")
        raise HTTPException(status_code=500, detail=str(e)) from e


# Mount static files for public website
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Mount transparency and evidence audit endpoints
app.include_router(transparency_router)

# Include search API endpoints only when PUBLIC_API_AVAILABLE to avoid importing
# heavy optional dependencies during tests or minimal deployments.
if PUBLIC_API_AVAILABLE:
    try:
        from .search_api import router as search_router

        app.include_router(search_router)
    except Exception:
        logger.warning("Search API not available; skipping search router registration.")

# Include public API routes
if PUBLIC_API_AVAILABLE:
    include_public_api(app)

# Initialize metrics
metrics = JustNewsMetrics("dashboard")

ready = False

# Register shutdown endpoint
try:
    from agents.common.shutdown import register_shutdown_endpoint

    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for dashboard")

# Register reload endpoint if available
try:
    from agents.common.reload import register_reload_endpoint

    register_reload_endpoint(app, require_admin=True)
except Exception:
    logger.debug("reload endpoint not registered for dashboard")

# Add metrics middleware
app.middleware("http")(metrics.request_middleware)


# Core Agent Endpoints


@app.get("/get_status")
def get_status():
    """Fetch the status of all agents."""
    try:
        return dashboard_engine.get_agent_status()
    except Exception as e:
        logger.error(f"An error occurred while fetching agent status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "agent": "dashboard"}


@app.get("/ready")
def ready_endpoint():
    """Readiness check endpoint."""
    return {"ready": ready}


@app.post("/send_command")
def send_command(call: ToolCall):
    """Send a command to another agent."""
    try:
        return dashboard_engine.send_command(call)
    except Exception as e:
        logger.error(f"An error occurred while sending a command: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# Web Interface Endpoints


@app.get("/")
def dashboard_home():
    """Serve the main JustNews public website"""
    try:
        # Try to serve the public website HTML file first
        public_website_path = Path(__file__).parent / "public_website.html"
        if public_website_path.exists():
            return FileResponse(public_website_path, media_type="text/html")
        else:
            # Fall back to embedded HTML
            return HTMLResponse(content=get_fallback_public_website_html())
    except Exception as e:
        logger.error(f"Error serving public website: {e}")
        return HTMLResponse(content=get_fallback_public_website_html())


@app.get("/article/{article_id}")
def serve_article_page(article_id: str):
    """Serve individual article page"""
    try:
        # Try to serve the public website HTML file with article context
        public_website_path = Path(__file__).parent / "public_website.html"
        if public_website_path.exists():
            with open(public_website_path, encoding="utf-8") as f:
                content = f.read()
            # Add article ID to the page for JavaScript to handle
            content = content.replace(
                "<body>", f'<body data-article-id="{article_id}">'
            )
            return HTMLResponse(content=content)
        else:
            return HTMLResponse(content=get_fallback_public_website_html())
    except Exception as e:
        logger.error(f"Error serving article page: {e}")
        return HTMLResponse(content=get_fallback_public_website_html())


@app.get("/search")
def serve_search_page(request: Request):
    """Serve search results page"""
    try:
        query = request.query_params.get("q", "")
        public_website_path = Path(__file__).parent / "public_website.html"
        if public_website_path.exists():
            with open(public_website_path, encoding="utf-8") as f:
                content = f.read()
            # Add search query to the page for JavaScript to handle
            content = content.replace("<body>", f'<body data-search-query="{query}">')
            return HTMLResponse(content=content)
        else:
            return HTMLResponse(content=get_fallback_public_website_html())
    except Exception as e:
        logger.error(f"Error serving search page: {e}")
        return HTMLResponse(content=get_fallback_public_website_html())


@app.get("/about")
def serve_about_page():
    """Serve about page"""
    try:
        public_website_path = Path(__file__).parent / "public_website.html"
        if public_website_path.exists():
            with open(public_website_path, encoding="utf-8") as f:
                content = f.read()
            # Add about flag to the page for JavaScript to handle
            content = content.replace("<body>", '<body data-page="about">')
            return HTMLResponse(content=content)
        else:
            return HTMLResponse(content=get_fallback_public_website_html())
    except Exception as e:
        logger.error(f"Error serving about page: {e}")
        return HTMLResponse(content=get_fallback_public_website_html())


@app.get("/api-docs")
def serve_api_docs():
    """Serve API documentation page"""
    try:
        public_website_path = Path(__file__).parent / "public_website.html"
        if public_website_path.exists():
            with open(public_website_path, encoding="utf-8") as f:
                content = f.read()
            # Add API docs flag to the page for JavaScript to handle
            content = content.replace("<body>", '<body data-page="api-docs">')
            return HTMLResponse(content=content)
        else:
            return HTMLResponse(content=get_fallback_public_website_html())
    except Exception as e:
        logger.error(f"Error serving API docs page: {e}")
        return HTMLResponse(content=get_fallback_public_website_html())


# GPU Monitoring Endpoints


@app.get("/gpu/info")
def get_gpu_info():
    """Get current GPU information and status."""
    try:
        return dashboard_engine.gpu_monitor.get_gpu_info()
    except Exception as e:
        logger.error(f"Error in get_gpu_info endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/gpu/history")
def get_gpu_history(hours: int = 1):
    """Get GPU usage history for the specified number of hours."""
    try:
        history = dashboard_engine.gpu_monitor.get_gpu_history(hours)
        return {
            "status": "success",
            "hours": hours,
            "data_points": len(history),
            "history": history,
            "timestamp": time.time(),
        }
    except Exception as e:
        logger.error(f"Error in get_gpu_history endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/gpu/agents")
def get_agent_gpu_usage():
    """Get GPU usage statistics per agent."""
    try:
        return dashboard_engine.gpu_monitor.get_agent_gpu_usage()
    except Exception as e:
        logger.error(f"Error in get_agent_gpu_usage endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/gpu/config")
def get_gpu_config():
    """Get current GPU configuration from the GPU manager."""
    try:
        return dashboard_engine.get_gpu_config()
    except Exception as e:
        logger.error(f"Error getting GPU config: {e}")
        return {"status": "error", "message": str(e), "timestamp": time.time()}


@app.post("/gpu/config")
def update_gpu_config(new_config: dict):
    """Update GPU configuration."""
    try:
        return dashboard_engine.update_gpu_config(new_config)
    except Exception as e:
        logger.error(f"Error updating GPU config: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/gpu/manager/status")
def get_gpu_manager_status():
    """Get comprehensive GPU manager system status."""
    try:
        return dashboard_engine.get_gpu_manager_status()
    except Exception as e:
        logger.error(f"Error getting GPU manager status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/gpu/allocations")
def get_gpu_allocations():
    """Get all current GPU allocations."""
    try:
        return dashboard_engine.get_gpu_allocations()
    except Exception as e:
        logger.error(f"Error getting GPU allocations: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/gpu/metrics")
def get_gpu_metrics():
    """Get GPU performance metrics from the manager."""
    try:
        return dashboard_engine.get_gpu_metrics()
    except Exception as e:
        logger.error(f"Error getting GPU metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


class IngestRequest(BaseModel):
    """Request model for ingesting external GPU metrics JSONL."""

    path: str
    max_lines: int | None = 10000


@app.post("/gpu/ingest_jsonl")
def ingest_gpu_jsonl(req: IngestRequest):
    """Ingest GPU watcher JSONL into dashboard storage."""
    try:
        return dashboard_engine.ingest_gpu_jsonl(req.path, req.max_lines)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting GPU JSONL: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/gpu/dashboard")
def get_gpu_dashboard_data():
    """Get comprehensive GPU dashboard data including manager integration."""
    try:
        return dashboard_engine.get_comprehensive_gpu_dashboard_data()
    except Exception as e:
        logger.error(f"Error in get_gpu_dashboard_data endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/gpu/history/db")
def get_gpu_history_from_db(
    hours: int = 24, gpu_index: int | None = None, metric: str = "utilization"
):
    """Get GPU metrics history from database."""
    try:
        return dashboard_engine.get_gpu_history_from_db(hours, gpu_index, metric)
    except Exception as e:
        logger.error(f"Error getting GPU history from DB: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/gpu/allocations/history")
def get_allocation_history(hours: int = 24, agent_name: str | None = None):
    """Get agent allocation history from database."""
    try:
        return dashboard_engine.get_allocation_history(hours, agent_name)
    except Exception as e:
        logger.error(f"Error getting allocation history: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/gpu/trends")
def get_performance_trends(hours: int = 24):
    """Get performance trends data."""
    try:
        return dashboard_engine.get_performance_trends(hours)
    except Exception as e:
        logger.error(f"Error getting performance trends: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/gpu/alerts")
def get_recent_alerts(limit: int = 50):
    """Get recent alerts from database."""
    try:
        return dashboard_engine.get_recent_alerts(limit)
    except Exception as e:
        logger.error(f"Error getting recent alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/storage/stats")
def get_storage_stats():
    """Get database storage statistics."""
    try:
        return dashboard_engine.get_storage_stats()
    except Exception as e:
        logger.error(f"Error getting storage stats: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# Orchestrator proxy helpers & endpoints


def fetch_orchestrator_gpu_info():
    """Fetch GPU info from orchestrator (fast timeout)."""
    try:
        r = requests.get(f"{GPU_ORCHESTRATOR_URL}/gpu/info", timeout=(1.5, 3.0))
        if r.status_code == 200:
            return r.json()
        return {"available": False, "error": f"unexpected_status:{r.status_code}"}
    except Exception as e:
        return {"available": False, "error": str(e)}


def fetch_orchestrator_policy():
    """Fetch policy from orchestrator (fast timeout)."""
    try:
        r = requests.get(f"{GPU_ORCHESTRATOR_URL}/policy", timeout=(1.5, 3.0))
        if r.status_code == 200:
            return r.json()
        return {
            "safe_mode_read_only": True,
            "error": f"unexpected_status:{r.status_code}",
        }
    except Exception as e:
        return {"safe_mode_read_only": True, "error": str(e)}


@app.get("/orchestrator/gpu/info")
def orchestrator_gpu_info_proxy():
    """Proxy to orchestrator /gpu/info with fallback."""
    return fetch_orchestrator_gpu_info()


@app.get("/orchestrator/gpu/policy")
def orchestrator_gpu_policy_proxy():
    """Proxy to orchestrator /policy with fallback."""
    return fetch_orchestrator_policy()


@app.get("/metrics")
def get_metrics():
    """Prometheus metrics endpoint."""
    from fastapi.responses import Response

    return Response(metrics.get_metrics(), media_type="text/plain")


# Crawler Control Endpoints


class CrawlRequest(BaseModel):
    domains: list[str]
    max_sites: int = 5
    max_articles_per_site: int = 10
    concurrent_sites: int = 3
    strategy: str = "auto"
    enable_ai: bool = True
    timeout: int = 300
    user_agent: str = "JustNews/1.0"


@app.post("/api/crawl/start")
async def start_crawl(request: CrawlRequest):
    """Start a new crawl job"""
    try:
        # Use MCP bus to call the crawler agent
        payload = {
            "agent": "crawler",
            "tool": "unified_production_crawl",
            "args": [request.domains],
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
        response = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to start crawl: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to start crawl: {str(e)}"
        ) from e


@app.get("/api/crawl/status")
async def get_crawl_status():
    """Get current crawl job statuses"""
    try:
        # Use MCP bus to get crawler status
        payload = {"agent": "crawler", "tool": "get_jobs", "args": [], "kwargs": {}}
        response = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=5)
        response.raise_for_status()
        jobs = response.json()

        # Get details for each job
        job_details = {}
        for job_id, _status in jobs.items():
            try:
                detail_payload = {
                    "agent": "crawler",
                    "tool": "get_job_status",
                    "args": [job_id],
                    "kwargs": {},
                }
                detail_response = requests.post(
                    f"{MCP_BUS_URL}/call", json=detail_payload, timeout=5
                )
                detail_response.raise_for_status()
                job_details[job_id] = detail_response.json()
            except Exception:
                job_details[job_id] = {"status": "unknown"}

        return job_details
    except requests.RequestException as e:
        logger.error(f"Failed to get crawl status: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get crawl status: {str(e)}"
        ) from e


@app.get("/api/crawl/scheduler")
async def get_crawl_scheduler(include_runs: bool = True, history_limit: int = 20):
    """Return the latest crawl scheduler snapshot with adaptive metrics."""

    try:
        snapshot = dashboard_engine.get_crawl_scheduler_snapshot(
            include_runs=include_runs
        )
        if history_limit:
            snapshot["history"] = dashboard_engine.get_crawl_scheduler_history(
                limit=history_limit
            )
        else:
            snapshot["history"] = []
        return snapshot
    except Exception as exc:
        logger.error(f"Failed to load crawl scheduler snapshot: {exc}")
        raise HTTPException(
            status_code=500, detail=f"Failed to load crawl scheduler snapshot: {exc}"
        ) from exc


@app.get("/api/metrics/crawler")
async def get_crawler_metrics():
    """Get crawler performance metrics"""
    try:
        # Use MCP bus to get crawler metrics
        payload = {"agent": "crawler", "tool": "get_metrics", "args": [], "kwargs": {}}
        response = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=5)
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


@app.get("/api/dashboard/pages")
def get_dashboard_pages():
    """Return the configured dashboard pages for dynamic menu building on the web UI."""
    try:
        # Prefer dashboard config in the module-level config variable
        pages = config.get("pages") if isinstance(config, dict) else None
        if not pages:
            # Fallback to reading the dashboard config directly
            path = Path(__file__).parent / "config.json"
            if path.exists():
                import json

                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                    pages = data.get("pages", [])
        # Provide a small fallback list so UI has something even if config is empty
        fallback_pages = [
            {"title": "Home", "path": "/"},
            {"title": "Search", "path": "/search"},
            {"title": "About", "path": "/about"},
            {"title": "Crawler Status", "path": "/api/crawl/status"},
            {"title": "Crawl Scheduler", "path": "/api/crawl/scheduler"},
            {"title": "GPU Dashboard", "path": "/gpu/dashboard"},
            {"title": "Transparency", "path": "/transparency/status"},
            {"title": "Crawler Metrics", "path": "/api/metrics/crawler"},
            {"title": "System Health", "path": "/api/health"},
            {"title": "Crawler Control", "path": "http://localhost:8016/"},
        ]
        return {"status": "success", "pages": pages or fallback_pages}
    except Exception as e:
        logger.warning(f"Failed to read dashboard pages config: {e}")
        return {"status": "error", "pages": [], "error": str(e)}


@app.get("/api/metrics/analyst")
async def get_analyst_metrics():
    """Get analyst metrics"""
    try:
        # Use MCP bus to get analyst metrics
        payload = {"agent": "analyst", "tool": "get_metrics", "args": [], "kwargs": {}}
        response = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        # Fallback mock data
        return {"sentiment_count": 120, "bias_count": 80, "topics_count": 95}


@app.get("/api/metrics/memory")
async def get_memory_metrics():
    """Get memory usage metrics"""
    try:
        # Use MCP bus to get memory metrics
        payload = {"agent": "memory", "tool": "get_metrics", "args": [], "kwargs": {}}
        response = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        # Fallback mock data
        return {"used": 60, "free": 40}


@app.get("/api/health")
async def get_system_health():
    """Get overall system health"""
    health = {}
    agents = [
        ("crawler", 8015),  # Assuming crawler port
        ("analyst", 8004),
        ("memory", 8007),
        ("mcp_bus", 8000),
    ]

    for name, port in agents:
        try:
            response = requests.get(f"http://localhost:{port}/health", timeout=2)
            health[name] = response.status_code == 200
        except Exception:
            health[name] = False

    return health


@app.get("/api/public/articles")
def public_articles(n: int = 10):
    """Compatibility endpoint used by the public website to fetch recent articles.

    This endpoint mirrors `/api/public/search/articles` but lives at the
    '/api/public/articles' path for a simpler, stable public website API.
    """
    try:
        service = get_search_service()
        articles = service.get_recent_articles_with_search(n_results=min(n, 50))
        # Convert to simplified schema
        return {
            "total_results": len(articles),
            "articles": [
                {
                    "id": a.id,
                    "title": a.title,
                    "summary": (a.content[:300] + "...")
                    if len(a.content) > 300
                    else a.content,
                    "source": a.source_name,
                    "published_date": a.published_date,
                    "sentiment_score": getattr(a, "sentiment_score", 0),
                    "fact_check_score": getattr(a, "fact_check_score", None),
                    "url": getattr(a, "url", None),
                }
                for a in articles
            ],
        }
    except Exception as exc:
        logger.exception("Public articles endpoint failed: %s", exc)
        raise HTTPException(
            status_code=500, detail="Recent articles temporarily unavailable"
        ) from exc


def get_fallback_dashboard_html():
    """Fallback HTML dashboard if template file is not available."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>JustNews GPU Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .metric { background: #f0f0f0; padding: 10px; margin: 10px; border-radius: 5px; }
        </style>
    </head>
    <body>
        <h1>🚀 JustNews GPU Dashboard</h1>
        <div id="dashboard">
            <div class="metric">
                <h3>GPU Status</h3>
                <p>Loading...</p>
            </div>
        </div>
        <button onclick="loadData()">Refresh</button>

        <script>
            async function loadData() {
                try {
                    const response = await fetch('/gpu/dashboard');
                    const data = await response.json();
                    updateDashboard(data);
                } catch (error) {
                    console.error('Error:', error);
                }
            }

            function updateDashboard(data) {
                const dashboard = document.getElementById('dashboard');
                if (data.status === 'success') {
                    dashboard.innerHTML = `
                        <div class="metric">
                            <h3>GPU Summary</h3>
                            <p>Total GPUs: ${data.summary.total_gpus}</p>
                            <p>Active Agents: ${data.summary.active_agents}</p>
                            <p>Avg Utilization: ${data.summary.gpu_utilization_avg.toFixed(1)}%</p>
                        </div>
                    `;
                }
            }

            // Auto-refresh every 5 seconds
            setInterval(loadData, 5000);
            loadData();
        </script>
    </body>
    </html>
    """


def get_fallback_public_website_html():
    """Fallback HTML for public JustNews website if template file is not available."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>JustNews - AI-Powered News Analysis</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            .hero-section { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 100px 0; }
            .news-card { transition: transform 0.2s; border: none; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .news-card:hover { transform: translateY(-5px); }
            .credibility-badge { position: absolute; top: 10px; right: 10px; padding: 5px 10px; border-radius: 20px; font-size: 0.8em; font-weight: bold; }
            .credibility-high { background: #28a745; color: white; }
            .credibility-medium { background: #ffc107; color: black; }
            .credibility-low { background: #dc3545; color: white; }
        </style>
    </head>
    <body>
        <!-- Navigation -->
        <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
            <div class="container">
                <a class="navbar-brand" href="#">
                    <i class="fas fa-newspaper"></i> JustNews
                </a>
                <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                    <span class="navbar-toggler-icon"></span>
                </button>
                <div class="collapse navbar-collapse" id="navbarNav">
                    <ul class="navbar-nav me-auto">
                        <li class="nav-item"><a class="nav-link active" href="#news">News</a></li>
                        <li class="nav-item"><a class="nav-link" href="#analysis">Analysis</a></li>
                        <li class="nav-item"><a class="nav-link" href="#sources">Sources</a></li>
                        <li class="nav-item"><a class="nav-link" href="#api">API</a></li>
                        <li class="nav-item dropdown">
                            <a class="nav-link dropdown-toggle" href="#" id="pagesDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">Pages</a>
                            <ul class="dropdown-menu" aria-labelledby="pagesDropdown">
                                <li><a class="dropdown-item" href="/">Home</a></li>
                                <li><a class="dropdown-item" href="/search">Search</a></li>
                                <li><a class="dropdown-item" href="/about">About</a></li>
                                <li><hr class="dropdown-divider"></li>
                                <li><a class="dropdown-item" href="/api/crawl/status">Crawler Status</a></li>
                                <li><a class="dropdown-item" href="/api/crawl/scheduler">Crawl Scheduler</a></li>
                                <li><a class="dropdown-item" href="/gpu/dashboard">GPU Dashboard</a></li>
                                <li><a class="dropdown-item" href="/transparency/status">Transparency</a></li>
                                <li><a class="dropdown-item" href="/api/metrics/crawler">Crawler Metrics</a></li>
                                <li><a class="dropdown-item" href="/api/health">System Health</a></li>
                            </ul>
                        </li>
                    </ul>
                    <form class="d-flex">
                        <input class="form-control me-2" type="search" placeholder="Search news..." id="searchInput">
                        <button class="btn btn-outline-light" type="button" onclick="searchNews()">Search</button>
                    </form>
                </div>
            </div>
        </nav>

        <!-- Hero Section -->
        <section class="hero-section">
            <div class="container text-center">
                <h1 class="display-4 mb-4">AI-Powered News Analysis</h1>
                <p class="lead mb-4">Discover news with transparent AI analysis, credibility scoring, and fact-checking</p>
                <div class="row text-center">
                    <div class="col-md-4">
                        <i class="fas fa-brain fa-3x mb-3"></i>
                        <h5>AI Analysis</h5>
                        <p>Sentiment, bias, and topic analysis</p>
                    </div>
                    <div class="col-md-4">
                        <i class="fas fa-shield-alt fa-3x mb-3"></i>
                        <h5>Fact Checking</h5>
                        <p>Source credibility and verification</p>
                    </div>
                    <div class="col-md-4">
                        <i class="fas fa-chart-line fa-3x mb-3"></i>
                        <h5>Transparency</h5>
                        <p>Open data and research APIs</p>
                    </div>
                </div>
            </div>
        </section>

        <!-- News Feed -->
        <section class="py-5" id="news">
            <div class="container">
                <h2 class="text-center mb-4">Latest News</h2>
                <div class="row" id="newsContainer">
                    <div class="col-12 text-center">
                        <div class="spinner-border" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <p>Loading news articles...</p>
                    </div>
                </div>
            </div>
        </section>

        <!-- Footer -->
        <footer class="bg-dark text-light py-4">
            <div class="container text-center">
                <p>&copy; 2025 JustNews. AI-powered news analysis platform.</p>
                <p>Built with transparency, accuracy, and trust.</p>
            </div>
        </footer>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            // Load news articles
            async function loadNews() {
                try {
                    const response = await fetch('/api/public/articles');
                    const data = await response.json();
                    displayNews(data.articles || []);
                } catch (error) {
                    console.error('Error loading news:', error);
                    document.getElementById('newsContainer').innerHTML = '<div class="col-12 text-center"><p class="text-muted">Unable to load news articles at this time.</p></div>';
                }
            }

            function displayNews(articles) {
                const container = document.getElementById('newsContainer');
                if (articles.length === 0) {
                    container.innerHTML = '<div class="col-12 text-center"><p class="text-muted">No articles available.</p></div>';
                    return;
                }

                container.innerHTML = articles.map(article => `
                    <div class="col-md-6 col-lg-4 mb-4">
                        <div class="card news-card h-100 position-relative">
                            <div class="credibility-badge credibility-${getCredibilityClass(article.source_credibility)}">
                                ${article.source_credibility}% Credible
                            </div>
                            <div class="card-body">
                                <h5 class="card-title">${article.title}</h5>
                                <p class="card-text text-muted">${article.summary}</p>
                                <div class="mb-2">
                                    <small class="text-muted">
                                        <i class="fas fa-user"></i> ${article.source} |
                                        <i class="fas fa-clock"></i> ${new Date(article.published_date).toLocaleDateString()}
                                    </small>
                                </div>
                                <div class="mb-2">
                                    <span class="badge bg-primary">${article.sentiment_score > 0 ? 'Positive' : article.sentiment_score < 0 ? 'Negative' : 'Neutral'}</span>
                                    <span class="badge bg-info">Fact Check: ${article.fact_check_score}%</span>
                                </div>
                                <p class="card-text"><small class="text-muted">${article.topics.join(', ')}</small></p>
                            </div>
                        </div>
                    </div>
                `).join('');
            }

            function getCredibilityClass(score) {
                if (score >= 80) return 'high';
                if (score >= 60) return 'medium';
                return 'low';
            }

            function searchNews() {
                const query = document.getElementById('searchInput').value;
                if (query.trim()) {
                    window.location.href = `/search?q=${encodeURIComponent(query)}`;
                }
            }

            // Load news on page load
            document.addEventListener('DOMContentLoaded', loadNews);
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("DASHBOARD_PORT", DASHBOARD_AGENT_PORT))

    logger.info(f"Starting Dashboard Agent on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
