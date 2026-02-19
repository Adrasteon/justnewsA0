"""
MCP Bus Agent - Main FastAPI Application

This is the main entry point for the MCP Bus agent, providing RESTful APIs
for inter-agent communication and coordination using the Model Context Protocol.

Features:
- FastAPI web server for agent communication
- Agent registration and management endpoints
- Tool calling with circuit breaker protection
- Health checks and monitoring
- Production-ready error handling and logging

Endpoints:
- POST /register: Register an agent with the bus
- POST /call: Call a tool on a registered agent
- GET /agents: List all registered agents
- GET /health: Health check endpoint
- GET /ready: Readiness check endpoint
- GET /stats: Bus statistics and metrics
- GET /circuit_breaker_status: Circuit breaker status
- GET /metrics: Prometheus metrics endpoint
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from common.metrics import JustNewsMetrics
from common.observability import bootstrap_observability, get_logger

# Initialize observability (logging + optional OTEL + optional Sentry)
bootstrap_observability("mcp_bus", level=logging.INFO)

# Compatibility: expose create_database_service for tests that patch agent modules
try:
    from database.utils.migrated_database_utils import (
        create_database_service,  # type: ignore
    )
except Exception:
    create_database_service = None
from .tools import (  # noqa: E402
    call_agent_tool,
    get_bus_stats,
    get_circuit_breaker_status,
    get_registered_agents,
    health_check,
    notify_gpu_orchestrator,
)
from .tools import register_agent as register_agent_tool  # noqa: E402

logger = get_logger(__name__)

# Global variables
ready = False
startup_time = time.time()
discovery_task = None
discovery_stop_event = None


def _agent_name_variants(agent_name: str) -> set[str]:
    """Return normalized variants for tolerant agent-name matching."""
    return {
        agent_name,
        agent_name.replace("-", "_"),
        agent_name.replace("_", "-"),
    }


def _is_agent_registered_by_name(agent_name: str) -> bool:
    """Check if an agent is already registered under any common name variant."""
    registered_names = set(get_registered_agents().keys())
    return bool(_agent_name_variants(agent_name).intersection(registered_names))


# Request/Response Models
class AgentRegistration(BaseModel):
    """Request model for agent registration."""

    name: str = Field(..., description="Name of the agent to register")
    address: str = Field(..., description="HTTP address of the agent")


class ToolCallRequest(BaseModel):
    """Request model for tool calling."""

    agent: str = Field(..., description="Name of the agent to call")
    tool: str = Field(..., description="Name of the tool to execute")
    args: list[Any] = Field(
        default_factory=list, description="Positional arguments for the tool"
    )
    kwargs: dict[str, Any] = Field(
        default_factory=dict, description="Keyword arguments for the tool"
    )


class ToolCallResponse(BaseModel):
    """Response model for tool calling."""

    status: str = Field(..., description="Call status ('success' or 'error')")
    data: dict[str, Any] | None = Field(None, description="Call result data")
    error: str | None = Field(None, description="Error message if call failed")
    timestamp: float = Field(..., description="Response timestamp")


class HealthResponse(BaseModel):
    """Response model for health checks."""

    timestamp: float = Field(..., description="Health check timestamp")
    overall_status: str = Field(..., description="Overall health status")
    components: dict[str, Any] = Field(..., description="Component health status")
    issues: list[str] = Field(..., description="List of issues found")
    stats: dict[str, Any] | None = Field(None, description="Bus statistics")


class StatsResponse(BaseModel):
    """Response model for bus statistics."""

    registered_agents: int = Field(..., description="Number of registered agents")
    total_circuit_breaker_failures: int = Field(
        ..., description="Total circuit breaker failures"
    )
    open_circuits: int = Field(..., description="Number of open circuits")
    agents_with_failures: int = Field(
        ..., description="Agents with circuit breaker failures"
    )
    uptime: float = Field(..., description="Service uptime in seconds")
    timestamp: float = Field(..., description="Statistics timestamp")


# Agent discovery configuration - Ref: /app/docs/canonical_port_mapping.md
KNOWN_AGENTS = {
    # Core Agents (8001-8023)
    "chief-editor": {"port": 8001, "env_var": "CHIEF_EDITOR_AGENT_PORT"},
    "scout": {"port": 8002, "env_var": "SCOUT_AGENT_PORT"},
    "fact-checker": {"port": 8018, "env_var": "FACT_CHECKER_AGENT_PORT"},
    "analyst": {"port": 8004, "env_var": "ANALYST_AGENT_PORT"},
    "synthesizer": {"port": 8005, "env_var": "SYNTHESIZER_AGENT_PORT"},
    "critic": {"port": 8006, "env_var": "CRITIC_AGENT_PORT"},
    "memory": {"port": 8007, "env_var": "MEMORY_AGENT_PORT"},
    "reasoning": {"port": 8008, "env_var": "REASONING_AGENT_PORT"},
    "newsreader": {"port": 8009, "env_var": "NEWSREADER_PORT"},  # Crawler
    "vllm-service": {"port": 8010, "env_var": "VLLM_SERVICE_PORT"},
    "analytics": {"port": 8012, "env_var": "ANALYTICS_AGENT_PORT"},
    "archive": {"port": 8012, "env_var": "ARCHIVE_AGENT_PORT"},
    "dashboard": {"port": 8013, "env_var": "DASHBOARD_PORT"},
    "gpu-orchestrator": {"port": 8014, "env_var": "GPU_ORCHESTRATOR_PORT"},
    "crawler-worker": {"port": 8015, "env_var": "CRAWLER_AGENT_PORT"},
    "crawler-control": {"port": 8016, "env_var": "CRAWLER_CONTROL_AGENT_PORT"},
    "journalist": {"port": 8017, "env_var": "JOURNALIST_PORT"},
    "auth-service": {"port": 8018, "env_var": "AUTH_SERVICE_PORT"},
    "hitl-service": {"port": 8019, "env_var": "HITL_SERVICE_PORT"},
    "workflow-orchestrator": {"port": 8023, "env_var": "WORKFLOW_ORCHESTRATOR_PORT"},
}


def get_agent_port(agent_name: str) -> int:
    """Get the port for a known agent, checking environment variables first."""
    if agent_name not in KNOWN_AGENTS:
        return None
    
    config = KNOWN_AGENTS[agent_name]
    env_var = config.get("env_var")
    
    if env_var:
        try:
            return int(os.environ.get(env_var, config.get("port")))
        except (ValueError, TypeError):
            pass
    
    return config.get("port")


async def discover_and_register_agents(only_missing: bool = False):
    """
    Discover running agents by polling known ports and register them with the bus.
    This allows agents to be discovered even if they restart after MCP Bus.
    """
    import asyncio
    import httpx
    
    if only_missing:
        logger.debug("🔍 Starting missing-agent discovery...")
    else:
        logger.info("🔍 Starting agent discovery...")
    discovered = 0
    
    for agent_name, config in KNOWN_AGENTS.items():
        if only_missing and _is_agent_registered_by_name(agent_name):
            continue

        port = get_agent_port(agent_name)
        if not port:
            continue
        
        agent_url = f"http://localhost:{port}"
        
        try:
            # Try to verify agent is running with a health check
            async with httpx.AsyncClient(timeout=2) as client:
                try:
                    response = await client.get(f"{agent_url}/health")
                    if response.status_code in (200, 404):  # 404 means endpoint missing but server is up
                        # Try to register the agent
                        result = register_agent_tool(agent_name, agent_url)
                        if result.get("status") in ("ok", "success"):
                            logger.info(f"✅ Discovered and registered {agent_name} at {agent_url}")
                            discovered += 1
                except httpx.ConnectError:
                    pass  # Agent not running on this port
                except asyncio.TimeoutError:
                    pass  # Agent not responding
        except Exception as e:
            logger.debug(f"Agent discovery check for {agent_name} on port {port}: {e}")
    
    if discovered > 0:
        logger.info(f"✅ Agent discovery complete: {discovered} agent(s) registered")
    else:
        logger.debug("ℹ️ No agents discovered via polling (they may register themselves)")


async def periodic_missing_agent_discovery_loop(interval_seconds: int, stop_event):
    """Periodically probe and register only missing agents."""
    import asyncio

    logger.info(
        "🔁 Periodic missing-agent discovery enabled (interval=%ss)", interval_seconds
    )

    while not stop_event.is_set():
        try:
            await discover_and_register_agents(only_missing=True)
        except Exception as e:
            logger.warning(f"⚠️ Missing-agent discovery iteration failed: {e}")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue


# Lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    global ready, discovery_task, discovery_stop_event
    import asyncio

    # Startup
    logger.info("🚀 Starting MCP Bus Agent...")

    try:
        # Discover and register any running agents
        await discover_and_register_agents()

        poll_interval = int(
            os.getenv("MCP_BUS_MISSING_AGENT_POLL_INTERVAL_SEC", "30")
        )
        if poll_interval > 0:
            discovery_stop_event = asyncio.Event()
            discovery_task = asyncio.create_task(
                periodic_missing_agent_discovery_loop(
                    interval_seconds=poll_interval,
                    stop_event=discovery_stop_event,
                )
            )
        else:
            logger.info("⏸️ Periodic missing-agent discovery disabled")
        
        # Notify GPU Orchestrator that MCP Bus is ready
        success = notify_gpu_orchestrator()
        if success:
            logger.info("✅ GPU Orchestrator notification successful")
        else:
            logger.warning("⚠️ GPU Orchestrator notification failed")

        ready = True
        logger.info("✅ MCP Bus Agent started successfully")

        yield

    except Exception as e:
        logger.error(f"❌ Failed to start MCP Bus Agent: {e}")
        raise
    finally:
        # Shutdown
        logger.info("🛑 Shutting down MCP Bus Agent...")
        if discovery_stop_event is not None:
            discovery_stop_event.set()
        if discovery_task is not None:
            discovery_task.cancel()
            try:
                await discovery_task
            except Exception:
                pass
        discovery_task = None
        discovery_stop_event = None
        ready = False
        logger.info("✅ MCP Bus Agent shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="MCP Bus Agent",
    description="Model Context Protocol Bus for inter-agent communication and coordination",
    version="2.0.0",
    lifespan=lifespan,
)

# Initialize metrics
metrics = JustNewsMetrics("mcp_bus")

# Add metrics middleware
app.middleware("http")(metrics.request_middleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register common shutdown endpoint
try:
    from agents.common.shutdown import register_shutdown_endpoint

    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for mcp_bus")

# Register reload endpoint
try:
    from agents.common.reload import register_reload_endpoint

    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for mcp_bus")


@app.get("/")
async def root():
    """Root endpoint with basic information."""
    return {
        "name": "MCP Bus Agent",
        "version": "2.0.0",
        "description": "Model Context Protocol Bus for inter-agent communication",
        "status": "running" if ready else "starting",
    }


@app.post("/register")
async def register_agent_endpoint(agent: AgentRegistration):
    """
    Register an agent with the MCP Bus.

    This endpoint allows agents to register themselves with the bus,
    making their tools available for inter-agent communication.
    """
    try:
        logger.info(f"📨 Agent registration request: {agent.name} at {agent.address}")

        result = register_agent_tool(agent.name, agent.address)

        logger.info(f"✅ Agent {agent.name} registered successfully")
        return result

    except ValueError as e:
        logger.error(f"❌ Invalid registration request: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"❌ Registration error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Registration failed: {str(e)}"
        ) from e


@app.post("/call", response_model=ToolCallResponse)
async def call_tool_endpoint(call: ToolCallRequest):
    """
    Call a tool on a registered agent.

    This endpoint routes tool calls to the appropriate registered agent
    with circuit breaker protection and retry logic.
    """
    try:
        logger.debug(f"📨 Tool call request: {call.agent}.{call.tool}")

        result = call_agent_tool(call.agent, call.tool, call.args, call.kwargs)

        response = ToolCallResponse(
            status=result.get("status", "unknown"),
            data=result.get("data"),
            error=result.get("error"),
            timestamp=time.time(),
        )

        logger.debug(f"✅ Tool call completed: {call.agent}.{call.tool}")
        return response

    except ValueError as e:
        logger.warning(f"❌ Tool call validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        logger.error(f"❌ Tool call runtime error: {e}")
        raise HTTPException(status_code=502, detail=str(e)) from e
    except ConnectionError as e:
        logger.error(f"❌ Tool call connection error: {e}")
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        logger.error(f"❌ Unexpected tool call error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Tool call failed: {str(e)}"
        ) from e


@app.get("/agents")
async def get_agents_endpoint():
    """
    Get all currently registered agents.

    Returns a mapping of agent names to their addresses.
    """
    try:
        agents = get_registered_agents()
        logger.debug(f"📋 Retrieved {len(agents)} registered agents")
        return agents
    except Exception as e:
        logger.error(f"❌ Failed to retrieve agents: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve agents: {str(e)}"
        ) from e


@app.get("/health", response_model=HealthResponse)
async def health_endpoint():
    """Health check endpoint for monitoring and load balancers."""
    try:
        health_result = health_check()
        return HealthResponse(**health_result)
    except Exception as e:
        logger.error(f"❌ Health check error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Health check failed: {str(e)}"
        ) from e


@app.get("/ready")
async def ready_endpoint():
    """Readiness check endpoint."""
    return {"ready": ready}


@app.get("/stats", response_model=StatsResponse)
async def stats_endpoint():
    """Get MCP Bus statistics and performance metrics."""
    try:
        stats = get_bus_stats()
        uptime = time.time() - startup_time

        response = StatsResponse(
            registered_agents=stats.get("registered_agents", 0),
            total_circuit_breaker_failures=stats.get(
                "total_circuit_breaker_failures", 0
            ),
            open_circuits=stats.get("open_circuits", 0),
            agents_with_failures=stats.get("agents_with_failures", 0),
            uptime=uptime,
            timestamp=time.time(),
        )

        logger.debug("📊 Bus statistics retrieved")
        return response

    except Exception as e:
        logger.error(f"❌ Stats retrieval error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Stats retrieval failed: {str(e)}"
        ) from e


@app.get("/circuit_breaker_status")
async def circuit_breaker_status_endpoint():
    """Get the current circuit breaker status for all agents."""
    try:
        status = get_circuit_breaker_status()
        logger.debug(f"🔌 Circuit breaker status retrieved for {len(status)} agents")
        return status
    except Exception as e:
        logger.error(f"❌ Failed to get circuit breaker status: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get circuit breaker status: {str(e)}"
        ) from e


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(metrics.get_metrics(), media_type="text/plain; charset=utf-8")


@app.get("/capabilities")
async def capabilities_endpoint():
    """Get MCP Bus capabilities and supported features."""
    return {
        "name": "MCP Bus Agent",
        "version": "2.0.0",
        "capabilities": [
            "agent_registration",
            "tool_calling",
            "circuit_breaker",
            "health_monitoring",
            "metrics_collection",
        ],
        "supported_protocols": ["http", "https"],
        "features": {
            "circuit_breaker": {
                "enabled": True,
                "failure_threshold": 3,
                "cooldown_seconds": 10,
                "max_retries": 3,
            },
            "timeouts": {"connect_timeout": 3.0, "read_timeout": 120.0},
        },
        "rate_limits": {"requests_per_minute": 1000, "concurrent_requests": 100},
    }


# Error handlers
@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle internal server errors."""
    logger.error(f"500 Internal Server Error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc)
            if os.getenv("DEBUG", "").lower() == "true"
            else "An unexpected error occurred",
        },
    )


@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 not found errors."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not found",
            "detail": f"Endpoint {request.url.path} not found",
        },
    )


@app.exception_handler(503)
async def service_unavailable_handler(request, exc):
    """Handle 503 service unavailable errors (circuit breaker)."""
    logger.warning(f"503 Service Unavailable: {exc}")
    return JSONResponse(
        status_code=503,
        content={
            "error": "Service temporarily unavailable",
            "detail": str(exc),
        },
    )


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("MCP_BUS_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_BUS_PORT", "8000"))

    reload_flag = os.environ.get("UVICORN_RELOAD", "false").lower() == "true"
    log_level = os.environ.get("UVICORN_LOG_LEVEL", "info")

    # When invoked via `python -m agents.mcp_bus.main` (systemd path), Uvicorn must
    # receive the fully-qualified module path; otherwise reload workers try to
    # import bare "main" which fails. Falling back keeps local `python main.py`
    # workflows functional.
    target = f"{__package__}.main:app" if __package__ else "main:app"

    logger.info("Starting MCP Bus Agent on %s:%s (reload=%s)", host, port, reload_flag)
    uvicorn.run(
        target,
        host=host,
        port=port,
        reload=reload_flag,
        log_level=log_level,
    )
