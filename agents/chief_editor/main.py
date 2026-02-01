"""
Chief Editor Agent - Main FastAPI Application

This is the main entry point for the Chief Editor agent, providing RESTful APIs
for editorial workflow orchestration, content quality assessment, and multi-agent
coordination.

Features:
- FastAPI web server with MCP bus integration
- Editorial decision making with 5-model AI workflow
- Content quality assessment and categorization
- Story brief generation and publishing coordination
- Evidence review queue management
- Health checks and monitoring

Endpoints:
- POST /assess_content_quality: Assess content quality using BERT
- POST /categorize_content: Categorize content using DistilBERT
- POST /analyze_editorial_sentiment: Analyze editorial sentiment using RoBERTa
- POST /generate_editorial_commentary: Generate commentary using T5
- POST /make_editorial_decision: Comprehensive editorial decision making
- POST /request_story_brief: Generate story briefs
- POST /publish_story: Coordinate story publishing
- POST /review_evidence: Queue evidence for human review
- GET /health: Health check endpoint
- GET /stats: Processing statistics

All endpoints include security validation, error handling, and comprehensive logging.
"""

import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from common.metrics import JustNewsMetrics
from common.observability import get_logger

# Compatibility: expose create_database_service for tests that patch agent modules
try:
    from database.utils.migrated_database_utils import (
        create_database_service,  # type: ignore
    )
except Exception:
    create_database_service = None

from .tools import (
    analyze_editorial_sentiment,
    assess_content_quality,
    categorize_content,
    format_editorial_output,
    generate_editorial_commentary,
    health_check,
    make_editorial_decision,
    publish_story,
    request_story_brief,
    review_evidence,
    validate_editorial_result,
)

# MCP Bus integration
try:
    from agents.common.mcp_bus_client import MCPBusClient

    MCP_AVAILABLE = True
except ImportError:
    # Fallback/Retry for different path structure
    try:
        from common.mcp_bus_client import MCPBusClient
        MCP_AVAILABLE = True
    except ImportError:
        MCPBusClient = None
        MCP_AVAILABLE = False

logger = get_logger(__name__)

# Environment variables
CHIEF_EDITOR_AGENT_PORT = int(os.environ.get("CHIEF_EDITOR_AGENT_PORT", 8001))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")


# Request/Response Models
class ContentAnalysisRequest(BaseModel):
    """Base request model for content analysis operations."""

    content: str = Field(
        ..., min_length=1, max_length=100000, description="Content to analyze"
    )
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")
    format_output: str = Field(
        "json", description="Output format (json, text, markdown)"
    )


class QualityAssessmentRequest(ContentAnalysisRequest):
    """Request model for quality assessment."""

    pass


class CategorizationRequest(ContentAnalysisRequest):
    """Request model for content categorization."""

    pass


class SentimentAnalysisRequest(ContentAnalysisRequest):
    """Request model for sentiment analysis."""

    pass


class CommentaryRequest(BaseModel):
    """Request model for commentary generation."""

    content: str = Field(
        ..., min_length=1, max_length=100000, description="Content for commentary"
    )
    context: str = Field(
        "news article", description="Context for commentary generation"
    )
    format_output: str = Field(
        "json", description="Output format (json, text, markdown)"
    )


class EditorialDecisionRequest(ContentAnalysisRequest):
    """Request model for comprehensive editorial decisions."""

    pass


class StoryBriefRequest(BaseModel):
    """Request model for story brief generation."""

    topic: str = Field(..., min_length=1, description="Story topic")
    scope: str = Field(..., min_length=1, description="Story scope")
    format_output: str = Field(
        "json", description="Output format (json, text, markdown)"
    )


class PublishRequest(BaseModel):
    """Request model for story publishing."""

    story_id: str = Field(..., min_length=1, description="Story ID to publish")
    format_output: str = Field(
        "json", description="Output format (json, text, markdown)"
    )


