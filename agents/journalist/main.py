"""
Journalist Agent - entrypoint

Lightweight agent wrapper that exposes a simple interface to the JournalistEngine.
This mirrors other agents' structure so it can be registered with MCP or run standalone
for local testing.
"""

from __future__ import annotations

import logging

from common.observability import bootstrap_observability

# Initialize observability for the Journalist agent
bootstrap_observability("journalist", level=logging.INFO)
from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402

from .journalist_engine import JournalistEngine  # noqa: E402
from .tools import health_check  # noqa: E402

# Compatibility: expose create_database_service for tests that patch agent modules
try:
    from database.utils.migrated_database_utils import (
        create_database_service,  # type: ignore
    )
except Exception:
    create_database_service = None

# MCP Bus Integration
try:
    from agents.common.mcp_bus_client import MCPBusClient
    MCP_AVAILABLE = True
except ImportError:
    MCPBusClient = None
    MCP_AVAILABLE = False

import os

logger = logging.getLogger(__name__)

engine: JournalistEngine | None = None
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")
JOURNALIST_PORT = int(os.environ.get("JOURNALIST_PORT", 8017))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    # Register with MCP Bus
    if MCP_AVAILABLE and MCPBusClient:
        try:
            mcp = MCPBusClient(base_url=MCP_BUS_URL)
            mcp.register_agent(
                agent_name="journalist",
                agent_address=f"http://localhost:{JOURNALIST_PORT}",
                tools=["crawl_url"]
            )
        except Exception as e:
            logger.warning(f"MCP Bus registration failed: {e}")

    logger.info("Starting Journalist agent...")
    engine = JournalistEngine()
    try:
        yield
    finally:
        logger.info("Shutting down Journalist agent...")
        if engine:
            await engine.shutdown()


app = FastAPI(title="Journalist Agent", version="0.1", lifespan=lifespan)


@app.get("/health")
async def _health():
    return health_check()


@app.post("/crawl_url")
async def crawl_url(payload: dict):
    """Trigger a crawl for a single URL via the journalist engine.

    Expects JSON like: { "url": "https://...", "mode": "standard" }
    """
    if engine is None:
        return {"success": False, "error": "Engine not initialized"}
    result = await engine.crawl_and_analyze(
        payload.get("url"), mode=payload.get("mode")
    )
    return result


if __name__ == "__main__":
    import os

    import uvicorn

    port = int(os.environ.get("JOURNALIST_PORT", 8017))
    uvicorn.run(app, host="0.0.0.0", port=port)
