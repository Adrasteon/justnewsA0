"""
Memory Agent - FastAPI Application with MCP Integration
=======================================================

Core Responsibilities:
- FastAPI web API with MCP Bus integration
- Article storage and retrieval endpoints
- Vector search capabilities
- Training example logging
- Background processing coordination
- Health monitoring and metrics

Architecture:
- Modular design with separate engines for different concerns
- Async background processing with ThreadPoolExecutor
- Database connection pooling
- GPU-accelerated embedding model management
- Comprehensive error handling and logging
"""

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from agents.common.mcp_bus_client import MCPBusClient
from common.metrics import JustNewsMetrics
from common.observability import bootstrap_observability, get_logger

# Compatibility: expose create_database_service for tests that patch agent modules
try:
    from database.utils.migrated_database_utils import (
        create_database_service,  # type: ignore
    )
except Exception:
    create_database_service = None

# Import memory agent engines
from agents.memory.memory_engine import MemoryEngine
from agents.memory.vector_engine import VectorEngine
from agents.memory.worker_engine import WorkerEngine

# Configure centralized logging
bootstrap_observability("memory")
logger = get_logger(__name__)

# Readiness flag
ready = False

# Global engine instances
memory_engine: MemoryEngine | None = None
vector_engine: VectorEngine | None = None
worker_engine: WorkerEngine | None = None

# Environment variables
MEMORY_AGENT_PORT = int(os.environ.get("MEMORY_AGENT_PORT", 8007))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")


def query_articles(query: str, limit: int = 10) -> list[dict]:
    """Lightweight helper for querying stored articles.

    Provides a stable import target for legacy code and tests that patch the
    memory agent's query functionality. When the vector engine is available we
    delegate to its local search implementation; otherwise we return an empty
    list to indicate no matches.
    """

    if vector_engine is None:
        logger.debug("Vector engine not initialized; returning no articles for query")
        return []

    try:
        return vector_engine.vector_search_articles_local(query, limit)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Vector search failed for query '%s': %s", query, exc)
        return []


# Pydantic models
class Article(BaseModel):
    content: str
    metadata: dict

    model_config = ConfigDict(arbitrary_types_allowed=True)


class TrainingExample(BaseModel):
    task: str
    input: dict
    output: dict
    critique: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class VectorSearch(BaseModel):
    query: str
    top_k: int = 5

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ToolCall(BaseModel):
    args: list[Any]
    kwargs: dict[str, Any]

    model_config = ConfigDict(arbitrary_types_allowed=True)





