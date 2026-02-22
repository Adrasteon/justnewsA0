"""
Workflow Orchestrator Agent - Main FastAPI Application.
"""

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from common.observability import bootstrap_observability, get_logger
from common.metrics import get_metrics
from agents.common.mcp_bus_client import MCPBusClient
from database.utils.migrated_database_utils import create_database_service, get_db_config
from .engine import OrchestratorEngine
from .runtime_config import (
    RUNTIME_KEY_REGISTRY,
    RuntimeConfigStore,
    TIER_KEY_PREFIXES,
    extract_owner_overrides,
    get_lane_policy_runtime_examples,
)
from .tools import get_orchestrator_status, force_run_policy

# Initialize Logging
bootstrap_observability("workflow_orchestrator")
logger = get_logger(__name__)

# Constants
PORT = int(os.environ.get("WORKFLOW_ORCHESTRATOR_PORT", 8023))
HOST = os.environ.get("HOST", "0.0.0.0")
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "localhost")
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")
os.environ.setdefault("JUSTNEWS_DB_EMBEDDING_ENABLED", "0")

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
runtime_store = RuntimeConfigStore()
metrics = get_metrics("workflow_orchestrator")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and Shutdown logic."""
    logger.info("🎼 Workflow Orchestrator Agent Starting...")

    # Bind runtime store so engine can poll config version and apply owner overrides each tick
    engine.attach_runtime_store(runtime_store)
    
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
app.middleware("http")(metrics.request_middleware)

class ToolCall(BaseModel):
    args: list[Any]
    kwargs: dict[str, Any]


class RuntimeConfigValidateRequest(BaseModel):
    patch: dict[str, Any]


class RuntimeConfigApplyRequest(BaseModel):
    patch: dict[str, Any]
    reason: str
    actor: str | None = "operator"


class RuntimeConfigRollbackRequest(BaseModel):
    target_version: int
    reason: str
    actor: str | None = "operator"


class RuntimeActuationRequest(BaseModel):
    tier: str
    patch: dict[str, Any]
    reason: str
    actor: str | None = "operator"


class RuntimeActuationRollbackRequest(BaseModel):
    apply_version: int
    reason: str
    actor: str | None = "operator"

@app.get("/health")
async def health_check():
    return {"status": "healthy", "engine_running": engine.running}


@app.get("/metrics")
async def metrics_endpoint():
    return Response(metrics.get_metrics(), media_type="text/plain; charset=utf-8")

@app.get("/status")
async def status_endpoint():
    return get_orchestrator_status(engine)


@app.get("/autonomic/status")
async def autonomic_status_endpoint():
    return get_orchestrator_status(engine)


@app.get("/runtime-config")
async def runtime_config_get():
    state = runtime_store.get_state()
    owner_overrides = extract_owner_overrides(
        state.get("overrides", {}), "workflow_orchestrator"
    )
    available_versions = [
        int(entry.get("version", 0)) for entry in state.get("timeline", [])
    ]
    return {
        "status": "ok",
        "config_version": state.get("version", 0),
        "updated_at": state.get("updated_at"),
        "registry": RUNTIME_KEY_REGISTRY,
        "tier_key_prefixes": TIER_KEY_PREFIXES,
        "runtime_overrides": state.get("overrides", {}),
        "owner_overrides": owner_overrides,
        "effective_owner_config": engine.config,
        "available_versions": sorted(set(available_versions)),
        "audit_log_tail": state.get("audit_log", [])[-20:],
    }


@app.post("/runtime-config/validate")
async def runtime_config_validate(request: RuntimeConfigValidateRequest):
    result = runtime_store.validate_patch(request.patch)
    return {
        "status": "ok" if result.ok else "error",
        "ok": result.ok,
        "normalized": result.normalized,
        "errors": result.errors,
        "warnings": result.warnings,
        "blocked_non_hot": result.blocked_non_hot,
        "impacted_services": result.impacted_services,
    }


@app.get("/runtime-config/examples")
async def runtime_config_examples():
    return {
        "status": "ok",
        "examples": get_lane_policy_runtime_examples(),
    }


@app.patch("/runtime-config")
async def runtime_config_apply(request: RuntimeConfigApplyRequest):
    reason = str(request.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")

    response = runtime_store.apply_patch(
        request.patch,
        reason=reason,
        actor=str(request.actor or "operator"),
    )
    if response.get("status") != "ok":
        raise HTTPException(status_code=400, detail=response)

    owner_overrides = extract_owner_overrides(
        runtime_store.get_state().get("overrides", {}), "workflow_orchestrator"
    )
    apply_result = engine.apply_runtime_overrides(owner_overrides)

    response["owner_apply_result"] = apply_result
    response["owner"] = "workflow_orchestrator"
    return response


@app.post("/runtime-config/rollback")
async def runtime_config_rollback(request: RuntimeConfigRollbackRequest):
    reason = str(request.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")

    response = runtime_store.rollback(
        request.target_version,
        reason=reason,
        actor=str(request.actor or "operator"),
    )
    if response.get("status") != "ok":
        raise HTTPException(status_code=400, detail=response)

    owner_overrides = extract_owner_overrides(
        runtime_store.get_state().get("overrides", {}), "workflow_orchestrator"
    )
    apply_result = engine.apply_runtime_overrides(owner_overrides)
    response["owner_apply_result"] = apply_result
    response["owner"] = "workflow_orchestrator"
    return response


@app.post("/runtime-config/actuate")
async def runtime_config_actuate(request: RuntimeActuationRequest):
    reason = str(request.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")

    response = runtime_store.apply_tier_patch(
        request.tier,
        request.patch,
        reason=reason,
        actor=str(request.actor or "operator"),
    )
    if response.get("status") != "ok":
        raise HTTPException(status_code=400, detail=response)

    owner_overrides = extract_owner_overrides(
        runtime_store.get_state().get("overrides", {}), "workflow_orchestrator"
    )
    apply_result = engine.apply_runtime_overrides(owner_overrides)
    response["owner_apply_result"] = apply_result
    response["owner"] = "workflow_orchestrator"
    return response


@app.post("/runtime-config/actuate/rollback")
async def runtime_config_actuation_rollback(request: RuntimeActuationRollbackRequest):
    reason = str(request.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")

    response = runtime_store.rollback_apply_version(
        request.apply_version,
        reason=reason,
        actor=str(request.actor or "operator"),
    )
    if response.get("status") != "ok":
        raise HTTPException(status_code=400, detail=response)

    owner_overrides = extract_owner_overrides(
        runtime_store.get_state().get("overrides", {}), "workflow_orchestrator"
    )
    apply_result = engine.apply_runtime_overrides(owner_overrides)
    response["owner_apply_result"] = apply_result
    response["owner"] = "workflow_orchestrator"
    return response

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
