"""
Synthesizer Agent - Simplified FastAPI Application

This module provides a simplified synthesizer agent with GPU-accelerated
content synthesis capabilities using a 4-model architecture (BERTopic,
BART, FLAN-T5, SentenceTransformers).

Key Features:
- Article clustering and synthesis
- GPU acceleration with CPU fallbacks
- MCP bus integration
- Comprehensive error handling
- Performance monitoring
- Transparency gating: the synthesizer refuses to report ready until the
    evidence audit API responds successfully.

Endpoints:
- POST /cluster_articles: Cluster articles into themes
- POST /neutralize_text: Remove bias from text
- POST /aggregate_cluster: Aggregate cluster into summary
- POST /synthesize_news_articles_gpu: GPU-accelerated synthesis
- GET /health: Health check
- GET /stats: Performance statistics
"""

import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import requests
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from agents.common.mcp_bus_client import MCPBusClient
from common.metrics import JustNewsMetrics
from common.observability import bootstrap_observability, get_logger

bootstrap_observability("synthesizer")

# Compatibility: expose create_database_service for tests that patch agent modules
try:
    from database.utils.migrated_database_utils import (
        create_database_service,  # type: ignore
    )
except Exception:
    create_database_service = None

# Import refactored components
from config.core import get_config

from .job_store import create_job, get_job, set_error, set_result, update_status
from .synthesizer_engine import SynthesizerEngine
from .tools import (
    aggregate_cluster_tool,
    cluster_articles_tool,
    get_stats,
    health_check,
    neutralize_text_tool,
    summarize_article,
    synthesize_gpu_tool,
)

logger = get_logger(__name__)


# Environment variables
SYNTHESIZER_AGENT_PORT: int = int(os.environ.get("SYNTHESIZER_AGENT_PORT", 8005))
MCP_BUS_URL: str = os.environ.get("MCP_BUS_URL", "http://localhost:8000")
EVIDENCE_AUDIT_BASE_URL: str | None = os.environ.get("EVIDENCE_AUDIT_BASE_URL")
TRANSPARENCY_HEALTH_TIMEOUT: float = float(
    os.environ.get("TRANSPARENCY_HEALTH_TIMEOUT", "3.0")
)
TRANSPARENCY_AUDIT_REQUIRED: bool = (
    os.environ.get("REQUIRE_TRANSPARENCY_AUDIT", "1") != "0"
)

# Global engine instance
synthesizer_engine: SynthesizerEngine | None = None
transparency_gate_passed: bool = False


def generate_summary(text: str, max_length: int = 256) -> dict[str, Any]:
    """Create a lightweight summary of ``text``.

    This helper offers a stable import surface for legacy integrations and
    security tests that patch the summarisation routine. When the engine is
    available we reuse its aggregation pipeline; otherwise we fall back to a
    trimmed preview so callers always receive a predictable structure.
    """

    if not text:
        return {"summary": "", "truncated": False}

    preview = text[:max_length].strip()

    # We avoid invoking asynchronous engine routines directly here to keep the
    # helper usable from both async and sync contexts. The detailed synthesis
    # endpoints provide richer summaries; this helper simply returns a trimmed
    # preview that callers can patch in tests.
    return {"summary": preview, "truncated": len(text) > len(preview)}





