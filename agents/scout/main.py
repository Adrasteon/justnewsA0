"""
Scout Agent - Main FastAPI Application [DEPRECATED]

DEPRECATION WARNING:
The Scout Agent is deprecated and will be removed in a future release.
Functionality has been migrated to:
- Retrieval & Analysis -> agents/fact_checker/investigator.py
- General Crawling -> agents/crawler/crawler_engine.py

This is the main entry point for the Scout agent, providing RESTful APIs
for web crawling, content discovery, and AI-powered analysis.
"""

import os
import time
import warnings
from contextlib import asynccontextmanager
from typing import Any

# Emit deprecation warning on import
warnings.warn(
    "The Scout Agent is deprecated. Use Investigator (agents/fact_checker) or Crawler (agents/crawler) instead.",
    DeprecationWarning,
    stacklevel=2
)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from common.metrics import JustNewsMetrics
from common.observability import get_logger, bootstrap_observability

from .scout_engine import CrawlMode, ScoutConfig, ScoutEngine
from .tools import (
    analyze_sentiment_tool,
    crawl_url_tool,
    deep_crawl_tool,
    detect_bias_tool,
    discover_sources_tool,
    get_stats,
    health_check,
)

# MCP Bus integration
try:
    from agents.common.mcp_bus_client import MCPBusClient
    MCP_AVAILABLE = True
except ImportError:
    MCPBusClient = None
    MCP_AVAILABLE = False

# Initialize Observability (Logging + Monitoring Core)
bootstrap_observability("scout")
logger = get_logger(__name__)

# Global engine instance
engine: ScoutEngine | None = None


# Request/Response Models
class DiscoverSourcesRequest(BaseModel):
    """Request model for source discovery."""

    domains: list[str] | None = Field(None, description="Specific domains to search")
    max_sources: int = Field(10, description="Maximum sources to discover")
    include_social: bool = Field(True, description="Include social media sources")


class DiscoverSourcesResponse(BaseModel):
    """Response model for source discovery."""

    success: bool = Field(..., description="Discovery success status")
    sources: list[dict[str, Any]] = Field(..., description="Discovered sources")
    total_found: int = Field(..., description="Total sources found")
    processing_time: float = Field(..., description="Processing time in seconds")


class CrawlURLRequest(BaseModel):
    """Request model for URL crawling."""

    url: str = Field(..., description="URL to crawl")
    mode: CrawlMode = Field(default=CrawlMode.STANDARD, description="Crawling mode")
    max_depth: int = Field(2, description="Maximum crawl depth")
    follow_external: bool = Field(False, description="Follow external links")


class CrawlURLResponse(BaseModel):
    """Response model for URL crawling."""

    success: bool = Field(..., description="Crawling success status")
    url: str = Field(..., description="Crawled URL")
    content: dict[str, Any] = Field(..., description="Extracted content")
    links_found: list[str] = Field(..., description="Links discovered")
    processing_time: float = Field(..., description="Processing time in seconds")


class DeepCrawlRequest(BaseModel):
    """Request model for deep site crawling."""

    site_url: str = Field(..., description="Site URL to crawl deeply")
    max_pages: int = Field(50, description="Maximum pages to crawl")
    concurrent_requests: int = Field(5, description="Concurrent request limit")


class DeepCrawlResponse(BaseModel):
    """Response model for deep crawling."""

    success: bool = Field(..., description="Deep crawl success status")
    site_url: str = Field(..., description="Site URL crawled")
    pages_crawled: int = Field(..., description="Number of pages crawled")
    articles_found: list[dict[str, Any]] = Field(..., description="Articles discovered")
    processing_time: float = Field(..., description="Processing time in seconds")


class SentimentAnalysisRequest(BaseModel):
    """Request model for sentiment analysis."""

    text: str = Field(..., description="Text to analyze")
    include_confidence: bool = Field(True, description="Include confidence scores")


class SentimentAnalysisResponse(BaseModel):
    """Response model for sentiment analysis."""

    success: bool = Field(..., description="Analysis success status")
    sentiment: str = Field(..., description="Sentiment classification")
    confidence: float = Field(..., description="Confidence score")
    scores: dict[str, float] = Field(..., description="Detailed sentiment scores")


class BiasDetectionRequest(BaseModel):
    """Request model for bias detection."""

    text: str = Field(..., description="Text to analyze for bias")
    include_explanation: bool = Field(True, description="Include bias explanation")


class BiasDetectionResponse(BaseModel):
    """Response model for bias detection."""

    success: bool = Field(..., description="Detection success status")
    bias_score: float = Field(..., description="Bias score (0.0-1.0)")
    bias_type: str = Field(..., description="Type of bias detected")
    explanation: str = Field(..., description="Bias explanation")


class HealthResponse(BaseModel):
    """Response model for health checks."""

    timestamp: float = Field(..., description="Health check timestamp")
    overall_status: str = Field(..., description="Overall health status")
    components: dict[str, Any] = Field(..., description="Component health status")
    issues: list[str] = Field(..., description="List of issues found")


