"""
GPU Orchestrator - FastAPI application for GPU management and model preloading.

This module provides the REST API endpoints for GPU orchestration including:
- GPU telemetry and monitoring
- GPU lease allocation and management
- Model preloading with background job management
- Policy configuration and health checks
- MCP Bus integration for inter-agent communication
"""

import logging
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from agents.common.mcp_bus_client import MCPBusClient
from common.observability import bootstrap_observability

from .gpu_orchestrator_engine import engine
from .tools import (
    get_allocations,
    get_gpu_info,
    get_metrics,
    get_mps_allocation,
    get_policy,
    lease_gpu,
    models_preload,
    models_status,
    release_gpu_lease,
    set_policy,
)

# Configure observability for the GPU Orchestrator service
bootstrap_observability("gpu_orchestrator", level=logging.INFO)


def _require_admin(request: Request):
    """Admin guard used by orchestration endpoints.

    Accepts either ADMIN_API_KEY (static) or a role-based JWT (requires role=admin).
    Returns requestor info dict (may be empty) on success, or raises HTTPException.
    """
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
        # return simple admin identity
        return {"method": "api_key", "user": "admin_api_key"}

    if not auth_header:
        raise HTTPException(status_code=401, detail="Admin credentials missing")

    # JWT path
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1]
    else:
        token = auth_header

    try:
        import agents.common.auth_models as auth_models

        payload = auth_models.verify_token(token)
        if payload is None:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        user = auth_models.get_user_by_id(payload.user_id)
        if user is None or user.get("role") != auth_models.UserRole.ADMIN.value:
            raise HTTPException(status_code=403, detail="Admin role required")
        return {
            "method": "jwt",
            "user": {"user_id": payload.user_id, "username": payload.username},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail="Auth verification failed") from e


# Compatibility: expose create_database_service for tests that patch agent modules
try:
    from database.utils.migrated_database_utils import (
        create_database_service,  # type: ignore
    )
except Exception:
    create_database_service = None

# Constants
GPU_ORCHESTRATOR_PORT = int(os.environ.get("GPU_ORCHESTRATOR_PORT", "8014"))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")
SAFE_MODE = os.environ.get("SAFE_MODE", "false").lower() == "true"

# Global state
READINESS = False