class EvidenceReviewRequest(BaseModel):
    """Request model for evidence review."""

    evidence_manifest: str = Field(
        ..., min_length=1, description="Evidence manifest path"
    )
    reason: str = Field(..., min_length=1, description="Reason for review")


class EditorialResponse(BaseModel):
    """Base response model for editorial operations."""

    success: bool = Field(..., description="Operation success status")
    result: dict[str, Any] = Field(..., description="Operation result data")
    processing_time: float = Field(..., description="Processing time in seconds")
    timestamp: float = Field(..., description="Response timestamp")
    format: str = Field(..., description="Output format used")


class HealthResponse(BaseModel):
    """Response model for health checks."""

    timestamp: float = Field(..., description="Health check timestamp")
    overall_status: str = Field(..., description="Overall health status")
    components: dict[str, Any] = Field(..., description="Component health status")
    model_status: dict[str, Any] = Field(..., description="AI model status")
    processing_stats: dict[str, Any] = Field(..., description="Processing statistics")
    issues: list[str] | None = Field(None, description="List of issues found")


class StatsResponse(BaseModel):
    """Response model for statistics."""

    total_processed: int = Field(..., description="Total analyses processed")
    quality_assessments: int = Field(..., description="Total quality assessments")
    categorizations: int = Field(..., description="Total content categorizations")
    sentiment_analyses: int = Field(..., description="Total sentiment analyses")
    editorial_decisions: int = Field(..., description="Total editorial decisions")
    story_briefs: int = Field(..., description="Total story briefs generated")
    stories_published: int = Field(..., description="Total stories published")
    average_processing_time: float = Field(..., description="Average processing time")
    uptime: float = Field(..., description="Service uptime in seconds")


# Global startup time
startup_time = time.time()


# Lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    logger.info("🎯 Starting Chief Editor Agent - Editorial Workflow Orchestrator")
    logger.info(
        "📋 Focus: Content quality assessment, editorial decision making, workflow coordination"
    )
    logger.info(
        "🤝 Integration: Coordinates Journalist, Analyst, Fact Checker, Synthesizer, and Critic agents"
    )
    logger.info(
        "🎨 Specializes: Unified AI workflow (Qwen + SentenceTransformers)"
    )

    try:
        # Register with MCP Bus if available
        if MCP_AVAILABLE:
            await register_with_mcp_bus()

        logger.info("✅ Chief Editor Agent started successfully")

        yield

    except Exception as e:
        logger.error(f"❌ Failed to start Chief Editor Agent: {e}")
        raise
    finally:
        logger.info("🛑 Chief Editor Agent shutdown completed")


async def register_with_mcp_bus():
    """Register agent with MCP Bus."""
    if not MCP_AVAILABLE:
        logger.warning("MCP Bus client not available - skipping registration")
        return

    try:
        mcp_bus_url = MCP_BUS_URL
        client = MCPBusClient(mcp_bus_url)

        # Map capabilities/endpoints to tools list
        tools = [
            "assess_content_quality",
            "categorize_content",
            "analyze_editorial_sentiment",
            "generate_editorial_commentary",
            "make_editorial_decision",
            "request_story_brief",
            "publish_story",
            "review_evidence"
        ]

        # register_agent is synchronous
        client.register_agent(
            agent_name="chief_editor",
            agent_address=f"http://localhost:{CHIEF_EDITOR_AGENT_PORT}",
            tools=tools
        )
        logger.info("✅ Registered with MCP Bus")

    except Exception as e:
        logger.error(f"❌ MCP Bus registration failed: {e}")


