"""
Training System MCP Bus Integration
Connects the isolated training system with the MCP Bus architecture for inter-agent communication
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
)
from pydantic import BaseModel, Field

from common.metrics import JustNewsMetrics
from common.observability import get_logger
from training_system.core.system_manager import get_system_training_manager
from training_system.core.training_coordinator import get_training_coordinator

# Configure centralized logging
logger = get_logger(__name__)

# Environment variables
TRAINING_SYSTEM_PORT: int = int(os.environ.get("TRAINING_SYSTEM_PORT", 8009))
MCP_BUS_URL: str = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

ready: bool = False


class TrainingMetrics(JustNewsMetrics):
    """Extended metrics class for training system specific metrics"""

    def __init__(self, agent_name: str = "training_system"):
        super().__init__(agent_name)
        self._init_training_metrics()

    def _init_training_metrics(self):
        """Initialize training-specific metrics"""
        # Training examples metrics
        self.training_examples_total = Counter(
            "justnews_training_examples_total",
            "Total number of training examples processed",
            [
                "agent",
                "agent_display_name",
                "example_type",
                "example_type_display_name",
            ],
            registry=self.registry,
        )

        self.training_examples_buffer_size = Gauge(
            "justnews_training_examples_buffer_size",
            "Current size of training example buffers",
            [
                "agent",
                "agent_display_name",
                "buffer_agent",
                "buffer_agent_display_name",
            ],
            registry=self.registry,
        )

        # Model update metrics
        self.model_updates_total = Counter(
            "justnews_model_updates_total",
            "Total number of model updates performed",
            [
                "agent",
                "agent_display_name",
                "target_agent",
                "target_agent_display_name",
                "update_type",
            ],
            registry=self.registry,
        )

        self.model_update_duration = Histogram(
            "justnews_model_update_duration_seconds",
            "Duration of model updates in seconds",
            [
                "agent",
                "agent_display_name",
                "target_agent",
                "target_agent_display_name",
            ],
            buckets=[10, 30, 60, 120, 300, 600, 1800],  # 10s to 30min
            registry=self.registry,
        )

        # Performance improvement metrics
        self.performance_improvement = Histogram(
            "justnews_performance_improvement",
            "Model performance improvements after training",
            [
                "agent",
                "agent_display_name",
                "target_agent",
                "target_agent_display_name",
            ],
            buckets=[-0.1, -0.05, -0.01, 0.0, 0.01, 0.05, 0.1, 0.2],
            registry=self.registry,
        )

        # Training system health metrics
        self.training_system_active = Gauge(
            "justnews_training_system_active",
            "Whether the training system is actively running",
            ["agent", "agent_display_name"],
            registry=self.registry,
        )

        self.rollback_events_total = Counter(
            "justnews_rollback_events_total",
            "Total number of model rollbacks due to performance degradation",
            [
                "agent",
                "agent_display_name",
                "target_agent",
                "target_agent_display_name",
            ],
            registry=self.registry,
        )

    def record_training_example(
        self, agent_name: str, example_type: str = "prediction_feedback"
    ):
        """Record a training example being added"""
        example_display = example_type.replace("_", "-")
        self.training_examples_total.labels(
            agent=self.agent_name,
            agent_display_name=self.display_name,
            example_type=example_type,
            example_type_display_name=example_display,
        ).inc()

    def update_buffer_size(self, buffer_agent: str, size: int):
        """Update training buffer size for an agent"""
        buffer_display = self.AGENT_DISPLAY_NAMES.get(
            buffer_agent, f"{buffer_agent}-agent"
        )
        self.training_examples_buffer_size.labels(
            agent=self.agent_name,
            agent_display_name=self.display_name,
            buffer_agent=buffer_agent,
            buffer_agent_display_name=buffer_display,
        ).set(size)

    def record_model_update(
        self,
        target_agent: str,
        update_type: str = "incremental",
        duration: float = None,
    ):
        """Record a model update event"""
        target_display = self.AGENT_DISPLAY_NAMES.get(
            target_agent, f"{target_agent}-agent"
        )

        self.model_updates_total.labels(
            agent=self.agent_name,
            agent_display_name=self.display_name,
            target_agent=target_agent,
            target_agent_display_name=target_display,
            update_type=update_type,
        ).inc()

        if duration is not None:
            self.model_update_duration.labels(
                agent=self.agent_name,
                agent_display_name=self.display_name,
                target_agent=target_agent,
                target_agent_display_name=target_display,
            ).observe(duration)

    def record_performance_change(self, target_agent: str, improvement: float):
        """Record performance improvement/degradation after training"""
        target_display = self.AGENT_DISPLAY_NAMES.get(
            target_agent, f"{target_agent}-agent"
        )
        self.performance_improvement.labels(
            agent=self.agent_name,
            agent_display_name=self.display_name,
            target_agent=target_agent,
            target_agent_display_name=target_display,
        ).observe(improvement)

    def record_rollback(self, target_agent: str):
        """Record a model rollback event"""
        target_display = self.AGENT_DISPLAY_NAMES.get(
            target_agent, f"{target_agent}-agent"
        )
        self.rollback_events_total.labels(
            agent=self.agent_name,
            agent_display_name=self.display_name,
            target_agent=target_agent,
            target_agent_display_name=target_display,
        ).inc()

    def set_training_active(self, active: bool):
        """Set training system active status"""
        self.training_system_active.labels(
            agent=self.agent_name, agent_display_name=self.display_name
        ).set(1 if active else 0)


# Global training metrics instance
training_metrics = TrainingMetrics()


class MCPBusClient:
    """MCP Bus client for training system communication"""

    def __init__(self, base_url: str = MCP_BUS_URL) -> None:
        self.base_url = base_url

    def register_agent(
        self, agent_name: str, agent_address: str, tools: list[str]
    ) -> None:
        """Register training system with MCP Bus"""
        registration_data = {
            "name": agent_name,
            "address": agent_address,
        }
        try:
            response = requests.post(
                f"{self.base_url}/register", json=registration_data, timeout=(2, 5)
            )
            response.raise_for_status()
            logger.info("Successfully registered %s with MCP Bus.", agent_name)
        except requests.exceptions.RequestException:
            logger.exception("Failed to register %s with MCP Bus.", agent_name)
            raise

    def call_agent_tool(
        self, agent: str, tool: str, args: list = None, kwargs: dict = None
    ) -> dict[str, Any]:
        """Call a tool on another agent via MCP Bus"""
        payload = {
            "agent": agent,
            "tool": tool,
            "args": args or [],
            "kwargs": kwargs or {},
        }
        try:
            response = requests.post(
                f"{self.base_url}/call", json=payload, timeout=(5, 10)
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to call {agent}.{tool}: {e}")
            raise


class TrainingRequest(BaseModel):
    """Request model for training operations"""

    agent_name: str = Field(..., description="Name of the agent to train")
    task_type: str = Field(..., description="Type of task for training")
    input_text: str = Field(..., description="Input text for training example")
    expected_output: Any = Field(..., description="Expected output for training")
    uncertainty_score: float = Field(
        ..., ge=0.0, le=1.0, description="Uncertainty score (0.0-1.0)"
    )
    importance_score: float = Field(
        0.5, ge=0.0, le=1.0, description="Importance score (0.0-1.0)"
    )
    source_url: str | None = Field(
        None, description="Source URL for the training example"
    )
    user_feedback: str | None = Field(
        None, description="User feedback or correction notes"
    )
    correction_priority: int = Field(
        0, ge=0, le=3, description="Correction priority (0-3)"
    )


class CorrectionRequest(BaseModel):
    """Request model for user corrections"""

    agent_name: str = Field(..., description="Name of the agent being corrected")
    task_type: str = Field(..., description="Type of task being corrected")
    input_text: str = Field(..., description="Original input text")
    incorrect_output: Any = Field(..., description="Incorrect output that was given")
    correct_output: Any = Field(..., description="Correct output that should be given")
    priority: int = Field(2, ge=0, le=3, description="Correction priority (0-3)")
    explanation: str | None = Field(None, description="Explanation of the correction")


class PredictionFeedback(BaseModel):
    """Request model for prediction feedback"""

    agent_name: str = Field(
        ..., description="Name of the agent that made the prediction"
    )
    task_type: str = Field(..., description="Type of task performed")
    input_text: str = Field(..., description="Input text that was processed")
    predicted_output: Any = Field(..., description="Output that was predicted")
    actual_output: Any = Field(..., description="Actual correct output")
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score of the prediction"
    )


class HitlCandidate(BaseModel):
    """Nested candidate payload passed from the HITL service."""

    id: str | None = None
    url: str | None = None
    site_id: str | None = None
    extracted_title: str | None = None
    extracted_text: str | None = None
    raw_html_ref: str | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    candidate_ts: str | None = None
    crawler_job_id: str | None = None


class HitlLabelPayload(BaseModel):
    """Training-forward payload originating from the HITL service."""

    label_id: str
    candidate_id: str
    label: str
    annotator_id: str | None = None
    source: str | None = None
    cleaned_text: str | None = None
    treat_as_valid: bool = False
    needs_cleanup: bool = False
    qa_sampled: bool = False
    ingest_job_id: str | None = None
    created_at: str | None = None
    ingestion_status: str | None = None
    candidate: HitlCandidate | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown context manager for training system"""
    logger.info("Training System is starting up.")

    # Initialize training system components
    try:
        # Initialize system-wide training manager (call for side-effects)
        _training_manager = get_system_training_manager()
        logger.info("System-wide training manager initialized")

        # Initialize training coordinator (call for side-effects)
        from training_system.core.training_coordinator import initialize_online_training

        _training_coordinator = initialize_online_training()
        logger.info("Online training coordinator initialized")

    except Exception as e:
        logger.error(f"Failed to initialize training system components: {e}")
        raise

    # Register with MCP Bus
    mcp_bus_client = MCPBusClient()
    try:
        mcp_bus_client.register_agent(
            agent_name="training_system",
            agent_address=f"http://localhost:{TRAINING_SYSTEM_PORT}",
            tools=[
                "add_training_example",
                "submit_user_correction",
                "add_prediction_feedback",
                "get_training_status",
                "get_system_training_dashboard",
                "force_agent_update",
                "get_training_metrics",
                "receive_hitl_label",
            ],
        )
        logger.info("Training System registered with MCP Bus")
    except Exception:
        logger.warning("MCP Bus unavailable; running in standalone mode.")

    global ready
    ready = True
    yield
    logger.info("Training System is shutting down.")


