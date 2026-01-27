"""
Archive Agent Main Application

FastAPI application providing archive services with MCP integration.
Handles article archiving, retrieval, search, and knowledge graph operations.
"""

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents.archive.archive_engine import get_archive_engine
from agents.archive.metrics_registry import metrics
from agents.common.mcp_bus_client import MCPBusClient
from common.observability import bootstrap_observability, get_logger

bootstrap_observability("archive")
logger = get_logger(__name__)

# Environment variables
ARCHIVE_AGENT_PORT = int(os.environ.get("ARCHIVE_AGENT_PORT", 8012))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

# Global variables
ready = False
archive_engine = get_archive_engine()



# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Archive agent is starting up.")

    # Register with MCP Bus
    mcp_bus_client = MCPBusClient(base_url=MCP_BUS_URL)
    try:
        mcp_bus_client.register_agent(
            agent_name="archive",
            agent_address=f"http://localhost:{ARCHIVE_AGENT_PORT}",
            tools=[
                "archive_articles",
                "retrieve_article",
                "search_archive",
                "get_archive_stats",
                "store_single_article",
                "queue_article",
                "get_article_entities",
                "search_knowledge_graph",
                "link_entities",
            ],
        )
        logger.info("Registered tools with MCP Bus.")
    except Exception as e:
        logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")

    global ready
    ready = True
    yield

    logger.info("Archive agent is shutting down.")


# Initialize FastAPI app
app = FastAPI(
    title="JustNews Archive Service",
    description="Comprehensive article archiving with knowledge graph integration",
    lifespan=lifespan,
)

# Register common endpoints
try:
    from agents.common.shutdown import register_shutdown_endpoint

    register_shutdown_endpoint(app)
except Exception:
    logger.debug("Shutdown endpoint not registered for archive")

try:
    from agents.common.reload import register_reload_endpoint

    register_reload_endpoint(app)
except Exception:
    logger.debug("Reload endpoint not registered for archive")

# Add metrics middleware
app.middleware("http")(metrics.request_middleware)


# Pydantic models
class ToolCall(BaseModel):
    """Standard MCP tool call format."""

    args: list[Any] = []
    kwargs: dict[str, Any] = {}


class ArticleData(BaseModel):
    """Article data model."""

    url: str
    url_hash: str = ""
    domain: str
    title: str
    content: str
    extraction_method: str = "generic_dom"
    status: str = "success"
    crawl_mode: str = "generic_site"
    canonical: str = ""
    paywall_flag: bool = False
    confidence: float = 0.8
    publisher_meta: dict[str, Any] = {}
    news_score: float = 0.7
    timestamp: str = ""


class CrawlerResults(BaseModel):
    """Crawler results model."""

    multi_site_crawl: bool = False
    sites_crawled: int = 0
    total_articles: int = 0
    processing_time_seconds: float = 0.0
    articles_per_second: float = 0.0
    articles: list[ArticleData] = []


# Health and readiness endpoints
@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "archive"}


@app.get("/ready")
def ready_endpoint():
    """Readiness check endpoint."""
    return {"ready": ready, "service": "archive"}


@app.get("/metrics")
def get_metrics():
    """Prometheus metrics endpoint."""
    from fastapi.responses import Response

    return Response(metrics.get_metrics(), media_type="text/plain")


# Tool endpoints
@app.post("/archive_articles")
async def archive_articles_endpoint(call: ToolCall):
    """Archive articles from crawler results."""
    try:
        from agents.archive.tools import archive_articles

        result = await archive_articles(**call.kwargs)
        return {"status": "success", "data": result}

    except Exception as e:
        logger.error(f"Error in archive_articles endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/retrieve_article")
async def retrieve_article_endpoint(call: ToolCall):
    """Retrieve archived article by storage key."""
    try:
        from agents.archive.tools import retrieve_article

        storage_key = call.kwargs.get("storage_key")
        if not storage_key:
            raise HTTPException(status_code=400, detail="storage_key is required")

        article = await retrieve_article(storage_key)
        if article is None:
            raise HTTPException(
                status_code=404, detail=f"Article not found: {storage_key}"
            )

        return {"status": "success", "data": article}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in retrieve_article endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/search_archive")
async def search_archive_endpoint(call: ToolCall):
    """Search archived articles by metadata."""
    try:
        from agents.archive.tools import search_archive

        query = call.kwargs.get("query", "")
        filters = call.kwargs.get("filters", {})

        if not query:
            raise HTTPException(status_code=400, detail="query is required")

        result = await search_archive(query, filters)
        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in search_archive endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/get_archive_stats")
def get_archive_stats_endpoint(call: ToolCall):
    """Get comprehensive archive statistics."""
    try:
        from agents.archive.tools import get_archive_stats

        stats = get_archive_stats()
        return {"status": "success", "data": stats}

    except Exception as e:
        logger.error(f"Error in get_archive_stats endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/store_single_article")
async def store_single_article_endpoint(call: ToolCall):
    """Store a single article with complete metadata."""
    try:
        from agents.archive.tools import store_single_article

        result = await store_single_article(**call.kwargs)
        return {"status": "success", "data": result}

    except Exception as e:
        logger.error(f"Error in store_single_article endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/queue_article")
def queue_article_endpoint(call: ToolCall):
    """Persist a cleaned HITL article into Stage B storage."""
    try:
        from agents.archive.tools import queue_article

        payload: Any | None = None
        if call.args:
            payload = call.args[0]
        elif "job_payload" in call.kwargs:
            payload = call.kwargs.get("job_payload")
        elif call.kwargs:
            payload = call.kwargs

        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=400, detail="ingest payload must be provided"
            )

        result = queue_article(payload)
        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Error in queue_article endpoint: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/get_article_entities")
async def get_article_entities_endpoint(call: ToolCall):
    """Get knowledge graph entities for an article."""
    try:
        from agents.archive.tools import get_article_entities

        storage_key = call.kwargs.get("storage_key")
        if not storage_key:
            raise HTTPException(status_code=400, detail="storage_key is required")

        entities = await get_article_entities(storage_key)
        return {"status": "success", "data": entities}

    except Exception as e:
        logger.error(f"Error in get_article_entities endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/search_knowledge_graph")
async def search_knowledge_graph_endpoint(call: ToolCall):
    """Search the knowledge graph for entities."""
    try:
        from agents.archive.tools import search_knowledge_graph

        query = call.kwargs.get("query", "")
        if not query:
            raise HTTPException(status_code=400, detail="query is required")

        results = await search_knowledge_graph(query)
        return {
            "status": "success",
            "data": {"query": query, "results": results, "count": len(results)},
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in search_knowledge_graph endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/link_entities")
async def link_entities_endpoint(call: ToolCall):
    """Link article entities to external knowledge bases."""
    try:
        from agents.archive.tools import link_entities

        article_data = call.kwargs.get("article_data", {})
        if not article_data:
            raise HTTPException(status_code=400, detail="article_data is required")

        result = await link_entities(article_data)
        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in link_entities endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# Additional utility endpoints
@app.get("/api/health")
async def api_health():
    """Detailed health check with component status."""
    try:
        health_data = await archive_engine.health_check()
        return health_data
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Health check failed: {str(e)}"
        ) from e


@app.get("/api/stats")
def api_stats():
    """Get archive statistics via REST API."""
    try:
        stats = archive_engine.get_archive_stats()
        return stats
    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Stats retrieval failed: {str(e)}"
        ) from e


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=ARCHIVE_AGENT_PORT)
