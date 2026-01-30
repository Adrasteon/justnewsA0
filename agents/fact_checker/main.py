"""
Fact Checker Agent - Refactored Main Application

This module provides the main FastAPI application for the fact checker agent,
implementing comprehensive fact verification and source credibility assessment.

Key Features:
- MCP Bus integration for inter-agent communication
- Comprehensive fact-checking endpoints
- GPU-accelerated processing with CPU fallbacks
- Robust error handling and validation
- Performance monitoring and metrics
- Health checks and service discovery

Endpoints:
- /verify_facts: Primary fact verification endpoint
- /validate_sources: Source credibility assessment
- /validate_is_news_gpu: GPU-accelerated news validation
- /verify_claims_gpu: GPU-accelerated claim verification
- /comprehensive_fact_check: Full article fact-checking
- /health: Health check endpoint
- /ready: Readiness check endpoint
- /metrics: Prometheus metrics endpoint

All endpoints support both MCP Bus format and direct API calls.
"""

import asyncio
import inspect
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

bootstrap_observability("fact_checker")
logger = get_logger(__name__)

# Compatibility: expose create_database_service for tests that patch agent modules
try:
    from database.utils.migrated_database_utils import (
        create_database_service,
        get_db_config,
    )
    # Initialize DB Service without ChromaDB to prevent segfaults
    # Fact Checker only needs MariaDB to update validation status
    try:
        db_config = get_db_config()
        if 'database' in db_config and 'chromadb' in db_config['database']:
            logger.info("Disabling ChromaDB for Fact Checker to prevent initialization issues")
            del db_config['database']['chromadb']
        create_database_service(db_config)
    except Exception as e:
        logger.warning(f"Failed to pre-initialize database service: {e}")

except Exception:
    create_database_service = None
    get_db_config = None

# Configure logging
logger = get_logger(__name__)

ready = False

# Environment variables
FACT_CHECKER_AGENT_PORT = int(os.environ.get("FACT_CHECKER_AGENT_PORT", 8003))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")