# Create FastAPI app
app = FastAPI(
    title="Chief Editor Agent",
    description="Editorial workflow orchestrator for news content processing",
    version="2.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize metrics
try:
    metrics = JustNewsMetrics("chief_editor")
    # Metrics middleware
    app.middleware("http")(metrics.request_middleware)
except Exception as e:
    logger.warning(f"Metrics initialization failed: {e}")
    metrics = None


@app.get("/")
async def root():
    """Root endpoint with basic information."""
    return {
        "name": "Chief Editor Agent",
        "version": "2.0.0",
        "description": "Editorial workflow orchestrator for news content",
        "status": "running",
        "capabilities": [
            "content_quality_assessment",
            "editorial_decision_making",
            "story_brief_generation",
            "publishing_coordination",
            "evidence_review_management",
        ],
    }


@app.post("/assess_content_quality", response_model=EditorialResponse)
async def assess_content_quality_endpoint(request: QualityAssessmentRequest):
    """
    Assess content quality using BERT-based analysis.

    This endpoint evaluates the overall quality of news content using
    advanced NLP models to determine publication readiness and editorial needs.
    """
    start_time = time.time()

    try:
        logger.info(
            f"🎯 Processing content quality assessment: {len(request.content)} characters"
        )

        # Perform analysis
        result = assess_content_quality(request.content, request.metadata)

        # Validate result
        if not validate_editorial_result(result):
            raise HTTPException(status_code=500, detail="Invalid analysis result")

        # Format output if requested
        if request.format_output != "json":
            formatted_result = format_editorial_output(result, request.format_output)
            result = {"formatted_output": formatted_result}

        processing_time = time.time() - start_time

        response = EditorialResponse(
            success=True,
            result=result,
            processing_time=processing_time,
            timestamp=time.time(),
            format=request.format_output,
        )

        logger.info(
            "✅ Content quality assessment completed in %.2f seconds",
            processing_time,
        )
        return response

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Content quality assessment failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Content quality assessment failed: {str(e)}"
        ) from e


@app.post("/categorize_content", response_model=EditorialResponse)
async def categorize_content_endpoint(request: CategorizationRequest):
    """
    Categorize content using DistilBERT-based classification.

    This endpoint automatically categorizes news content into appropriate
    editorial categories for workflow routing and prioritization.
    """
    start_time = time.time()

    try:
        logger.info(
            f"📂 Processing content categorization: {len(request.content)} characters"
        )

        # Perform analysis
        result = categorize_content(request.content, request.metadata)

        # Validate result
        if not validate_editorial_result(result):
            raise HTTPException(status_code=500, detail="Invalid analysis result")

        # Format output if requested
        if request.format_output != "json":
            formatted_result = format_editorial_output(result, request.format_output)
            result = {"formatted_output": formatted_result}

        processing_time = time.time() - start_time

        response = EditorialResponse(
            success=True,
            result=result,
            processing_time=processing_time,
            timestamp=time.time(),
            format=request.format_output,
        )

        logger.info(
            "✅ Content categorization completed in %.2f seconds",
            processing_time,
        )
        return response

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Content categorization failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Content categorization failed: {str(e)}"
        ) from e


@app.post("/analyze_editorial_sentiment", response_model=EditorialResponse)
async def analyze_editorial_sentiment_endpoint(request: SentimentAnalysisRequest):
    """
    Analyze editorial sentiment using RoBERTa-based analysis.

    This endpoint determines the editorial tone and sentiment of content
    to inform publication decisions and editorial positioning.
    """
    start_time = time.time()

    try:
        logger.info(
            f"📊 Processing editorial sentiment analysis: {len(request.content)} characters"
        )

        # Perform analysis
        result = analyze_editorial_sentiment(request.content, request.metadata)

        # Validate result
        if not validate_editorial_result(result):
            raise HTTPException(status_code=500, detail="Invalid analysis result")

        # Format output if requested
        if request.format_output != "json":
            formatted_result = format_editorial_output(result, request.format_output)
            result = {"formatted_output": formatted_result}

        processing_time = time.time() - start_time

        response = EditorialResponse(
            success=True,
            result=result,
            processing_time=processing_time,
            timestamp=time.time(),
            format=request.format_output,
        )

        logger.info(
            "✅ Editorial sentiment analysis completed in %.2f seconds",
            processing_time,
        )
        return response

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Editorial sentiment analysis failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Editorial sentiment analysis failed: {str(e)}"
        ) from e