class PolicyUpdate(BaseModel):
    """GPU policy update model."""

    max_memory_per_agent_mb: int | None = Field(
        None, ge=256, description="Per-agent memory cap in MB"
    )
    allow_fractional_shares: bool | None = None
    kill_on_oom: bool | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class LeaseRequest(BaseModel):
    """GPU lease request model."""

    agent: str
    min_memory_mb: int | None = Field(0, ge=0)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ReleaseRequest(BaseModel):
    """GPU lease release request model."""

    token: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class PreloadRequest(BaseModel):
    """Model preload request model."""

    agents: list[str] | None = Field(
        default=None,
        description="Subset of agents to preload; default all from AGENT_MODEL_MAP.json",
    )
    refresh: bool = Field(
        default=False, description="Restart preloading even if a job already completed"
    )
    strict: bool | None = Field(
        default=None, description="Override STRICT_MODEL_STORE env for this preload run"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


class WorkerPoolRequest(BaseModel):
    """Request payload for orchestrator-managed worker pools."""

    pool_id: str | None = Field(
        default=None,
        description="Explicit pool identifier; defaults to agent or timestamp",
    )
    agent: str | None = Field(
        default=None, description="Logical agent name used for auditing"
    )
    model: str | None = Field(default=None, description="Model identifier to load")
    adapter: str | None = Field(
        default=None,
        description="Optional adapter path to apply after loading the base model",
    )
    num_workers: int = Field(
        default=1, ge=1, le=64, description="Number of warm workers to spawn"
    )
    hold_seconds: int = Field(
        default=600,
        ge=1,
        le=7200,
        description="How long workers remain alive without external intervention",
    )
    variant: str | None = Field(
        default=None,
        description="Optional loading strategy hint (fp16, bnb-4bit-qlora, etc.)",
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global READINESS
    engine.logger.info("GPU Orchestrator starting up")
    engine.initialize_nvml()
    engine.logger.info("GPU Orchestrator startup sequence complete")

    # Registration status tracker
    registration_complete = threading.Event()

    def register_agent_background(
        agent_name: str, agent_address: str, tools: list[str]
    ):
        """Register the agent with the MCP Bus in a background thread."""

        def background_task():
            client = MCPBusClient(base_url=MCP_BUS_URL)
            try:
                client.register_agent(agent_name, agent_address, tools)
            finally:
                # Always signal completion — tests and startup shouldn't stall indefinitely
                registration_complete.set()  # Signal registration completion (success or fail)

        thread = threading.Thread(target=background_task, daemon=True)
        thread.start()

    # Start background registration
    register_agent_background(
        agent_name="gpu_orchestrator",
        agent_address=f"http://localhost:{GPU_ORCHESTRATOR_PORT}",
        tools=[
            "health",
            "gpu_info",
            "get_policy",
            "set_policy",
            "get_allocations",
            "lease",
            "release",
            "models_preload",
            "models_status",
            "mps_allocation",
        ],
    )

    # Wait for registration to complete before signaling readiness
    engine.logger.info("Waiting for MCP Bus registration to complete...")
    registration_complete.wait(timeout=30)  # Wait up to 30 seconds
    if registration_complete.is_set():
        engine.logger.info("MCP Bus registration completed successfully.")
    else:
        engine.logger.warning(
            "MCP Bus registration did not complete within the timeout."
        )

    READINESS = True
    yield
    engine.logger.info("GPU Orchestrator shutting down")


# Create FastAPI app
app = FastAPI(title="GPU Orchestrator", lifespan=lifespan)

# Add metrics middleware
app.middleware("http")(engine.metrics.request_middleware)

# Optional shared endpoints
try:
    from agents.common.shutdown import register_shutdown_endpoint

    register_shutdown_endpoint(app)
except Exception:
    engine.logger.debug("shutdown endpoint not registered for gpu_orchestrator")

try:
    from agents.common.reload import register_reload_endpoint

    register_reload_endpoint(app)
except Exception:
    engine.logger.debug("reload endpoint not registered for gpu_orchestrator")


@app.get("/health")
@app.post("/health")
async def health(request: Request):
    """Health check endpoint."""
    return {"status": "ok", "safe_mode": SAFE_MODE}


@app.get("/ready")
def ready():
    """Readiness check endpoint."""
    return {"ready": READINESS}


@app.get("/leader")
def get_leader(request: Request):
    """Return leader state for the orchestrator instance (true/false)."""
    # No admin required — provides visibility
    try:
        return {
            "is_leader": getattr(engine, "is_leader", False),
            "lock_name": getattr(engine, "_leader_lock_name", None),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/control/reclaim")
def trigger_reclaim(request: Request):
    """Trigger an immediate reclaim pass (leader only)."""
    _require_admin(request)
    try:
        if not getattr(engine, "is_leader", False):
            raise HTTPException(status_code=409, detail="not_leader")
        try:
            engine._reclaimer_pass()
            return {"reclaimed": True}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/gpu/info")
def gpu_info_endpoint():
    """Return current GPU telemetry (read-only)."""
    try:
        data = get_gpu_info()

        if not engine._NVML_SUPPORTED:
            data["nvml_init_error"] = engine._NVML_INIT_ERROR or "unsupported"
            engine.logger.warning(f"NVML not supported: {data['nvml_init_error']}")

        return data
    except Exception as e:
        engine.logger.error(f"Failed to get GPU snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/policy")
def get_policy_endpoint():
    """Get current GPU policy."""
    return get_policy()


@app.post("/policy")
def set_policy_endpoint(update: PolicyUpdate):
    """Update GPU policy."""
    return set_policy(
        max_memory_per_agent_mb=update.max_memory_per_agent_mb,
        allow_fractional_shares=update.allow_fractional_shares,
        kill_on_oom=update.kill_on_oom,
    )


@app.get("/allocations")
def get_allocations_endpoint():
    """Return current agent→GPU allocation view."""
    return get_allocations()


@app.post("/lease")
def lease_endpoint(req: LeaseRequest):
    """Obtain a simple ephemeral GPU lease."""
    return lease_gpu(req.agent, req.min_memory_mb)


@app.post("/leases/{token}/heartbeat")
def lease_heartbeat(request: Request, token: str):
    """Heartbeat a persisted lease token so it is not considered expired."""
    # best-effort (engine may not have DB connectivity)
    try:
        ok = engine.heartbeat_lease(token)
        if not ok:
            raise HTTPException(status_code=500, detail="heartbeat_failed")
        return {"token": token, "heartbeat": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/leases")
def list_leases(request: Request):
    """Admin endpoint to list persistent and in-memory leases."""
    _require_admin(request)
    try:
        # engine.get_allocations() will purge expired leases from memory
        mem = engine.get_allocations()
        resp = {"in_memory": mem}
        # Add persistent rows when DB accessible
        if getattr(engine, "db_service", None):
            try:
                try:
                    cursor, conn = engine._get_safe_cursor(per_call=True, dictionary=True, buffered=True)
                    try:
                        cursor.execute(
                            "SELECT token, agent_name, gpu_index, mode, created_at, expires_at, last_heartbeat, metadata FROM orchestrator_leases"
                        )
                        rows = cursor.fetchall()
                    finally:
                        try:
                            cursor.close()
                        except Exception:
                            pass
                        try:
                            if conn is not None:
                                conn.close()
                        except Exception:
                            pass
                    resp["persistent"] = rows
                except Exception:
                    resp["persistent"] = None
            except Exception:
                resp["persistent"] = None

        return resp
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/release")
def release_endpoint(req: ReleaseRequest):
    """Release a GPU lease."""
    return release_gpu_lease(req.token)


@app.post("/models/preload")
def models_preload_endpoint(req: PreloadRequest):
    """Start a background model preload job."""
    return models_preload(req.agents, req.refresh, req.strict)


@app.post("/workers/pool")
def create_worker_pool(
    request: Request,
    payload: WorkerPoolRequest | None = Body(default=None),
    agent: str | None = None,
    model: str | None = None,
    adapter: str | None = None,
    num_workers: int = 1,
    hold_seconds: int = 600,
    variant: str | None = None,
):
    """Create or reuse a named worker pool.

    Accepts either a JSON payload (preferred) or legacy query parameters for backwards compatibility.
    """

    body = payload.model_dump(exclude_unset=True) if payload else {}
    pool_id = (
        body.get("pool_id") or agent or body.get("agent") or f"pool_{int(time.time())}"
    )
    model_id = body.get("model") or model
    adapter_id = body.get("adapter") or adapter
    configured_workers = int(body.get("num_workers", num_workers))
    hold_time = int(body.get("hold_seconds", hold_seconds))
    variant_hint = body.get("variant") or variant

    # Require admin and capture requestor identity for audit
    requestor = _require_admin(request)
    try:
        requestor["ip"] = request.client.host
    except Exception:
        pass

    try:
        resp = engine.start_worker_pool(
            pool_id=pool_id,
            model_id=model_id,
            adapter=adapter_id,
            num_workers=configured_workers,
            hold_seconds=hold_time,
            requestor=requestor,
            variant=variant_hint,
        )
        return resp
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/workers/pool")
def list_pools(request: Request):
    # listing pools is a sensitive operational endpoint — restrict to admins
    _require_admin(request)
    return engine.list_worker_pools()


@app.delete("/workers/pool/{pool_id}")
def delete_pool(request: Request, pool_id: str):
    requestor = _require_admin(request)
    try:
        requestor["ip"] = request.client.host
    except Exception:
        pass
    try:
        resp = engine.stop_worker_pool(pool_id)
        # audit stop with requestor
        engine._audit_worker_pool_event(
            "stop", pool_id, None, None, 0, requestor=requestor
        )
        return resp
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="unknown_pool") from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/models/status")
def models_status_endpoint():
    """Return current model preload status."""
    return models_status()


@app.get("/vllm/status")
def vllm_status_endpoint():
    """Return VLLM server status."""
    return engine.get_vllm_status()


@app.post("/jobs/submit")
def jobs_submit(request: Request, payload: dict):
    """Submit a job to the orchestrator: persists and optionally pushes to job stream."""
    # admin or agent may submit jobs; always accept
    try:
        job_id = payload.get("job_id") or f"job_{int(time.time() * 1000)}"
        job_type = payload.get("type") or "inference_jobs"
        job_payload = payload.get("payload") or {}
        resp = engine.submit_job(job_id, job_type, job_payload)
        return resp
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/jobs/{job_id}")
def jobs_get(request: Request, job_id: str):
    _require_admin(request)
    try:
        record = engine.get_job(job_id)
        if not record:
            raise HTTPException(status_code=404, detail="not_found")
        return record
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/mps/allocation")
def get_mps_allocation_endpoint():
    """Return MPS resource allocation configuration."""
    return get_mps_allocation()


@app.get("/metrics")
def get_metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(get_metrics(), media_type="text/plain")


@app.get("/tools")
def list_tools_endpoint():
    """List all tools exposed by the GPU Orchestrator."""
    return {
        "tools": [
            "health",
            "gpu_info",
            "get_policy",
            "set_policy",
            "get_allocations",
            "lease",
            "release",
            "models_preload",
            "models_status",
            "mps_allocation",
        ]
    }


@app.post("/notify_ready")
def notify_ready_endpoint():
    """Handle notification from MCP Bus that it is ready."""
    try:
        client = MCPBusClient(base_url=MCP_BUS_URL)
        client.register_agent(
            agent_name="gpu_orchestrator",
            agent_address=f"http://localhost:{GPU_ORCHESTRATOR_PORT}",
            tools=[
                "health",
                "gpu_info",
                "get_policy",
                "set_policy",
                "get_allocations",
                "lease",
                "release",
                "models_preload",
                "models_status",
                "mps_allocation",
            ],
        )
        engine.logger.info(
            "Successfully registered GPU Orchestrator with MCP Bus after notification."
        )
    except Exception as e:
        engine.logger.error(f"Failed to register GPU Orchestrator with MCP Bus: {e}")
        raise HTTPException(status_code=500, detail="Registration failed") from e


@app.get("/workers/policy")
def get_pool_policy():
    return engine.get_pool_policy()


@app.post("/workers/policy")
def set_pool_policy(request: Request, payload: dict):
    requestor = _require_admin(request)
    try:
        requestor["ip"] = request.client.host
    except Exception:
        pass
    try:
        new = engine.set_pool_policy(payload)
        # Persist policy to system configuration for durable storage
        try:
            from config.core import get_config_manager

            mgr = get_config_manager()
            mgr.update_config({"gpu_orchestrator": {"pool_policy": payload}})
        except Exception:
            # if persistence fails, log & continue — do not block operator action
            engine.logger.warning("Failed to persist pool policy to system config")

        engine._audit_policy_event("policy_update", payload, requestor=requestor)
        return new
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/workers/pool/{pool_id}/swap")
def swap_pool_adapter(
    request: Request,
    pool_id: str,
    new_adapter: str | None = None,
    wait_seconds: int = 10,
):
    requestor = _require_admin(request)
    try:
        requestor["ip"] = request.client.host
    except Exception:
        pass
    try:
        return engine.hot_swap_pool_adapter(
            pool_id=pool_id,
            new_adapter=new_adapter,
            requestor=requestor,
            wait_seconds=wait_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="unknown_pool") from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=GPU_ORCHESTRATOR_PORT)


# Backwards-compatibility: expose ALLOCATIONS at module level for tests that import it
try:
    try:
        ALLOCATIONS = get_allocations()
    except Exception:
        # Fall back to an empty allocation mapping if retrieving allocations fails at import-time
        ALLOCATIONS = {}
except NameError:
    # If get_allocations isn't available for some reason, expose an empty dict
    ALLOCATIONS = {}