# Define the lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    logger.info("Fact Checker agent is starting up.")
    mcp_bus_client = MCPBusClient(base_url=MCP_BUS_URL)
    agent_address = f"http://localhost:{FACT_CHECKER_AGENT_PORT}"
    try:
        mcp_bus_client.register_agent(
            agent_name="fact_checker",
            agent_address=agent_address,
            tools=[
                "verify_facts",
                "validate_sources",
                "validate_is_news_gpu",
                "verify_claims_gpu",
                "comprehensive_fact_check",
                "extract_claims",
                "assess_credibility",
                "verify_article",
            ],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")
    global ready
    ready = True
    yield
    logger.info("Fact Checker agent is shutting down.")


# Initialize FastAPI with the lifespan context manager
app = FastAPI(
    title="Fact Checker Agent",
    description="AI-powered fact verification and source credibility assessment",
    version="2.0.0",
    lifespan=lifespan,
)

# Initialize metrics lazily to allow tests to patch constructor
_metrics_client: JustNewsMetrics | None = None
_metrics_factory: Any = JustNewsMetrics


def get_metrics_client() -> JustNewsMetrics:
    global _metrics_client, _metrics_factory
    current_factory = JustNewsMetrics
    if _metrics_client is None or _metrics_factory is not current_factory:
        _metrics_factory = current_factory
        _metrics_client = current_factory("fact_checker")
    return _metrics_client


# Lightweight helpers patched in tests
def validate_content_size(content: str | None, max_bytes: int = 1_000_000) -> bool:
    """Return True when content is within the configured size budget."""
    if content is None:
        return True
    try:
        return len(content.encode("utf-8")) <= max_bytes
    except Exception:
        return False


def sanitize_content(content: str | None) -> str:
    """Trim whitespace and coerce non-string payloads into safe defaults."""
    if content is None:
        return ""
    return content.strip() if isinstance(content, str) else str(content)


def verify_facts(
    content: str, source_url: str | None = None, context: str | None = None
) -> dict[str, Any]:
    from .tools import verify_facts as run_verify_facts

    return run_verify_facts(content, source_url, context)


def extract_claims(content: str) -> list[str]:
    from .tools import extract_claims as run_extract_claims

    return run_extract_claims(content)


def run_validate_sources(
    content: str,
    sources: list[str] | None = None,
    domain: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    from .tools import validate_sources as validate_tool

    return validate_tool(content, sources, domain, source_url)


def run_comprehensive_fact_check(
    content: str,
    source_url: str | None = None,
    context: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from .tools import comprehensive_fact_check as comprehensive_tool

    return comprehensive_tool(content, source_url, context, metadata)


def run_assess_credibility(
    content: str | None = None,
    domain: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    from .tools import assess_credibility as assess_tool

    return assess_tool(content, domain, source_url)


def run_detect_contradictions(text_passages: list[str]) -> dict[str, Any]:
    from .tools import detect_contradictions as detect_tool

    return detect_tool(text_passages)


# Register shutdown endpoint if available
try:
    from agents.common.shutdown import register_shutdown_endpoint

    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for fact_checker")

# Register reload endpoint if available
try:
    from agents.common.reload import register_reload_endpoint

    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for fact_checker")


@app.middleware("http")
async def metrics_middleware(request, call_next):
    """Proxy to the metrics middleware, instantiating on first use."""
    middleware = get_metrics_client().request_middleware
    if not inspect.iscoroutinefunction(middleware):
        return await call_next(request)

    response = middleware(request, call_next)
    if inspect.isawaitable(response):
        return await response
    return response


# Pydantic models for request/response validation
class ToolCall(BaseModel):
    """Standard MCP tool call format."""

    args: list[Any]
    kwargs: dict[str, Any]


class FactCheckRequest(BaseModel):
    """Request model for fact checking operations."""

    content: str
    source_url: str | None = None
    context: str | None = None
    metadata: dict[str, Any] | None = None


class VerificationResult(BaseModel):
    """Response model for verification results."""

    verification_score: float
    classification: str
    confidence: float
    details: dict[str, Any]
    processing_time: float
    timestamp: str


@app.get("/health")
def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "fact_checker",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/ready")
def ready_endpoint():
    """Readiness check endpoint."""
    return {"ready": ready}


@app.get("/metrics")
def get_metrics():
    """Prometheus metrics endpoint."""
    from fastapi.responses import Response

    payload = get_metrics_client().get_metrics()
    if isinstance(payload, bytes):
        content = payload
    else:
        content = str(payload)
    return Response(content, media_type="text/plain")


@app.post("/verify")
def verify_endpoint(request: FactCheckRequest) -> dict[str, Any]:
    """Lightweight verification endpoint used by synchronous callers."""
    if not validate_content_size(request.content):
        raise HTTPException(status_code=400, detail="Content too large")

    cleaned_content = sanitize_content(request.content)
    result = verify_facts(cleaned_content, request.source_url, request.context)
    return result


@app.post("/extract-claims")
def extract_claims_endpoint(request: FactCheckRequest) -> list[str]:
    """Convenience wrapper that returns extracted claims without MCP payload."""
    if not validate_content_size(request.content):
        raise HTTPException(status_code=400, detail="Content too large")

    cleaned_content = sanitize_content(request.content)
    result = extract_claims(cleaned_content)
    if isinstance(result, dict):
        return result.get("claims", [])
    return result


@app.post("/verify_facts")
async def verify_facts_tool(call: ToolCall) -> dict[str, Any]:
    """
    Primary fact verification endpoint.

    Verifies factual claims using AI models and evidence assessment.
    """
    try:
        from .tools import verify_facts as run_verify_facts

        logger.info(
            f"Calling verify_facts tool with args: {call.args} and kwargs: {call.kwargs}"
        )

        # Extract parameters
        content = call.kwargs.get("content") or (call.args[0] if call.args else "")
        source_url = call.kwargs.get("source_url", "")
        context = call.kwargs.get("context", "")

        if not content:
            raise HTTPException(status_code=400, detail="Content parameter is required")

        result = run_verify_facts(content, source_url, context)
        import asyncio
        if asyncio.iscoroutine(result) or asyncio.is_future(result):
             result = await result

        logger.info(
            f"Fact verification completed with score: {result.get('verification_score', 0.0)}"
        )
        return result

    except Exception as e:
        logger.error(f"An error occurred in verify_facts: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/verify_article")
async def verify_article_endpoint(call: ToolCall) -> dict[str, Any]:
    """
    MCP-compatible tool endpoint for verifying an article by ID.
    Expects 'article_id' in kwargs.
    """
    try:
        from .tools import verify_article_tool
        
        logger.info(f"Calling verify_article tool with kwargs: {call.kwargs}")
        
        article_id = call.kwargs.get("article_id")
        if article_id is None:
             raise HTTPException(status_code=400, detail="article_id is required")
        
        return await verify_article_tool(int(article_id))
    except Exception as e:
        logger.error(f"An error occurred in verify_article: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/validate_sources")
async def validate_sources(call: ToolCall) -> dict[str, Any]:
    """
    Source credibility assessment endpoint.

    Evaluates the reliability and credibility of information sources.
    """
    try:
        logger.info(
            f"Calling validate_sources with args: {call.args} and kwargs: {call.kwargs}"
        )

        # Extract parameters
        content = call.kwargs.get("content") or (call.args[0] if call.args else "")
        source_url = call.kwargs.get("source_url", "")
        domain = call.kwargs.get("domain", "")
        sources = call.kwargs.get("sources") or (
            call.args[1] if len(call.args) > 1 else None
        )

        if not content and not source_url:
            raise HTTPException(
                status_code=400,
                detail="Either content or source_url parameter is required",
            )

        result = await asyncio.to_thread(
            run_validate_sources,
            content,
            sources,
            domain or None,
            source_url or None,
        )

        logger.info(
            f"Source validation completed with credibility score: {result.get('credibility_score', 0.0)}"
        )
        return result

    except Exception as e:
        logger.error(f"An error occurred in validate_sources: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/validate_is_news_gpu")
async def validate_is_news_gpu(call: ToolCall) -> dict[str, Any]:
    """
    GPU-accelerated news content validation endpoint.

    Determines if provided content qualifies as legitimate news reporting.
    """
    try:
        from .tools import validate_is_news_gpu

        logger.info(
            f"Calling GPU validate_is_news with args: {call.args} and kwargs: {call.kwargs}"
        )

        # Extract parameters
        content = call.kwargs.get("content") or (call.args[0] if call.args else "")

        if not content:
            raise HTTPException(status_code=400, detail="Content parameter is required")

        result = await validate_is_news_gpu(content)

        logger.info(f"GPU news validation completed: {result.get('is_news', False)}")
        return result

    except Exception as e:
        logger.error(f"An error occurred in GPU validate_is_news: {e}")
        # Fallback to CPU implementation
        try:
            from .tools import validate_is_news_cpu

            content = call.kwargs.get("content") or (call.args[0] if call.args else "")
            result = await validate_is_news_cpu(content)
            logger.info("Fallback to CPU news validation successful")
            return result
        except Exception as fallback_error:
            logger.error(f"Fallback CPU validation also failed: {fallback_error}")
            raise HTTPException(
                status_code=500, detail=f"GPU and CPU validation failed: {str(e)}"
            ) from fallback_error


@app.post("/verify_claims_gpu")
async def verify_claims_gpu(call: ToolCall) -> dict[str, Any]:
    """
    GPU-accelerated claim verification endpoint.

    Verifies multiple claims against available evidence and sources.
    """
    try:
        from .tools import verify_claims_gpu

        logger.info(
            f"Calling GPU verify_claims with args: {call.args} and kwargs: {call.kwargs}"
        )

        # Extract parameters
        claims = call.kwargs.get("claims") or (call.args[0] if call.args else [])
        sources = call.kwargs.get("sources") or (
            call.args[1] if len(call.args) > 1 else []
        )

        if not claims:
            raise HTTPException(status_code=400, detail="Claims parameter is required")

        result = await verify_claims_gpu(claims, sources)

        logger.info(f"GPU claims verification completed for {len(claims)} claims")
        return result

    except Exception as e:
        logger.error(f"An error occurred in GPU verify_claims: {e}")
        # Fallback to CPU implementation
        try:
            from .tools import verify_claims_cpu

            claims = call.kwargs.get("claims") or (call.args[0] if call.args else [])
            sources = call.kwargs.get("sources") or (
                call.args[1] if len(call.args) > 1 else []
            )
            result = await verify_claims_cpu(claims, sources)
            logger.info("Fallback to CPU claims verification successful")
            return result
        except Exception as fallback_error:
            logger.error(f"Fallback CPU verification also failed: {fallback_error}")
            raise HTTPException(
                status_code=500, detail=f"GPU and CPU verification failed: {str(e)}"
            ) from fallback_error


@app.post("/comprehensive_fact_check")
async def comprehensive_fact_check_endpoint(
    request: FactCheckRequest,
) -> dict[str, Any]:
    """
    Comprehensive fact-checking endpoint for full articles.

    Performs complete fact verification analysis including claim extraction,
    evidence assessment, and source credibility evaluation.
    """
    try:
        logger.info(
            f"Starting comprehensive fact check for content length: {len(request.content)}"
        )

        result = await asyncio.to_thread(
            run_comprehensive_fact_check,
            request.content,
            request.source_url,
            request.context,
            request.metadata,
        )

        logger.info(
            f"Comprehensive fact check completed with overall score: {result.get('overall_score', 0.0)}"
        )
        return result

    except Exception as e:
        logger.error(f"An error occurred in comprehensive_fact_check: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/extract_claims")
async def extract_claims_tool(call: ToolCall) -> dict[str, Any]:
    """
    Claim extraction endpoint.

    Extracts verifiable claims from text content using NLP techniques.
    """
    try:
        logger.info(
            f"Calling extract_claims with args: {call.args} and kwargs: {call.kwargs}"
        )

        # Extract parameters
        content = call.kwargs.get("content") or (call.args[0] if call.args else "")

        if not content:
            raise HTTPException(status_code=400, detail="Content parameter is required")

        claims = await asyncio.to_thread(extract_claims, content)
        claim_list = claims if isinstance(claims, list) else []

        logger.info(f"Claim extraction completed: {len(claim_list)} claims found")
        return {
            "claims": claim_list,
            "claim_count": len(claim_list),
        }

    except Exception as e:
        logger.error(f"An error occurred in extract_claims: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/assess_credibility")
async def assess_credibility(call: ToolCall) -> dict[str, Any]:
    """
    Source credibility assessment endpoint.

    Evaluates the credibility and reliability of information sources.
    """
    try:
        logger.info(
            f"Calling assess_credibility with args: {call.args} and kwargs: {call.kwargs}"
        )

        # Extract parameters
        content = call.kwargs.get("content") or (call.args[0] if call.args else "")
        domain = call.kwargs.get("domain", "")
        source_url = call.kwargs.get("source_url", "")

        if not content and not domain and not source_url:
            raise HTTPException(
                status_code=400,
                detail="At least one of content, domain, or source_url is required",
            )

        result = await asyncio.to_thread(
            run_assess_credibility,
            content or None,
            domain or None,
            source_url or None,
        )

        logger.info(
            f"Credibility assessment completed with score: {result.get('credibility_score', 0.0)}"
        )
        return result

    except Exception as e:
        logger.error(f"An error occurred in assess_credibility: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/detect_contradictions")
async def detect_contradictions(call: ToolCall) -> dict[str, Any]:
    """
    Contradiction detection endpoint.

    Identifies logical contradictions and inconsistencies in text passages.
    """
    try:
        logger.info(
            f"Calling detect_contradictions with args: {call.args} and kwargs: {call.kwargs}"
        )

        # Extract parameters
        text_passages = call.kwargs.get("text_passages") or (
            call.args[0] if call.args else []
        )

        if not text_passages or len(text_passages) < 2:
            raise HTTPException(
                status_code=400,
                detail="At least 2 text passages are required for contradiction detection",
            )

        result = await asyncio.to_thread(run_detect_contradictions, text_passages)

        logger.info(
            f"Contradiction detection completed: {result.get('contradictions_found', 0)} contradictions found"
        )
        return result

    except Exception as e:
        logger.error(f"An error occurred in detect_contradictions: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/performance/stats")
def get_performance_stats():
    """Get GPU acceleration performance statistics."""
    try:
        from .tools import get_performance_stats

        return get_performance_stats()
    except Exception as e:
        logger.error(f"Error getting performance stats: {e}")
        return {"error": str(e), "gpu_available": False}


@app.get("/model/status")
def get_model_status():
    """Get status of all fact-checking models."""
    try:
        from .tools import get_model_status

        return get_model_status()
    except Exception as e:
        logger.error(f"Error getting model status: {e}")
        return {"error": str(e), "models_loaded": False}


@app.post("/log_feedback")
def log_feedback(call: ToolCall) -> dict[str, Any]:
    """Log user feedback for model improvement."""
    try:
        from .tools import log_feedback

        feedback_data = {
            "timestamp": datetime.now().isoformat(),
            "operation": call.kwargs.get("operation", "unknown"),
            "feedback": call.kwargs.get("feedback"),
            "rating": call.kwargs.get("rating"),
            "comments": call.kwargs.get("comments"),
        }

        result = log_feedback(feedback_data)

        logger.info(f"Feedback logged: {feedback_data.get('operation', 'unknown')}")
        return result

    except Exception as e:
        logger.error(f"An error occurred while logging feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/correct_verification")
def correct_verification(call: ToolCall) -> dict[str, Any]:
    """Submit user correction for fact verification."""
    try:
        from .tools import correct_verification

        correction_data = {
            "claim": call.kwargs.get("claim"),
            "context": call.kwargs.get("context"),
            "incorrect_classification": call.kwargs.get("incorrect_classification"),
            "correct_classification": call.kwargs.get("correct_classification"),
            "priority": call.kwargs.get("priority", 2),
        }

        result = correct_verification(**correction_data)

        logger.info(
            f"Verification correction submitted: {correction_data.get('claim', '')[:50]}..."
        )
        return result

    except Exception as e:
        logger.error(f"An error occurred while submitting verification correction: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/correct_credibility")
def correct_credibility(call: ToolCall) -> dict[str, Any]:
    """Submit user correction for credibility assessment."""
    try:
        from .tools import correct_credibility

        correction_data = {
            "source_text": call.kwargs.get("source_text"),
            "domain": call.kwargs.get("domain"),
            "incorrect_reliability": call.kwargs.get("incorrect_reliability"),
            "correct_reliability": call.kwargs.get("correct_reliability"),
            "priority": call.kwargs.get("priority", 2),
        }

        result = correct_credibility(**correction_data)

        logger.info(
            f"Credibility correction submitted for domain: {correction_data.get('domain', 'unknown')}"
        )
        return result

    except Exception as e:
        logger.error(f"An error occurred while submitting credibility correction: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/training/status")
def get_training_status():
    """Get online training status for fact checker models."""
    try:
        from .tools import get_training_status

        return get_training_status()
    except Exception as e:
        logger.error(f"Error getting training status: {e}")
        return {"error": str(e), "online_training_enabled": False}


@app.post("/force_update")
def force_model_update() -> dict[str, Any]:
    """Force immediate model update (admin function)."""
    try:
        from .tools import force_model_update

        result = force_model_update()
        logger.info(f"Model update triggered: {result.get('update_triggered', False)}")
        return result
    except Exception as e:
        logger.error(f"An error occurred while forcing model update: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# Legacy endpoint compatibility
@app.post("/validate_is_news")
def validate_is_news_legacy(call: ToolCall) -> dict[str, Any]:
    """Legacy endpoint for backward compatibility."""
    return validate_is_news_gpu(call)


@app.post("/verify_claims")
def verify_claims_legacy(call: ToolCall) -> dict[str, Any]:
    """Legacy endpoint for backward compatibility."""
    return verify_claims_gpu(call)


@app.post("/validate_claims")
def validate_claims_legacy(request: dict) -> dict[str, Any]:
    """Legacy endpoint for backward compatibility."""
    try:
        # Handle MCP Bus format
        if not (
            ("args" in request and len(request["args"]) > 0)
            or ("kwargs" in request and "content" in request["kwargs"])
        ):
            raise ValueError("Missing 'content' in request")
        else:
            raise ValueError("Missing 'content' in request")

        # Perform basic validation
        validation_score = 0.75  # Placeholder score
        return {"validation_score": validation_score, "legacy_endpoint": True}
    except ValueError as ve:
        logger.warning(f"Validation error in legacy validate_claims: {ve}")
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as e:
        logger.error(f"An error occurred in legacy validate_claims: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("FACT_CHECKER_HOST", "0.0.0.0")
    port = int(os.environ.get("FACT_CHECKER_PORT", 8003))

    logger.info(f"Starting Fact Checker Agent on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