@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles startup and shutdown events for the FastAPI application."""
    global ready, memory_engine, vector_engine, worker_engine

    logger.info("Memory agent is starting up.")

    try:
        # Initialize engines
        memory_engine = MemoryEngine()
        vector_engine = VectorEngine()
        worker_engine = WorkerEngine()

        # Initialize components
        try:
            await memory_engine.initialize()
        except Exception as e:
            # Provide extra guidance when canonical Chroma validation fails
            from database.utils.chromadb_utils import ChromaCanonicalValidationError

            if isinstance(e, ChromaCanonicalValidationError):
                logger.error(
                    "Memory engine failed to initialize because CHROMADB canonical validation failed.\n"
                    "  - Confirm CHROMADB_HOST/CHROMADB_PORT match the canonical CHROMADB_CANONICAL_HOST/PORT in /etc/justnews/global.env\n"
                    "  - Use 'scripts/chroma_diagnose.py' and 'scripts/chroma_bootstrap.py' to diagnose and provision the tenant/collection\n"
                    "  - Example: PYTHONPATH=. conda run -n ${CANONICAL_ENV:-justnews-py312} python scripts/chroma_diagnose.py --host <host> --port <port> --autocreate"
                )
            raise
        await vector_engine.initialize()
        await worker_engine.initialize(memory_engine, vector_engine)

        # Register agent with MCP Bus
        mcp_bus_client = MCPBusClient(base_url=MCP_BUS_URL)
        try:
            mcp_bus_client.register_agent(
                agent_name="memory",
                agent_address=f"http://localhost:{MEMORY_AGENT_PORT}",
                tools=[
                    "save_article",
                    "get_article",
                    "get_all_article_ids",
                    "vector_search_articles",
                    "log_training_example",
                    "ingest_article",
                    "get_recent_articles",
                    "get_article_count",
                    "get_sources",
                ],
            )
            logger.info("Registered tools with MCP Bus.")
        except Exception as e:
            logger.warning(f"MCP Bus unavailable: {e}. Running in standalone mode.")

        # Mark ready after successful initialization
        ready = True
        logger.info("Memory agent startup completed successfully.")

    except Exception as e:
        logger.error(f"Failed to initialize memory agent: {e}")
        raise

    yield

    logger.info("Memory agent is shutting down.")

    try:
        # Shutdown engines in reverse order
        if worker_engine:
            await worker_engine.shutdown()
        if vector_engine:
            await vector_engine.shutdown()
        if memory_engine:
            await memory_engine.shutdown()

        logger.info("Memory agent shutdown completed successfully.")

    except Exception as e:
        logger.error(f"Error during memory agent shutdown: {e}")


app = FastAPI(
    lifespan=lifespan,
    title="Memory Agent",
    description="AI-powered memory and storage system",
)

# Initialize metrics
metrics = JustNewsMetrics("memory")
app.middleware("http")(metrics.request_middleware)

# Register common shutdown endpoint
try:
    from agents.common.shutdown import register_shutdown_endpoint

    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for memory")

# Register reload endpoint and handler for runtime reloads
try:
    from agents.common.reload import register_reload_endpoint, register_reload_handler

    def _reload_embedding_model():
        """Reload the embedding model from cache"""
        global vector_engine
        if vector_engine:
            try:
                # Trigger reload in vector engine
                import asyncio

                asyncio.create_task(vector_engine.reload_model())
                return {"reloaded": True}
            except Exception as e:
                return {"reloaded": False, "error": str(e)}
        return {"reloaded": False, "error": "Vector engine not available"}

    register_reload_handler("embedding_model", _reload_embedding_model)
    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for memory")


@app.get("/health")
@app.post("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "agent": "memory"}


@app.get("/ready")
def ready_endpoint():
    """Readiness endpoint for startup gating."""
    return {"ready": ready}


@app.get("/metrics")
def metrics_endpoint():
    """Prometheus metrics endpoint"""
    from fastapi.responses import Response

    return Response(metrics.get_metrics(), media_type="text/plain; charset=utf-8")


@app.post("/save_article")
def save_article_endpoint(request: dict):
    """Saves an article to the database. Handles both direct calls and MCP Bus format."""
    try:
        # Handle MCP Bus format: {"args": [...], "kwargs": {...}}
        if "args" in request and "kwargs" in request:
            if len(request["args"]) > 0:
                article_data = request["args"][0]
            else:
                article_data = request["kwargs"]
        else:
            # Direct call format
            article_data = request

        # Create Article object from the data
        article = Article(**article_data)

        # Use the memory engine to save the article
        result = memory_engine.save_article(article.content, article.metadata)
        return result

    except Exception as e:
        logger.error(f"Error saving article: {e}")
        raise HTTPException(
            status_code=400, detail=f"Error saving article: {str(e)}"
        ) from e


@app.post("/get_article")
async def get_article_endpoint(request: Request):
    """
    Retrieves an article from the database. Designed to be called from the MCP Bus.
    """
    try:
        payload = await request.json()
        retrieval_id = None

        # The payload from the bus is a dict: {"args": [], "kwargs": {...}}
        if "kwargs" in payload and "article_id" in payload["kwargs"]:
            retrieval_id = int(payload["kwargs"]["article_id"])

        if retrieval_id is None:
            raise HTTPException(
                status_code=400,
                detail="article_id must be provided in the 'kwargs' of the tool call payload",
            )

        # Use memory engine to retrieve article
        article = memory_engine.get_article(retrieval_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        return article

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving article: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving article: {str(e)}"
        ) from e


@app.post("/get_all_article_ids")
async def get_all_article_ids_endpoint():
    """Retrieves all article IDs from the database."""
    logger.info("Received request for get_all_article_ids_endpoint")
    try:
        result = memory_engine.get_all_article_ids()
        logger.info(
            f"Returning result from get_all_article_ids_endpoint: {len(result.get('article_ids', []))} IDs"
        )
        return result
    except Exception as e:
        logger.error(f"Error retrieving article IDs: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving article IDs: {str(e)}"
        ) from e


@app.post("/vector_search_articles")
def vector_search_articles_endpoint(request: dict):
    """Performs a vector search for articles. Handles both direct calls and MCP Bus format."""
    try:
        # Handle MCP Bus format: {"args": [...], "kwargs": {...}}
        if "args" in request and "kwargs" in request:
            if len(request["args"]) > 0:
                search_data = request["args"][0]
            else:
                search_data = request["kwargs"]
        else:
            # Direct call format
            search_data = request

        # Create VectorSearch object from the data
        search = VectorSearch(**search_data)

        # Use vector engine for local search to avoid recursive HTTP calls
        results = vector_engine.vector_search_articles_local(search.query, search.top_k)
        return results

    except Exception as e:
        logger.error(f"Error searching articles: {e}")
        raise HTTPException(
            status_code=400, detail=f"Error searching articles: {str(e)}"
        ) from e


@app.post("/get_recent_articles")
def get_recent_articles_endpoint(request: dict):
    """Returns the most recent articles for synthesis/testing."""
    try:
        # Normalize payload
        limit = 10
        if isinstance(request, dict) and "args" in request and "kwargs" in request:
            if request.get("args"):
                arg0 = request["args"][0]
                if isinstance(arg0, dict) and "limit" in arg0:
                    limit = int(arg0.get("limit", limit))
            if "limit" in request.get("kwargs", {}):
                limit = int(request["kwargs"].get("limit", limit))
        elif isinstance(request, dict):
            limit = int(request.get("limit", limit))

        # Use memory engine to get recent articles
        articles = memory_engine.get_recent_articles(limit)
        return {"articles": articles}

    except Exception as e:
        logger.error(f"Error retrieving recent articles: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving recent articles: {str(e)}"
        ) from e


@app.post("/log_training_example")
def log_training_example_endpoint(example: TrainingExample):
    """Logs a training example to the database."""
    try:
        result = memory_engine.log_training_example(
            example.task, example.input, example.output, example.critique
        )
        return result
    except Exception as e:
        logger.error(f"Error logging training example: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error logging training example: {str(e)}"
        ) from e


@app.post("/ingest_article")
def ingest_article_endpoint(request: dict):
    """Handles article ingestion with sources and article_source_map operations."""
    try:
        # Handle MCP Bus format: {"args": [...], "kwargs": {...}}
        if "args" in request and "kwargs" in request:
            kwargs = request["kwargs"]
        else:
            # Direct call format
            kwargs = request

        article_payload = kwargs.get("article_payload", {})
        statements = kwargs.get("statements", [])

        if not article_payload:
            raise HTTPException(status_code=400, detail="Missing article_payload")

        logger.info(f"Ingesting article: {article_payload.get('url')}")

        # Use memory engine for ingestion
        result = memory_engine.ingest_article(article_payload, statements)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion error: {str(e)}") from e


@app.get("/get_article_count")
def get_article_count_endpoint():
    """Get total count of articles in database."""
    try:
        count = memory_engine.get_article_count()
        return {"count": count}
    except Exception as e:
        logger.error(f"Error getting article count: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving article count: {str(e)}"
        ) from e


@app.post("/get_sources")
def get_sources_endpoint(request: dict):
    """Get list of sources from the database."""
    try:
        # Handle MCP Bus format: {"args": [...], "kwargs": {...}}
        if "args" in request and "kwargs" in request:
            kwargs = request["kwargs"]
        else:
            # Direct call format
            kwargs = request

        limit = kwargs.get("limit", 10)

        # Use memory engine to get sources
        sources = memory_engine.get_sources(limit)
        return {"sources": sources}

    except Exception as e:
        logger.error(f"Error getting sources: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving sources: {str(e)}"
        ) from e


@app.get("/stats")
def get_stats_endpoint():
    """Get memory agent statistics"""
    try:
        stats = {}

        if memory_engine:
            stats.update(memory_engine.get_stats())

        if vector_engine:
            stats.update(vector_engine.get_stats())

        if worker_engine:
            stats.update(worker_engine.get_stats())

        return {"stats": stats}

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving stats: {str(e)}"
        ) from e


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("MEMORY_HOST", "0.0.0.0")
    port = int(os.environ.get("MEMORY_PORT", 8007))

    logger.info(f"Starting Memory Agent on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