app = FastAPI(lifespan=lifespan, title="JustNews Training System", version="1.0.0")

# Initialize metrics
metrics = JustNewsMetrics("training_system")
app.middleware("http")(metrics.request_middleware)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy" if ready else "starting",
        "timestamp": datetime.now().isoformat(),
        "service": "training_system",
    }


@app.post("/tool/add_training_example")
async def add_training_example(request: TrainingRequest):
    """Add a training example to the system"""
    try:
        training_manager = get_system_training_manager()
        result = training_manager.add_training_example(
            agent_name=request.agent_name,
            task_type=request.task_type,
            input_text=request.input_text,
            expected_output=request.expected_output,
            uncertainty_score=request.uncertainty_score,
            importance_score=request.importance_score,
            source_url=request.source_url,
            user_feedback=request.user_feedback,
            correction_priority=request.correction_priority,
        )

        # Record metrics
        training_metrics.record_training_example(request.agent_name, "user_example")
        training_metrics.update_system_metrics()

        return {
            "status": "success",
            "message": "Training example added successfully",
            "data": result,
        }

    except Exception as e:
        logger.error(f"Failed to add training example: {e}")
        training_metrics.record_error(
            "training_example_error", "/tool/add_training_example"
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/tool/submit_user_correction")
async def submit_user_correction(request: CorrectionRequest):
    """Submit a user correction for model improvement"""
    try:
        training_manager = get_system_training_manager()
        result = training_manager.submit_user_correction(
            agent_name=request.agent_name,
            task_type=request.task_type,
            input_text=request.input_text,
            incorrect_output=request.incorrect_output,
            correct_output=request.correct_output,
            priority=request.priority,
            explanation=request.explanation,
        )

        return {
            "status": "success",
            "message": "User correction submitted successfully",
            "data": result,
        }

    except Exception as e:
        logger.error(f"Failed to submit user correction: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/tool/add_prediction_feedback")
async def add_prediction_feedback(request: PredictionFeedback):
    """Add prediction feedback from agent operations"""
    try:
        training_manager = get_system_training_manager()
        result = training_manager.add_prediction_feedback(
            agent_name=request.agent_name,
            task_type=request.task_type,
            input_text=request.input_text,
            predicted_output=request.predicted_output,
            actual_output=request.actual_output,
            confidence_score=request.confidence_score,
        )

        return {
            "status": "success",
            "message": "Prediction feedback added successfully",
            "data": result,
        }

    except Exception as e:
        logger.error(f"Failed to add prediction feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/tool/receive_hitl_label")
async def receive_hitl_label(payload: HitlLabelPayload):
    """Accept a HITL label payload and enqueue it for training."""

    try:
        training_manager = get_system_training_manager()
        result = training_manager.process_hitl_label(payload.model_dump(mode="python"))

        training_metrics.record_training_example(result["agent_name"], "hitl_label")
        training_metrics.update_buffer_size(
            result["agent_name"], result.get("buffer_size", 0)
        )

        return {
            "status": "success",
            "message": "HITL label accepted for training",
            "data": result,
        }
    except Exception as e:
        logger.error(f"Failed to process HITL label payload: {e}")
        training_metrics.record_error("hitl_label_error", "/tool/receive_hitl_label")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/tool/get_training_status")
async def get_training_status():
    """Get current training system status"""
    try:
        coordinator = get_training_coordinator()
        if coordinator:
            status = coordinator.get_training_status()
            return {"status": "success", "data": status}
        else:
            return {
                "status": "error",
                "message": "Training coordinator not initialized",
            }

    except Exception as e:
        logger.error(f"Failed to get training status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/tool/get_system_training_dashboard")
async def get_system_training_dashboard():
    """Get comprehensive training system dashboard data"""
    try:
        training_manager = get_system_training_manager()
        dashboard = training_manager.get_system_training_dashboard()

        return {"status": "success", "data": dashboard}

    except Exception as e:
        logger.error(f"Failed to get training dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/tool/force_agent_update")
async def force_agent_update(agent_name: str):
    """Force immediate model update for specific agent"""
    try:
        coordinator = get_training_coordinator()
        if coordinator:
            success = coordinator.force_update_agent(agent_name)
            return {
                "status": "success",
                "message": f"Update {'triggered' if success else 'not needed'} for {agent_name}",
                "data": {"update_triggered": success},
            }
        else:
            return {
                "status": "error",
                "message": "Training coordinator not initialized",
            }

    except Exception as e:
        logger.error(f"Failed to force agent update: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/tool/get_training_metrics")
async def get_training_metrics():
    """Get training system performance metrics"""
    try:
        training_manager = get_system_training_manager()
        metrics_data = training_manager.get_training_metrics()

        return {"status": "success", "data": metrics_data}

    except Exception as e:
        logger.error(f"Failed to get training metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# Global MCP Bus client instance
mcp_client = MCPBusClient()


def call_training_tool(tool_name: str, **kwargs) -> dict[str, Any]:
    """Convenience function to call training system tools via MCP Bus"""
    return mcp_client.call_agent_tool("training_system", tool_name, kwargs=kwargs)


def add_training_example_via_mcp(
    agent_name: str,
    task_type: str,
    input_text: str,
    expected_output: Any,
    uncertainty_score: float,
    importance_score: float = 0.5,
    **kwargs,
) -> dict[str, Any]:
    """Add training example via MCP Bus"""
    return call_training_tool(
        "add_training_example",
        agent_name=agent_name,
        task_type=task_type,
        input_text=input_text,
        expected_output=expected_output,
        uncertainty_score=uncertainty_score,
        importance_score=importance_score,
        **kwargs,
    )


def submit_correction_via_mcp(
    agent_name: str,
    task_type: str,
    input_text: str,
    incorrect_output: Any,
    correct_output: Any,
    priority: int = 2,
    **kwargs,
) -> dict[str, Any]:
    """Submit user correction via MCP Bus"""
    return call_training_tool(
        "submit_user_correction",
        agent_name=agent_name,
        task_type=task_type,
        input_text=input_text,
        incorrect_output=incorrect_output,
        correct_output=correct_output,
        priority=priority,
        **kwargs,
    )


def get_training_status_via_mcp() -> dict[str, Any]:
    """Get training status via MCP Bus"""
    return call_training_tool("get_training_status")


def get_training_dashboard_via_mcp() -> dict[str, Any]:
    """Get training dashboard via MCP Bus"""
    return call_training_tool("get_system_training_dashboard")
