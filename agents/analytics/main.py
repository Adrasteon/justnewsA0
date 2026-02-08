"""
Analytics Service for JustNews

FastAPI application providing advanced analytics, performance monitoring, and optimization
recommendations. Includes comprehensive system health monitoring and interactive dashboard.
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agents.analytics.analytics_engine import (
    get_analytics_engine,
    initialize_analytics_engine,
    shutdown_analytics_engine,
)
from agents.analytics.dashboard import create_analytics_app
from agents.common.mcp_bus_client import MCPBusClient
from common.metrics import JustNewsMetrics
from common.observability import bootstrap_observability, get_logger

bootstrap_observability("analytics")
logger = get_logger(__name__)

# Environment variables
ANALYTICS_AGENT_PORT = int(os.environ.get("ANALYTICS_AGENT_PORT", 8011))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

ready = False


# Define the lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown"""
    logger.info("📊 Analytics agent is starting up.")

    # Initialize analytics engine
    try:
        if not await initialize_analytics_engine():
            logger.error("❌ Failed to initialize analytics engine")
            sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Analytics engine initialization failed: {e}")
        sys.exit(1)

    # Register with MCP Bus
    mcp_bus_client = MCPBusClient(base_url=MCP_BUS_URL)
    try:
        mcp_bus_client.register_agent(
            agent_name="analytics",
            agent_address=f"http://localhost:{ANALYTICS_AGENT_PORT}",
            tools=[
                "get_system_health",
                "get_performance_metrics",
                "get_agent_profile",
                "get_optimization_recommendations",
            ],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")

    global ready
    ready = True
    logger.info("✅ Analytics agent started successfully")

    yield

    # Shutdown
    logger.info("🛑 Analytics agent is shutting down.")
    try:
        await shutdown_analytics_engine()
        logger.info("✅ Analytics agent shutdown complete")
    except Exception as e:
        logger.error(f"❌ Analytics agent shutdown error: {e}")


# Initialize FastAPI with the lifespan context manager
app = FastAPI(
    title="JustNews Analytics Service",
    description="Advanced analytics and performance monitoring service",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize metrics
metrics = JustNewsMetrics("analytics")
app.middleware("http")(metrics.request_middleware)

# Register common shutdown endpoint
try:
    from agents.common.shutdown import register_shutdown_endpoint

    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for analytics")

# Register reload endpoint if available
try:
    from agents.common.reload import register_reload_endpoint

    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for analytics")

# Include the analytics dashboard routes
analytics_dashboard = create_analytics_app()
app.mount("/dashboard", analytics_dashboard, name="analytics-dashboard")


@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "JustNews Analytics Service",
        "version": "1.0.0",
        "description": "Advanced analytics and performance monitoring",
        "status": "running",
        "dashboard": "/dashboard",
    }


@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint"""
    try:
        engine = get_analytics_engine()
        health_info = await engine.health_check()

        # Determine HTTP status code based on health
        status_code = 200 if health_info["status"] == "healthy" else 503

        return JSONResponse(content=health_info, status_code=status_code)

    except Exception as e:
        logger.error(f"Health check error: {e}")
        return JSONResponse(
            content={
                "service": "analytics_service",
                "status": "error",
                "error": str(e),
                "timestamp": asyncio.get_event_loop().time(),
            },
            status_code=503,
        )


@app.get("/ready")
async def readiness_check():
    """Service readiness probe endpoint (systemd)"""
    return {"ready": ready}


@app.get("/info")
async def service_info():
    """Get service information and capabilities"""
    try:
        engine = get_analytics_engine()
        info = engine.get_service_info()
        return info

    except Exception as e:
        logger.error(f"Service info error: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get service information"
        ) from e


# Metrics endpoint
@app.get("/metrics")
def get_metrics():
    """Prometheus metrics endpoint."""
    from fastapi import Response

    return Response(content=metrics.get_metrics(), media_type="text/plain")


# Pydantic models


class ToolCall(BaseModel):
    args: list
    kwargs: dict


class PerformanceMetrics(BaseModel):
    agent_name: str
    operation: str
    processing_time_s: float
    batch_size: int
    success: bool
    gpu_memory_allocated_mb: float = 0.0
    gpu_memory_reserved_mb: float = 0.0
    gpu_utilization_pct: float = 0.0
    temperature_c: float = 0.0
    power_draw_w: float = 0.0
    throughput_items_per_s: float = 0.0


@app.post("/get_system_health")
def get_system_health(call: ToolCall):
    """Get comprehensive system health metrics"""
    try:
        engine = get_analytics_engine()
        health = engine.get_system_health()

        logger.info("Retrieved system health metrics")
        return {"status": "success", "data": health}
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/get_performance_metrics")
def get_performance_metrics(call: ToolCall):
    """Get real-time performance metrics for specified time period"""
    try:
        kwargs = call.kwargs or {}
        hours = kwargs.get("hours", 1)

        if hours < 1 or hours > 24:
            raise HTTPException(
                status_code=400, detail="Hours must be between 1 and 24"
            )

        engine = get_analytics_engine()
        analytics = engine.get_performance_metrics(hours=hours)

        logger.info(f"Retrieved performance metrics for {hours} hours")
        return {"status": "success", "data": analytics}
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/get_agent_profile")
def get_agent_profile(call: ToolCall):
    """Get performance profile for specific agent"""
    try:
        kwargs = call.kwargs or {}
        agent_name = kwargs.get("agent_name")
        hours = kwargs.get("hours", 24)

        if not agent_name:
            raise HTTPException(status_code=400, detail="agent_name is required")

        if hours < 1 or hours > 168:  # Max 1 week
            raise HTTPException(
                status_code=400, detail="Hours must be between 1 and 168"
            )

        engine = get_analytics_engine()
        profile = engine.get_agent_profile(agent_name, hours=hours)

        logger.info(f"Retrieved profile for agent {agent_name}")
        return {"status": "success", "data": profile}
    except Exception as e:
        logger.error(f"Error getting agent profile: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/get_optimization_recommendations")
def get_optimization_recommendations(call: ToolCall):
    """Get advanced optimization recommendations"""
    try:
        kwargs = call.kwargs or {}
        hours = kwargs.get("hours", 24)

        engine = get_analytics_engine()
        recommendations = engine.get_optimization_recommendations(hours)

        logger.info(f"Generated {len(recommendations)} optimization recommendations")
        return {"status": "success", "data": recommendations}
    except Exception as e:
        logger.error(f"Error getting optimization recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/record_performance_metric")
def record_performance_metric(call: ToolCall):
    """Record a custom performance metric"""
    try:
        kwargs = call.kwargs or {}

        # Validate required fields
        required_fields = [
            "agent_name",
            "operation",
            "processing_time_s",
            "batch_size",
            "success",
        ]
        for field in required_fields:
            if field not in kwargs:
                raise HTTPException(
                    status_code=400, detail=f"Missing required field: {field}"
                )

        engine = get_analytics_engine()
        success = engine.record_performance_metric(kwargs)

        if success:
            logger.info(f"Recorded performance metric for {kwargs['agent_name']}")
            return {"status": "success", "message": "Metric recorded successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to record metric")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording performance metric: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled exceptions"""
    logger.error(f"Unhandled exception in {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if app.debug else "An unexpected error occurred",
        },
    )


def main():
    """Main entry point for running the analytics service"""
    import uvicorn

    # Get configuration from environment
    host = "0.0.0.0"  # Bind to all interfaces
    port = ANALYTICS_AGENT_PORT
    workers = int(os.environ.get("ANALYTICS_WORKERS", "1"))
    reload = os.environ.get("ANALYTICS_RELOAD", "false").lower() == "true"

    logger.info(f"📊 Starting Analytics Service on {host}:{port}")

    # Configure uvicorn
    config = uvicorn.Config(
        app=app, host=host, port=port, workers=workers, reload=reload, log_level="info"
    )

    server = uvicorn.Server(config)

    # Handle graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"🛑 Received signal {signum}, shutting down...")
        server.should_exit = True

    import signal

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the server
    server.run()


if __name__ == "__main__":
    main()