class StatsResponse(BaseModel):
    """Response model for statistics."""

    total_crawled: int = Field(..., description="Total URLs crawled")
    total_discovered: int = Field(..., description="Total sources discovered")
    success_rate: float = Field(..., description="Success rate (0.0-1.0)")
    average_processing_time: float = Field(..., description="Average processing time")
    uptime: float = Field(..., description="Service uptime in seconds")


# Lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    global engine

    # Startup
    logger.info("🚀 Starting Scout Agent...")

    try:
        # Initialize engine
        config = ScoutConfig()
        engine = ScoutEngine(config)

        # Register with MCP Bus if available
        if MCP_AVAILABLE:
            await register_with_mcp_bus()

        logger.info("✅ Scout Agent started successfully")

        yield

    except Exception as e:
        logger.error(f"❌ Failed to start Scout Agent: {e}")
        raise
    finally:
        # Shutdown
        logger.info("🛑 Shutting down Scout Agent...")

        # Cleanup engine
        if engine:
            engine.cleanup()

        logger.info("✅ Scout Agent shutdown complete")


async def register_with_mcp_bus():
    """Register agent with MCP Bus."""
    if not MCP_AVAILABLE:
        logger.warning("MCP Bus client not available - skipping registration")
        return

    try:
        mcp_bus_url = os.getenv("MCP_BUS_URL", "http://localhost:8000")
        client = MCPBusClient(mcp_bus_url)

        host = os.getenv("SCOUT_HOST", "localhost")
        port = os.getenv("SCOUT_PORT", "8002") 
        agent_address = f"http://{host}:{port}"

        # Register synchronously (MCPBusClient.register_agent is sync)
        client.register_agent(
            agent_name="scout",
            agent_address=agent_address,
            tools=[
                "source_discovery",
                "web_crawling",
                "deep_crawling", 
                "sentiment_analysis",
                "bias_detection"
            ]
        )
        logger.info("✅ Registered with MCP Bus")

    except Exception as e:
        logger.error(f"❌ MCP Bus registration failed: {e}")


# Create FastAPI app
app = FastAPI(
    title="Scout Agent",
    description="AI-powered web crawling and content analysis agent",
    version="2.0.0",
    lifespan=lifespan,
)