@app.post("/generate_editorial_commentary", response_model=EditorialResponse)
async def generate_editorial_commentary_endpoint(request: CommentaryRequest):
    """
    Generate editorial commentary using T5-based generation.

    This endpoint creates editorial notes and commentary for content
    to guide the editorial workflow and decision making process.
    """
    start_time = time.time()

    try:
        logger.info(
            f"💬 Processing editorial commentary generation: {len(request.content)} characters"
        )

        # Perform analysis
        result = generate_editorial_commentary(request.content, request.context)

        # Validate result
        if not validate_editorial_result(result):
            raise HTTPException(status_code=500, detail="Invalid analysis result")

        # Format output if requested
        if request.format_output != "json":
            formatted_result = format_editorial_output(result, request.format_output)
            result = {"formatted_output": formatted_result}

        processing_time = time.time() - start_time

        response = EditorialResponse(
            success=True,
            result=result,
            processing_time=processing_time,
            timestamp=time.time(),
            format=request.format_output,
        )

        logger.info(
            "✅ Editorial commentary generation completed in %.2f seconds",
            processing_time,
        )
        return response

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Editorial commentary generation failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Editorial commentary generation failed: {str(e)}"
        ) from e


@app.post("/make_editorial_decision", response_model=EditorialResponse)
async def make_editorial_decision_endpoint(request: EditorialDecisionRequest):
    """
    Make comprehensive editorial decision using all 5 AI models.

    This endpoint provides a complete editorial assessment including
    quality, categorization, sentiment, and workflow recommendations.
    """
    start_time = time.time()

    try:
        logger.info(
            f"🏛️ Processing comprehensive editorial decision: {len(request.content)} characters"
        )

        # Perform analysis
        result = make_editorial_decision(request.content, request.metadata)

        # Validate result
        if not validate_editorial_result(result):
            raise HTTPException(status_code=500, detail="Invalid analysis result")

        # Format output if requested
        if request.format_output != "json":
            formatted_result = format_editorial_output(result, request.format_output)
            result = {"formatted_output": formatted_result}

        processing_time = time.time() - start_time

        response = EditorialResponse(
            success=True,
            result=result,
            processing_time=processing_time,
            timestamp=time.time(),
            format=request.format_output,
        )

        logger.info(
            "✅ Editorial decision completed in %.2f seconds",
            processing_time,
        )
        return response

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Editorial decision making failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Editorial decision making failed: {str(e)}"
        ) from e


@app.post("/request_story_brief", response_model=EditorialResponse)
async def request_story_brief_endpoint(request: StoryBriefRequest):
    """
    Generate a story brief for editorial planning.

    This endpoint creates structured story briefs to guide content development
    and editorial planning across the newsroom.
    """
    start_time = time.time()

    try:
        logger.info(f"📝 Processing story brief request: {request.topic}")

        # Perform analysis
        result = request_story_brief(request.topic, request.scope)

        # Validate result
        if not validate_editorial_result(result):
            raise HTTPException(status_code=500, detail="Invalid brief result")

        # Format output if requested
        if request.format_output != "json":
            formatted_result = format_editorial_output(result, request.format_output)
            result = {"formatted_output": formatted_result}

        processing_time = time.time() - start_time

        response = EditorialResponse(
            success=True,
            result=result,
            processing_time=processing_time,
            timestamp=time.time(),
            format=request.format_output,
        )

        logger.info(
            "✅ Story brief generated in %.2f seconds",
            processing_time,
        )
        return response

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Story brief generation failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Story brief generation failed: {str(e)}"
        ) from e


