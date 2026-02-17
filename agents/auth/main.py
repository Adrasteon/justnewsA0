"""
Authentication Service for JustNews

FastAPI application providing user authentication, authorization, and session management.
Implements JWT-based authentication with role-based access control and GDPR compliance.
"""

import asyncio
import os
import signal
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from common.observability import bootstrap_observability, get_logger

# Compatibility: expose create_database_service for tests that patch agent modules
try:
    from database.utils.migrated_database_utils import (
        create_database_service,  # type: ignore
    )
except Exception:
    create_database_service = None
from agents.auth.auth_engine import (
    get_auth_engine,
    initialize_auth_engine,
    shutdown_auth_engine,
)
from agents.common.auth_api import router as auth_router

bootstrap_observability("auth")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown"""
    # Startup
    logger.info("🚀 Starting Authentication Service...")

    try:
        # Initialize authentication engine
        if not await initialize_auth_engine():
            logger.error("❌ Failed to initialize authentication engine")
            sys.exit(1)

        logger.info("✅ Authentication Service started successfully")

    except Exception as e:
        logger.error(f"❌ Authentication Service startup failed: {e}")
        sys.exit(1)

    yield

    # Shutdown
    logger.info("🛑 Shutting down Authentication Service...")

    try:
        await shutdown_auth_engine()
        logger.info("✅ Authentication Service shutdown complete")

    except Exception as e:
        logger.error(f"❌ Authentication Service shutdown error: {e}")


# Create FastAPI application
app = FastAPI(
    title="JustNews Authentication Service",
    description="User authentication, authorization, and session management service",
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


@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "JustNews Authentication Service",
        "version": "1.0.0",
        "description": "JWT-based authentication with role-based access control",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint"""
    try:
        engine = get_auth_engine()
        health_info = await engine.health_check()

        # Determine HTTP status code based on health
        status_code = 200 if health_info["status"] == "healthy" else 503

        return JSONResponse(content=health_info, status_code=status_code)

    except Exception as e:
        logger.error(f"Health check error: {e}")
        return JSONResponse(
            content={
                "service": "auth_service",
                "status": "error",
                "error": str(e),
                "timestamp": asyncio.get_event_loop().time(),
            },
            status_code=503,
        )


@app.get("/info")
async def service_info():
    """Get service information and capabilities"""
    try:
        engine = get_auth_engine()
        info = engine.get_service_info()
        return info

    except Exception as e:
        logger.error(f"Service info error: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get service information"
        ) from e


@app.get("/ready")
async def readiness_check():
    """Service readiness probe endpoint (systemd)"""
    try:
        engine = get_auth_engine()
        if engine.is_initialized():
            return {"status": "ready"}
        else:
            return JSONResponse(
                content={"status": "not ready", "reason": "engine not initialized"},
                status_code=503,
            )

    except Exception as e:
        logger.error(f"Readiness check error: {e}")
        return JSONResponse(
            content={"status": "error", "error": str(e)}, status_code=503
        )


# Include authentication router
app.include_router(auth_router)


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
    """Main entry point for running the authentication service"""
    import uvicorn

    # Get configuration from environment
    host = "0.0.0.0"  # Bind to all interfaces
    port = int(os.environ.get("AUTH_SERVICE_PORT", "8018"))
    workers = int(os.environ.get("AUTH_WORKERS", "1"))
    reload = os.environ.get("AUTH_RELOAD", "false").lower() == "true"

    logger.info(f"🔐 Starting Authentication Service on {host}:{port}")

    # Configure uvicorn
    config = uvicorn.Config(
        app=app, host=host, port=port, workers=workers, reload=reload, log_level="info"
    )

    server = uvicorn.Server(config)

    # Handle graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"🛑 Received signal {signum}, shutting down...")
        server.should_exit = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the server
    server.run()


if __name__ == "__main__":
    main()