# Metrics setup
metrics = JustNewsMetrics("scout")
app.middleware("http")(metrics.request_middleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global startup time
startup_time = time.time()


@app.get("/")
async def root():
    """Root endpoint with basic information."""
    return {
        "name": "Scout Agent",
        "version": "2.0.0",
        "description": "AI-powered web crawling and content analysis",
        "status": "running",
    }


@app.post("/discover_sources", response_model=DiscoverSourcesResponse)
async def discover_sources_endpoint(request: DiscoverSourcesRequest):
    """
    Discover news sources and websites.

    This endpoint uses intelligent algorithms to find relevant news sources
    based on the provided criteria.
    """
    global engine

    if not engine:
        raise HTTPException(status_code=503, detail="Scout engine not initialized")

    try:
        logger.info(
            f"🔍 Discovering sources: domains={request.domains}, max_sources={request.max_sources}"
        )

        result = await discover_sources_tool(
            engine=engine,
            domains=request.domains,
            max_sources=request.max_sources,
            include_social=request.include_social,
        )

        response = DiscoverSourcesResponse(**result)
        logger.info(
            f"✅ Source discovery completed: {len(result.get('sources', []))} sources found"
        )
        return response

    except Exception as e:
        logger.error(f"❌ Source discovery failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Source discovery failed: {str(e)}"
        ) from e


@app.post("/crawl_url", response_model=CrawlURLResponse)
async def crawl_url_endpoint(request: CrawlURLRequest):
    """
    Crawl a specific URL for content extraction.

    This endpoint crawls the provided URL and extracts relevant content
    using the specified crawling mode.
    """
    global engine

    if not engine:
        raise HTTPException(status_code=503, detail="Scout engine not initialized")

    try:
        logger.info(f"🕷️ Crawling URL: {request.url}")

        result = await crawl_url_tool(
            engine=engine,
            url=request.url,
            mode=request.mode,
            max_depth=request.max_depth,
            follow_external=request.follow_external,
        )

        response = CrawlURLResponse(**result)
        logger.info(
            f"✅ URL crawling completed: {result.get('processing_time', 0):.2f}s"
        )
        return response

    except Exception as e:
        logger.error(f"❌ URL crawling failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"URL crawling failed: {str(e)}"
        ) from e


@app.post("/deep_crawl_site", response_model=DeepCrawlResponse)
async def deep_crawl_site_endpoint(request: DeepCrawlRequest):
    """
    Perform deep crawling of a website.

    This endpoint performs comprehensive crawling of a website to discover
    and extract multiple articles and content.
    """
    global engine

    if not engine:
        raise HTTPException(status_code=503, detail="Scout engine not initialized")

    try:
        logger.info(f"🔬 Deep crawling site: {request.site_url}")

        result = await deep_crawl_tool(
            engine=engine,
            site_url=request.site_url,
            max_pages=request.max_pages,
            concurrent_requests=request.concurrent_requests,
        )

        response = DeepCrawlResponse(**result)
        logger.info(
            f"✅ Deep crawl completed: {result.get('pages_crawled', 0)} pages, {len(result.get('articles_found', []))} articles"
        )
        return response

    except Exception as e:
        logger.error(f"❌ Deep crawl failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Deep crawl failed: {str(e)}"
        ) from e


@app.post("/analyze_sentiment", response_model=SentimentAnalysisResponse)
async def analyze_sentiment_endpoint(request: SentimentAnalysisRequest):
    """
    Analyze sentiment in provided text.

    This endpoint uses AI models to analyze the sentiment of the provided text
    and returns classification with confidence scores.
    """
    global engine

    if not engine:
        raise HTTPException(status_code=503, detail="Scout engine not initialized")

    try:
        logger.info(f"😊 Analyzing sentiment for text ({len(request.text)} chars)")

        result = await analyze_sentiment_tool(
            engine=engine,
            text=request.text,
            include_confidence=request.include_confidence,
        )

        response = SentimentAnalysisResponse(**result)
        logger.info(
            f"✅ Sentiment analysis completed: {result.get('sentiment', 'unknown')}"
        )
        return response

    except Exception as e:
        logger.error(f"❌ Sentiment analysis failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Sentiment analysis failed: {str(e)}"
        ) from e


@app.post("/detect_bias", response_model=BiasDetectionResponse)
async def detect_bias_endpoint(request: BiasDetectionRequest):
    """
    Detect bias in provided text.

    This endpoint analyzes text for potential bias using AI models
    and provides detailed bias assessment.
    """
    global engine

    if not engine:
        raise HTTPException(status_code=503, detail="Scout engine not initialized")

    try:
        logger.info(f"⚖️ Detecting bias for text ({len(request.text)} chars)")

        result = await detect_bias_tool(
            engine=engine,
            text=request.text,
            include_explanation=request.include_explanation,
        )

        response = BiasDetectionResponse(**result)
        logger.info(
            f"✅ Bias detection completed: score={result.get('bias_score', 0.0):.2f}"
        )
        return response

    except Exception as e:
        logger.error(f"❌ Bias detection failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Bias detection failed: {str(e)}"
        ) from e


@app.get("/health", response_model=HealthResponse)
async def health_endpoint():
    """Health check endpoint for monitoring and load balancers."""
    global engine

    if not engine:
        raise HTTPException(status_code=503, detail="Scout engine not initialized")

    try:
        health_result = await health_check(engine)
        return HealthResponse(**health_result)
    except Exception as e:
        logger.error(f"❌ Health check error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Health check failed: {str(e)}"
        ) from e


@app.get("/stats", response_model=StatsResponse)
async def stats_endpoint():
    """Get processing statistics and performance metrics."""
    global engine

    if not engine:
        raise HTTPException(status_code=503, detail="Scout engine not initialized")

    try:
        uptime = time.time() - startup_time

        stats_result = await get_stats(engine)
        stats = StatsResponse(
            total_crawled=stats_result.get("total_crawled", 0),
            total_discovered=stats_result.get("total_discovered", 0),
            success_rate=stats_result.get("success_rate", 0.0),
            average_processing_time=stats_result.get("average_processing_time", 0.0),
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
        "name": "Scout Agent",
        "version": "2.0.0",
        "capabilities": [
            "source_discovery",
            "web_crawling",
            "deep_crawling",
            "sentiment_analysis",
            "bias_detection",
            "content_extraction",
        ],
        "supported_modes": ["fast", "standard", "deep"],
        "ai_models": ["bert", "deberta", "roberta"],
        "max_concurrent_crawls": 10,
        "rate_limits": {"requests_per_minute": 60, "concurrent_crawls": 5},
    }


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


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(
        content=metrics.get_metrics(), media_type="text/plain; charset=utf-8"
    )


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("SCOUT_HOST", "0.0.0.0")
    port = int(os.environ.get("SCOUT_PORT", os.environ.get("PORT", "8002")))
    reload_flag = (
        os.environ.get(
            "UVICORN_RELOAD", os.environ.get("SCOUT_RELOAD", "false")
        ).lower()
        == "true"
    )
    log_level = os.environ.get(
        "UVICORN_LOG_LEVEL", os.environ.get("SCOUT_LOG_LEVEL", "info")
    )

    target = f"{__package__}.main:app" if __package__ else "main:app"

    logger.info(
        "Starting Scout Service on %s:%s (reload=%s)",
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