@app.post("/publish_story", response_model=EditorialResponse)
async def publish_story_endpoint(request: dict):
    """
    Coordinate story publishing across the editorial workflow.

    This endpoint manages the publishing process, coordinating with
    other agents and updating editorial timelines.
    """
    start_time = time.time()

    try:
        # Handle MCP Bus format vs Direct Pydantic model
        story_id = None
        format_output = "json"
        
        if "args" in request and "kwargs" in request:
             # MCP Bus format
             kwargs = request.get("kwargs", {})
             if "story_id" in kwargs:
                 story_id = kwargs["story_id"]
             elif request["args"]:
                 story_id = request["args"][0]
                 
             format_output = kwargs.get("format_output", "json")
        else:
             # Direct/Pydantic dict
             story_id = request.get("story_id")
             format_output = request.get("format_output", "json")
             
        if not story_id:
             logger.error("Missing story_id in publishing request")
             raise HTTPException(status_code=400, detail="Missing story_id")

        logger.info(f"🚀 Processing story publishing: {story_id}")

        # Perform analysis
        result = publish_story(story_id)

        # Validate result
        if not validate_editorial_result(result):
            raise HTTPException(status_code=500, detail="Invalid publishing result")

        # Format output if requested
        if format_output != "json":
            formatted_result = format_editorial_output(result, format_output)
            result = {"formatted_output": formatted_result}

        processing_time = time.time() - start_time

        response = EditorialResponse(
            success=True,
            result=result,
            processing_time=processing_time,
            timestamp=time.time(),
            format=format_output,
        )

        logger.info(
            "✅ Story publishing pipeline completed in %.2f seconds",
            processing_time,
        )
        return response

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Story publishing failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Story publishing failed: {str(e)}"
        ) from e


@app.get("/api/v1/articles/drafts")
def list_drafts():
    """List drafts of synthesized articles for Chief Editor review.

    Returns both Option A (articles.is_synthesized) and Option B (synthesized_articles)
    depending on the persistence used.
    """
    try:
        from database.utils.migrated_database_utils import create_database_service

        db_service = create_database_service()
        cursor = db_service.mb_conn.cursor(dictionary=True)

        # Check which table is in use by system config
        from config.core import get_config

        cfg = get_config()
        storage = cfg.system.get("persistence", {}).get(
            "synthesized_article_storage", "extend"
        )

        if storage == "extend":
            cursor.execute(
                "SELECT id, title, summary, is_published, created_at FROM articles WHERE is_synthesized = 1 ORDER BY created_at DESC LIMIT 100"
            )
            rows = cursor.fetchall()
            for r in rows:
                # Normalize datatypes
                r["created_at"] = str(r.get("created_at"))
            cursor.close()
            return {"drafts": rows}
        else:
            cursor.execute(
                "SELECT id, story_id, title, summary, is_published, created_at FROM synthesized_articles ORDER BY created_at DESC LIMIT 100"
            )
            rows = cursor.fetchall()
            for r in rows:
                r["created_at"] = str(r.get("created_at"))
            cursor.close()
            return {"drafts": rows}
    except Exception as e:
        logger.exception("Failed to list drafts")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/review_evidence", response_model=EditorialResponse)
async def review_evidence_endpoint(request: EvidenceReviewRequest):
    """
    Queue evidence for human review and editorial oversight.

    This endpoint manages the evidence review queue, notifying editors
    and maintaining audit trails for editorial decisions.
    """
    start_time = time.time()

    try:
        logger.info(
            f"🔍 Processing evidence review request: {request.evidence_manifest}"
        )

        # Perform analysis
        result = review_evidence(request.evidence_manifest, request.reason)

        processing_time = time.time() - start_time

        response = EditorialResponse(
            success=True,
            result=result,
            processing_time=processing_time,
            timestamp=time.time(),
            format="json",
        )

        logger.info(
            "✅ Evidence review queued in %.2f seconds",
            processing_time,
        )
        return response

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Evidence review queuing failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Evidence review queuing failed: {str(e)}"
        ) from e