def check_transparency_gateway(
    *,
    base_url: str | None,
    timeout: float,
    required: bool,
) -> bool:
    """Ensure the evidence audit API is reachable before synthesis proceeds."""

    if not base_url:
        message = "EVIDENCE_AUDIT_BASE_URL is not configured"
        if required:
            raise RuntimeError(message)
        logger.warning("%s; continuing in soft-fail mode", message)
        return False

    status_url = f"{base_url.rstrip('/')}/status"
    try:
        response = requests.get(status_url, timeout=timeout)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
    except (
        Exception
    ) as exc:  # pragma: no cover - exercised in unit tests via monkeypatch
        if required:
            raise RuntimeError(f"Transparency status request failed: {exc}") from exc
        logger.warning("Transparency status request failed: %s", exc)
        return False

    integrity = payload.get("integrity", {})
    status = integrity.get("status")
    if status not in {"ok", "degraded"}:
        message = f"Transparency integrity status '{status}' is not acceptable"
        if required:
            raise RuntimeError(message)
        logger.warning(message)
        return False

    if status == "degraded":
        logger.warning(
            "Transparency dataset integrity degraded: missing_assets=%s",
            integrity.get("missing_assets", []),
        )

    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown context manager for the FastAPI app."""
    global synthesizer_engine, transparency_gate_passed

    logger.info("🚀 Synthesizer agent is starting up.")

    # Initialize synthesizer engine
    try:
        synthesizer_engine = SynthesizerEngine()
        await synthesizer_engine.initialize()
        logger.info("✅ Synthesizer engine initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize synthesizer engine: {e}")
        synthesizer_engine = None

    # Block readiness until transparency evidence API is healthy
    try:
        transparency_gate_passed = check_transparency_gateway(
            base_url=EVIDENCE_AUDIT_BASE_URL,
            timeout=TRANSPARENCY_HEALTH_TIMEOUT,
            required=TRANSPARENCY_AUDIT_REQUIRED,
        )
        if transparency_gate_passed:
            logger.info(
                "🔍 Transparency gate satisfied; proceeding with synthesizer startup"
            )
        elif not TRANSPARENCY_AUDIT_REQUIRED:
            # If transparency audit is not required, mark gate as passed for readiness
            transparency_gate_passed = True
            logger.info(
                "✅ Transparency audit requirement disabled; proceeding with reduced transparency mode"
            )
        else:
            logger.warning(
                "⚠️ Transparency gate not satisfied but audit requirement disabled; synthesizer will remain not-ready"
            )
    except RuntimeError as exc:
        logger.error("Transparency audit check failed: %s", exc)
        synthesizer_engine = None
        transparency_gate_passed = False
        if TRANSPARENCY_AUDIT_REQUIRED:
            raise

    # Register with MCP bus
    mcp_bus_client = MCPBusClient(base_url=MCP_BUS_URL)
    try:
        mcp_bus_client.register_agent(
            agent_name="synthesizer",
            agent_address=f"http://localhost:{SYNTHESIZER_AGENT_PORT}",
            tools=[
                "cluster_articles",
                "neutralize_text",
                "aggregate_cluster",
                "synthesize_news_articles_gpu",
                "get_synthesizer_performance",
                "summarize_article",
            ],
        )
        logger.info("✅ Registered tools with MCP Bus.")
    except Exception:
        logger.warning("⚠️ MCP Bus unavailable; running in standalone mode.")

    yield

    # Cleanup on shutdown
    if synthesizer_engine:
        try:
            synthesizer_engine.cleanup()
            logger.info("🧹 Synthesizer engine cleanup completed")
        except Exception as e:
            logger.warning(f"⚠️ Engine cleanup warning: {e}")

    logger.info("🛑 Synthesizer agent is shutting down.")


app = FastAPI(
    title="Synthesizer Agent",
    description="GPU-accelerated news article synthesis and clustering",
    version="3.0.0",
    lifespan=lifespan,
)

# Initialize metrics
metrics = JustNewsMetrics("synthesizer")
app.middleware("http")(metrics.request_middleware)

# Register common endpoints
try:
    from agents.common.shutdown import register_shutdown_endpoint

    register_shutdown_endpoint(app)
except Exception:
    logger.debug("Shutdown endpoint not registered")

try:
    from agents.common.reload import register_reload_endpoint

    register_reload_endpoint(app)
except Exception:
    logger.debug("Reload endpoint not registered")


class ToolCall(BaseModel):
    """Standard MCP tool call format."""

    args: list[Any] = []
    kwargs: dict[str, Any] = {}


class SynthesisRequest(BaseModel):
    """Request model for synthesis operations."""

    articles: list[dict[str, Any]]
    max_clusters: int | None = 5
    context: str | None = "news analysis"
    # Optional cluster identifier to fetch articles and run analysis
    cluster_id: str | None = None
    publish: bool = False
    story_id: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    if synthesizer_engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    if not transparency_gate_passed:
        raise HTTPException(
            status_code=503, detail="Transparency audit gateway not satisfied"
        )
    return {"status": "ok", "engine": "ready", "transparency": "verified"}


@app.get("/ready")
def ready_endpoint() -> dict[str, bool]:
    """Readiness probe."""
    return {"ready": synthesizer_engine is not None and transparency_gate_passed}


@app.get("/metrics")
def get_metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(content=metrics.get_metrics(), media_type="text/plain")


@app.post("/log_feedback")
def log_feedback(call: ToolCall) -> dict[str, Any]:
    """Log feedback sent from other agents or tests."""
    try:
        feedback_data = {
            "timestamp": datetime.now().isoformat(),
            "feedback": call.kwargs.get("feedback"),
        }
        logger.info(f"📝 Logging feedback: {feedback_data}")
        return feedback_data
    except Exception as e:
        logger.exception("❌ Failed to log feedback")
        raise HTTPException(status_code=500, detail="Failed to log feedback") from e


@app.post("/cluster_articles")
async def cluster_articles_endpoint(call: ToolCall) -> Any:
    """Cluster a list of articles into groups."""
    if synthesizer_engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        # Extract parameters
        article_texts = (
            call.args[0] if call.args else call.kwargs.get("article_texts", [])
        )
        n_clusters = call.kwargs.get("n_clusters", 2)

        if not article_texts:
            raise HTTPException(status_code=400, detail="No articles provided")

        logger.info(
            f"🎯 Clustering {len(article_texts)} articles into {n_clusters} clusters"
        )

        result = await cluster_articles_tool(
            synthesizer_engine, article_texts, n_clusters
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("❌ Cluster articles failed")
        raise HTTPException(
            status_code=500, detail=f"Clustering failed: {str(e)}"
        ) from e


@app.post("/neutralize_text")
async def neutralize_text_endpoint(call: ToolCall) -> Any:
    """Neutralize text for bias and aggressive language."""
    if synthesizer_engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        text = call.args[0] if call.args else call.kwargs.get("text", "")

        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="No text provided")

        logger.info(f"⚖️ Neutralizing text ({len(text)} chars)")

        result = await neutralize_text_tool(synthesizer_engine, text)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("❌ Neutralize text failed")
        raise HTTPException(
            status_code=500, detail=f"Neutralization failed: {str(e)}"
        ) from e


@app.post("/aggregate_cluster")
async def aggregate_cluster_endpoint(call: ToolCall) -> Any:
    """Aggregate a cluster of articles into a synthesis."""
    if synthesizer_engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        article_texts = (
            call.args[0] if call.args else call.kwargs.get("article_texts", [])
        )
        # Map 'type' from caller to 'aggregation_type' for tool
        aggregation_type = call.kwargs.get("type", "full")
        previous_context = call.kwargs.get("previous_context")

        if not article_texts:
            raise HTTPException(status_code=400, detail="No articles provided")

        logger.info(f"📝 Aggregating {len(article_texts)} articles (type={aggregation_type})")

        result = await aggregate_cluster_tool(
            synthesizer_engine,
            article_texts,
            aggregation_type=aggregation_type,
            previous_context=previous_context
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("❌ Aggregate cluster failed")
        raise HTTPException(
            status_code=500, detail=f"Aggregation failed: {str(e)}"
        ) from e


@app.post("/synthesize_news_articles_gpu")
async def synthesize_news_articles_gpu_endpoint(
    request: SynthesisRequest,
) -> dict[str, Any]:
    """GPU-accelerated news article synthesis endpoint."""
    if synthesizer_engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        if not request.articles:
            raise HTTPException(status_code=400, detail="No articles provided")

        logger.info(
            f"🚀 GPU synthesis: {len(request.articles)} articles, max_clusters={request.max_clusters}"
        )

        result = await synthesize_gpu_tool(
            synthesizer_engine,
            request.articles,
            request.max_clusters,
            request.context,
            cluster_id=request.cluster_id,
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("❌ GPU synthesis failed")
        raise HTTPException(
            status_code=500, detail=f"GPU synthesis failed: {str(e)}"
        ) from e


@app.post("/synthesize_and_publish")
async def synthesize_and_publish(request: SynthesisRequest) -> dict[str, Any]:
    """Synthesize content and optionally publish it if editorial gates pass."""

    if synthesizer_engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    # Default behavior: call the synthesize tool
    result = await synthesize_gpu_tool(
        synthesizer_engine,
        request.articles,
        request.max_clusters,
        request.context,
        cluster_id=request.cluster_id,
    )

    if not result or not result.get("success"):
        return {"status": "error", "error": "synthesis_failed", "details": result}

    # Critic check
    try:
        # Critic supports a sync API; use the async wrapper for thread-safety
        from agents.critic.tools import process_critique_request

        critic_result = await process_critique_request(
            result.get("synthesis", ""), "synthesis"
        )
    except Exception:
        critic_result = {"error": "critic_failed"}

    # Draft fact-check (run always; publishing gate will decide enforcement)
    try:
        import agents.analyst.tools as _analyst_tools

        draft_report = getattr(
            _analyst_tools, "generate_analysis_report", lambda *a, **k: None
        )(
            [result.get("synthesis", "")],
            article_ids=None,
            cluster_id=request.cluster_id,
        )
    except Exception:
        draft_report = None

    # Decide publish gating via configuration
    cfg = get_config()
    # If system has a persistence preference, honor it.
    try:
        persistence_mode = cfg.system.get("persistence", {}).get(
            "synthesized_article_storage", "extend"
        )
    except Exception:
        persistence_mode = "extend"
    publish_cfg = cfg.agents.publishing
    require_pass = bool(publish_cfg.require_draft_fact_check_pass_for_publish)

    # Determine draft fact-check status
    fact_status = None
    if isinstance(draft_report, dict):
        per_article = draft_report.get("per_article", [])
        if per_article and isinstance(per_article, list):
            sa = (
                per_article[0].get("source_fact_check")
                if isinstance(per_article[0], dict)
                else None
            )
            fact_status = sa.get("fact_check_status") if isinstance(sa, dict) else None
        if not fact_status:
            sfc = draft_report.get("source_fact_checks", [])
            if sfc and isinstance(sfc, list) and isinstance(sfc[0], dict):
                fact_status = sfc[0].get("fact_check_status")

    # Gate on fact-check pass if required
    if require_pass and fact_status != "passed":
        return {
            "status": "error",
            "error": "draft_fact_check_failed",
            "analysis_report": draft_report,
            "critic_result": critic_result,
        }

    # Persist synthesized draft depending on persistence mode (best-effort)
    try:
        from .persistence import save_synthesized_draft

        # If we can compute an embedding, pass it; otherwise let save function handle None
        embedding = None
        try:
            if synthesizer_engine and getattr(
                synthesizer_engine, "embedding_model", None
            ):
                # compute embedding via sentence-transformers model
                embedding = list(
                    map(
                        float,
                        synthesizer_engine.embedding_model.encode(
                            result.get("synthesis", "")
                        ),
                    )
                )
        except Exception:
            embedding = None

        audit_story_id = request.story_id or f"synth_{request.cluster_id or 'manual'}_{int(datetime.now().timestamp())}"
        synthesis_text = result.get("synthesis", "")
        synthesis_metadata = {
            "provenance": {
                "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "source_agent": "synthesizer",
                "entrypoint": "synthesize_and_publish",
                "cluster_id": request.cluster_id,
                "story_id": audit_story_id,
                "method": result.get("method"),
                "model_used": result.get("model_used"),
                "confidence": result.get("confidence"),
                "context": request.context,
                "articles_processed": result.get("articles_processed"),
                "clusters_found": result.get("clusters_found"),
                "synthesis_length_chars": len(synthesis_text or ""),
                "synthesis_length_words": len((synthesis_text or "").split()),
            },
            "critic": critic_result,
            "draft_fact_check": draft_report,
        }

        save_synthesized_draft(
            story_id=audit_story_id,
            title=result.get("title") or result.get("synthesis", "")[:200],
            body=result.get("synthesis", ""),
            summary=result.get("summary"),
            analysis_summary=getattr(draft_report, "analysis_summary", None)
            if draft_report
            else None,
            synth_metadata=synthesis_metadata,
            persistence_mode=persistence_mode,
            embedding=embedding,
        )
    except Exception:
        # best-effort: persist may fail, but publishing should proceed; log and continue
        logger.exception("Failed to persist synthesized draft (non-fatal)")

    # Decide whether we need chief editor review
    if publish_cfg.chief_editor_review_required and not request.publish:
        return {
            "status": "queued_for_review",
            "analysis_report": draft_report,
            "critic_result": critic_result,
        }

    # Auto-publish via chief editor tool
    try:
        from agents.chief_editor.tools import publish_story

        story_id = (
            request.story_id
            or f"synth_{request.cluster_id or 'manual'}_{int(datetime.now().timestamp())}"
        )
        publish_result = publish_story(story_id)
        return {
            "status": publish_result.get("status", "published"),
            "story_id": publish_result.get("story_id", story_id),
            "analysis_report": draft_report,
            "critic_result": critic_result,
        }
    except Exception as e:
        logger.exception("Publish failed")
        return {"status": "error", "error": "publish_failed", "details": str(e)}

    # End: synthesize_news_articles_gpu_endpoint


@app.post("/get_synthesizer_performance")
async def get_synthesizer_performance_endpoint(call: ToolCall) -> dict[str, Any]:
    """Get synthesizer performance statistics."""
    if synthesizer_engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        logger.info("📊 Retrieving synthesizer performance stats")

        result = await get_stats(synthesizer_engine)
        return result
    except Exception as e:
        logger.exception("❌ Performance stats failed")
        raise HTTPException(
            status_code=500, detail=f"Performance stats failed: {str(e)}"
        ) from e


@app.post("/api/v1/articles/synthesize")
async def synthesize_article_job(request: SynthesisRequest):
    """Kick off an asynchronous synthesis job and return a job_id for status checks."""
    import uuid

    if synthesizer_engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    job_id = str(uuid.uuid4())
    create_job(job_id)

    async def _run_job(job_id_local: str):
        try:
            update_status(job_id_local, "running")
            res = await synthesize_gpu_tool(
                synthesizer_engine,
                request.articles,
                request.max_clusters,
                request.context,
                cluster_id=request.cluster_id,
            )
            set_result(job_id_local, res)
        except Exception as exc:
            set_error(job_id_local, str(exc))

    # Fire-and-forget background task
    import asyncio

    asyncio.create_task(_run_job(job_id))
    return {"job_id": job_id}


@app.get("/api/v1/articles/synthesize/{job_id}")
async def get_synthesis_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# Health and stats endpoints
@app.get("/stats")
async def get_stats_endpoint() -> dict[str, Any]:
    """Get comprehensive synthesizer statistics."""
    if synthesizer_engine is None:
        return {"error": "Engine not initialized"}

    try:
        return await health_check(synthesizer_engine)
    except Exception as e:
        logger.exception("❌ Stats endpoint failed")
        return {"error": str(e)}


# Compatibility aliases
@app.post("/synthesize_content")
async def synthesize_content_alias(request: SynthesisRequest) -> Any:
    """Alias for compatibility with existing E2E tests."""
    return await synthesize_news_articles_gpu_endpoint(request)


@app.post("/summarize_article")
async def summarize_article_endpoint(call: ToolCall) -> Any:
    """Summarize a single article."""
    if synthesizer_engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        # Extract article_id from args or kwargs
        if call.args:
            article_id = call.args[0]
        else:
            article_id = call.kwargs.get("article_id")

        if not article_id:
            raise HTTPException(status_code=400, detail="No article_id provided")

        logger.info(f"📝 Request to summarize article {article_id}")
        return await summarize_article(synthesizer_engine, int(article_id))

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("❌ Summarization failed")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    host: str = os.environ.get("SYNTHESIZER_HOST", "0.0.0.0")
    port: int = int(os.environ.get("SYNTHESIZER_PORT", SYNTHESIZER_AGENT_PORT))

    logger.info("🎯 Starting Synthesizer Agent on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port)
