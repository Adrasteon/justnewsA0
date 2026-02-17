"""
Workflow Orchestrator Agent - Main FastAPI Application.
"""

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from common.observability import bootstrap_observability, get_logger
from agents.common.mcp_bus_client import MCPBusClient
from database.utils.migrated_database_utils import create_database_service, get_db_config
from .engine import OrchestratorEngine
from .tools import get_orchestrator_status, force_run_policy

# Initialize Logging
bootstrap_observability("workflow_orchestrator")
logger = get_logger(__name__)

# Constants
PORT = int(os.environ.get("WORKFLOW_ORCHESTRATOR_PORT", 8020))
HOST = os.environ.get("HOST", "0.0.0.0")
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "localhost")
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

# Initialize DB Service without ChromaDB to prevent segfaults
try:
    db_config = get_db_config()
    if 'database' in db_config and 'chromadb' in db_config['database']:
        logger.info("Disabling ChromaDB for Orchestrator to prevent initialization issues")
        del db_config['database']['chromadb']
    create_database_service(db_config)
except Exception as e:
    logger.warning(f"Failed to pre-initialize database service: {e}")

# Global Engine
engine = OrchestratorEngine()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and Shutdown logic."""
    logger.info("🎼 Workflow Orchestrator Agent Starting...")
    
    # Start Engine
    await engine.start()
    
    # Register with MCP Bus
    try:
        mcp_client = MCPBusClient(base_url=MCP_BUS_URL)
        agent_address = f"http://{PUBLIC_HOST}:{PORT}"
        mcp_client.register_agent(
            agent_name="workflow_orchestrator",
            agent_address=agent_address,
            tools=["get_status", "force_workflow"]
        )
    except Exception as e:
        logger.warning(f"MCP Bus registration failed: {e}")

    yield
    
    # Shutdown
    await engine.stop()
    logger.info("Workflow Orchestrator Agent Stopped.")

app = FastAPI(title="Workflow Orchestrator", lifespan=lifespan)

class ToolCall(BaseModel):
    args: list[Any]
    kwargs: dict[str, Any]

@app.get("/health")
async def health_check():
    return {"status": "healthy", "engine_running": engine.running}

@app.get("/status")
async def status_endpoint():
    return get_orchestrator_status(engine)

# MCP Tool Endpoints

@app.post("/get_status")
async def get_status_tool(call: ToolCall):
    """MCP Tool wrapper for status."""
    return get_orchestrator_status(engine)

@app.post("/force_workflow")
async def force_workflow_tool(call: ToolCall):
    """MCP Tool wrapper for forcing a policy."""
    policy_name = call.kwargs.get("policy_name")
    if not policy_name:
        return {"status": "error", "message": "policy_name required"}
    return force_run_policy(engine, policy_name)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