@app.get("/health", response_model=HealthResponse)
async def health_endpoint():
    """Health check endpoint for monitoring and load balancers."""
    try:
        health_result = await health_check()
        return HealthResponse(**health_result)
    except Exception as e:
        logger.error(f"❌ Health check error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Health check failed: {str(e)}"
        ) from e


@app.get("/stats", response_model=StatsResponse)
async def stats_endpoint():
    """Get processing statistics and performance metrics."""
    try:
        from .tools import get_chief_editor_engine

        engine = get_chief_editor_engine()

        uptime = time.time() - startup_time

        stats = StatsResponse(
            total_processed=engine.processing_stats["total_processed"],
            quality_assessments=engine.processing_stats["quality_assessments"],
            categorizations=engine.processing_stats["categorizations"],
            sentiment_analyses=engine.processing_stats["sentiment_analyses"],
            editorial_decisions=engine.processing_stats["editorial_decisions"],
            story_briefs=engine.processing_stats["story_briefs"],
            stories_published=engine.processing_stats["stories_published"],
            average_processing_time=engine.processing_stats["average_processing_time"],
            uptime=uptime,
        )

        return stats

    except Exception as e:
        logger.error(f"❌ Stats retrieval error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Stats retrieval failed: {str(e)}"
        ) from e


@app.get("/capabilities")
async def capabilities_endpoint():
    """Get agent capabilities and supported features."""
    return {
        "name": "Chief Editor Agent",
        "version": "2.0.0",
        "capabilities": [
            "content_quality_assessment",
            "content_categorization",
            "editorial_sentiment_analysis",
            "editorial_commentary_generation",
            "comprehensive_editorial_decisions",
            "story_brief_generation",
            "publishing_coordination",
            "evidence_review_management",
        ],
        "supported_formats": ["json", "text", "markdown"],
        "ai_models": {
            "quality_assessment": "BERT (bert-base-uncased)",
            "categorization": "DistilBERT (distilbert-base-uncased)",
            "sentiment_analysis": "RoBERTa (cardiffnlp/twitter-roberta-base-sentiment-latest)",
            "commentary_generation": "T5 (t5-small)",
            "workflow_embeddings": "SentenceTransformers (all-MiniLM-L6-v2)",
        },
        "workflow_stages": [
            "intake",
            "analysis",
            "fact_check",
            "synthesis",
            "review",
            "publish",
            "archive",
        ],
        "editorial_priorities": ["urgent", "high", "medium", "low", "review"],
    }


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    if not metrics:
        return Response(
            status_code=503,
            content="# metrics unavailable\n",
            media_type="text/plain; charset=utf-8",
        )
    return Response(
        content=metrics.get_metrics(), media_type="text/plain; charset=utf-8"
    )


# Error handlers
@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle internal server errors."""
    logger.error(f"500 Internal Server Error: {exc}")
    payload = {
        "error": "Internal server error",
        "detail": str(exc)
        if os.getenv("DEBUG", "").lower() == "true"
        else "An unexpected error occurred",
    }
    return JSONResponse(status_code=500, content=payload)


@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 not found errors."""
    payload = {"error": "Not found", "detail": f"Endpoint {request.url.path} not found"}
    return JSONResponse(status_code=404, content=payload)


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("CHIEF_EDITOR_HOST", "0.0.0.0")
    port = int(os.environ.get("CHIEF_EDITOR_PORT", "8001"))
    reload_flag = (
        os.environ.get(
            "UVICORN_RELOAD", os.environ.get("CHIEF_EDITOR_RELOAD", "false")
        ).lower()
        == "true"
    )
    log_level = os.environ.get(
        "UVICORN_LOG_LEVEL", os.environ.get("CHIEF_EDITOR_LOG_LEVEL", "info")
    )

    target = f"{__package__}.main:app" if __package__ else "main:app"

    logger.info(
        "Starting Chief Editor Service on %s:%s (reload=%s)",
        host,
        port,
        reload_flag,
    )

    uvicorn.run(
        target,
        host=host,
        port=port,
        reload=reload_flag,
        log_level=log_level,
    )
