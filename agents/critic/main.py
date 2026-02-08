"""
Critic Agent - Refactored FastAPI Application

This module provides a streamlined FastAPI application for the critic agent,
focusing on content analysis, critique synthesis, and quality assessment.

Key Features:
- Content critique and synthesis analysis
- Argument structure evaluation
- Editorial consistency checking
- Logical fallacy detection
- Source credibility assessment
- MCP Bus integration for inter-agent communication

All endpoints include comprehensive error handling, validation, and logging.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents.common.mcp_bus_client import MCPBusClient

# Import metrics library
from common.metrics import JustNewsMetrics
from common.observability import bootstrap_observability, get_logger

# Configure logging
bootstrap_observability("critic")
logger = get_logger(__name__)

# Environment variables
CRITIC_AGENT_PORT = int(os.environ.get("CRITIC_AGENT_PORT", 8006))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

ready = False



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Critic agent is starting up.")
    mcp_bus_client = MCPBusClient(MCP_BUS_URL)
    try:
        mcp_bus_client.register_agent(
            agent_name="critic",
            agent_address=f"http://localhost:{CRITIC_AGENT_PORT}",
            tools=[
                "critique_synthesis",
                "critique_neutrality",
                "analyze_argument_structure",
                "assess_editorial_consistency",
                "detect_logical_fallacies",
                "assess_source_credibility",
                "health_check",
                "validate_critique_result",
                "format_critique_output",
                "get_critic_engine",
            ],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")
    global ready
    ready = True
    yield
    logger.info("Critic agent is shutting down.")


app = FastAPI(
    title="Critic Agent API",
    description="Content analysis and critique services for editorial quality control",
    version="2.0.0",
    lifespan=lifespan,
)

# Initialize metrics
metrics = JustNewsMetrics("critic")

# Register shutdown endpoint if available
try:
    from agents.common.shutdown import register_shutdown_endpoint

    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for critic")

# Register reload endpoint if available
try:
    from agents.common.reload import register_reload_endpoint

    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for critic")

# Add metrics middleware
app.middleware("http")(metrics.request_middleware)


# Pydantic models
class ToolCall(BaseModel):
    """Standard MCP tool call format"""

    args: list[Any]
    kwargs: dict[str, Any]


class CritiqueRequest(BaseModel):
    """Critique request model"""

    content: str
    url: str | None = None
    context: str | None = None


class ArgumentAnalysisRequest(BaseModel):
    """Argument structure analysis request"""

    text: str
    url: str | None = None


class ConsistencyRequest(BaseModel):
    """Editorial consistency request"""

    text: str
    url: str | None = None


class FallacyRequest(BaseModel):
    """Logical fallacy detection request"""

    text: str
    url: str | None = None


class CredibilityRequest(BaseModel):
    """Source credibility assessment request"""

    text: str
    url: str | None = None


# Health and status endpoints
@app.get("/health")
def health():
    """Health check endpoint"""
    return {"status": "ok", "agent": "critic", "version": "2.0.0"}


@app.get("/ready")
def ready_endpoint():
    """Readiness check endpoint"""
    return {"ready": ready}


@app.get("/metrics")
def get_metrics():
    """Prometheus metrics endpoint"""
    from fastapi.responses import Response

    return Response(metrics.get_metrics(), media_type="text/plain")


# Core critique endpoints
@app.post("/critique_synthesis")
def critique_synthesis_endpoint(call: ToolCall):
    """Synthesize comprehensive content critique"""
    try:
        from .tools import critique_synthesis

        logger.info(f"Calling critique_synthesis with {len(call.args)} args")

        result = critique_synthesis(*call.args, **call.kwargs)

        # Log performance metrics
        if isinstance(result, dict) and "critique_score" in result:
            logger.info(
                f"✅ Critique synthesis complete: score {result['critique_score']:.1f}/10"
            )

        return result

    except Exception as e:
        logger.error(f"❌ Critique synthesis error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/critique_neutrality")
def critique_neutrality_endpoint(call: ToolCall):
    """Analyze content neutrality and bias indicators"""
    try:
        from .tools import critique_neutrality

        logger.info(f"Calling critique_neutrality with {len(call.args)} args")

        result = critique_neutrality(*call.args, **call.kwargs)

        # Log performance metrics
        if isinstance(result, dict) and "neutrality_score" in result:
            logger.info(
                f"✅ Neutrality analysis complete: score {result['neutrality_score']:.1f}/10"
            )

        return result

    except Exception as e:
        logger.error(f"❌ Neutrality analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# Specialized analysis endpoints
@app.post("/analyze_argument_structure")
def analyze_argument_structure_endpoint(request: ArgumentAnalysisRequest):
    """Analyze argument structure in content"""
    try:
        from .tools import analyze_argument_structure

        logger.info(f"Analyzing argument structure for {len(request.text)} characters")

        result = analyze_argument_structure(request.text, request.url)

        # Log performance metrics
        if isinstance(result, dict) and "argument_strength" in result:
            strength = result["argument_strength"].get("strength_score", 0.0)
            logger.info(f"✅ Argument analysis complete: strength {strength:.2f}")

        return result

    except Exception as e:
        logger.error(f"❌ Argument structure analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/assess_editorial_consistency")
def assess_editorial_consistency_endpoint(request: ConsistencyRequest):
    """Assess editorial consistency and coherence"""
    try:
        from .tools import assess_editorial_consistency

        logger.info(
            f"Assessing editorial consistency for {len(request.text)} characters"
        )

        result = assess_editorial_consistency(request.text, request.url)

        # Log performance metrics
        if isinstance(result, dict) and "coherence_score" in result:
            coherence = result["coherence_score"]
            logger.info(
                f"✅ Consistency assessment complete: coherence {coherence:.2f}"
            )

        return result

    except Exception as e:
        logger.error(f"❌ Editorial consistency error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/detect_logical_fallacies")
def detect_logical_fallacies_endpoint(request: FallacyRequest):
    """Detect logical fallacies in content"""
    try:
        from .tools import detect_logical_fallacies

        logger.info(f"Detecting logical fallacies in {len(request.text)} characters")

        result = detect_logical_fallacies(request.text, request.url)

        # Log performance metrics
        if isinstance(result, dict) and "fallacy_count" in result:
            count = result["fallacy_count"]
            logger.info(f"✅ Fallacy detection complete: {count} fallacies found")

        return result

    except Exception as e:
        logger.error(f"❌ Logical fallacy detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/assess_source_credibility")
def assess_source_credibility_endpoint(request: CredibilityRequest):
    """Assess source credibility and evidence quality"""
    try:
        from .tools import assess_source_credibility

        logger.info(f"Assessing source credibility for {len(request.text)} characters")

        result = assess_source_credibility(request.text, request.url)

        # Log performance metrics
        if isinstance(result, dict) and "credibility_score" in result:
            credibility = result["credibility_score"]
            logger.info(f"✅ Credibility assessment complete: score {credibility:.2f}")

        return result

    except Exception as e:
        logger.error(f"❌ Source credibility error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# Utility endpoints
@app.post("/health_check")
def health_check_endpoint(call: ToolCall):
    """Perform comprehensive health check"""
    try:
        from .tools import health_check

        logger.info("Performing critic agent health check")

        result = health_check()

        # Log health status
        if isinstance(result, dict) and "overall_status" in result:
            status = result["overall_status"]
            logger.info(f"🏥 Health check: {status}")

        return result

    except Exception as e:
        logger.error(f"❌ Health check error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/validate_critique_result")
def validate_critique_result_endpoint(call: ToolCall):
    """Validate critique result structure"""
    try:
        from .tools import validate_critique_result

        logger.info("Validating critique result")

        result = validate_critique_result(*call.args, **call.kwargs)
        return {"valid": result}

    except Exception as e:
        logger.error(f"❌ Result validation error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/format_critique_output")
def format_critique_output_endpoint(call: ToolCall):
    """Format critique result for output"""
    try:
        from .tools import format_critique_output

        logger.info("Formatting critique output")

        result = format_critique_output(*call.args, **call.kwargs)
        return {"formatted_output": result}

    except Exception as e:
        logger.error(f"❌ Output formatting error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/get_critic_engine")
def get_critic_engine_endpoint(call: ToolCall):
    """Get critic engine instance"""
    try:
        from .tools import get_critic_engine

        logger.info("Retrieving critic engine instance")

        engine = get_critic_engine()
        return {
            "engine_status": "available",
            "model_count": len(engine.models) if hasattr(engine, "models") else 0,
        }

    except Exception as e:
        logger.error(f"❌ Engine retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# Feedback logging endpoint
@app.post("/log_feedback")
def log_feedback_endpoint(call: ToolCall):
    """Log feedback for critique performance tracking"""
    try:
        feedback_data = {
            "timestamp": datetime.now().isoformat(),
            "agent": "critic",
            "feedback": call.kwargs.get("feedback", {}),
            "operation": call.kwargs.get("operation", "unknown"),
        }
        logger.info(f"📝 Feedback logged: {feedback_data['operation']}")
        return feedback_data

    except Exception as e:
        logger.error(f"❌ Feedback logging error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("CRITIC_HOST", "0.0.0.0")
    port = CRITIC_AGENT_PORT

    logger.info(f"Starting Critic Agent on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
