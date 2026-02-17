"""
Synthesizer Tools - Utility Functions for Content Synthesis

This module provides utility functions for the Synthesizer agent, including
article clustering, text neutralization, cluster aggregation, and GPU-accelerated
synthesis with comprehensive error handling.

Key Functions:
- cluster_articles_tool: Cluster articles using ML techniques
- neutralize_text_tool: Remove bias from text
- aggregate_cluster_tool: Aggregate cluster into synthesis
- synthesize_gpu_tool: GPU-accelerated full synthesis pipeline
- health_check: System health monitoring
- get_stats: Performance statistics

All functions include robust error handling and fallbacks.
"""

import asyncio
import time
from typing import Any

from common.observability import get_logger

from .synthesizer_engine import SynthesizerEngine

logger = get_logger(__name__)


async def cluster_articles_tool(
    engine: SynthesizerEngine, article_texts: list[str], n_clusters: int = 3
) -> dict[str, Any]:
    """
    Cluster articles using advanced ML techniques.

    Args:
        engine: SynthesizerEngine instance
        article_texts: List of article texts to cluster
        n_clusters: Target number of clusters

    Returns:
        Clustering results with cluster assignments
    """
    logger.info(
        f"🎯 Clustering {len(article_texts)} articles into {n_clusters} clusters"
    )

    # start_time is outside the try/except so we can compute elapsed on exception paths
    start_time = time.time()
    try:
        # Validate input
        if not article_texts:
            return {
                "success": False,
                "clusters": [],
                "n_clusters": 0,
                "articles_processed": 0,
                "error": "No articles provided",
            }

        # Perform clustering
        result = await engine.cluster_articles(article_texts, n_clusters)

        processing_time = time.time() - start_time
        
        # Handle dict response (compatibility)
        if isinstance(result, dict):
             success = result.get("status") == "success"
             clusters = result.get("clusters", [])
             n_clusters_out = len(clusters)
             articles_processed = len(article_texts)
             method = "bertopic" if result.get("topic_info") else "kmeans"
             model_used = "unknown"
             confidence = 1.0
             topics = result.get("topic_info", [])
        else:
             success = getattr(result, "success", False)
             metadata = getattr(result, "metadata", {})
             clusters = metadata.get("clusters", [])
             n_clusters_out = metadata.get("n_clusters", 0)
             articles_processed = metadata.get("articles_processed", 0)
             method = getattr(result, "method", "unknown")
             model_used = getattr(result, "model_used", "unknown")
             confidence = getattr(result, "confidence", 1.0)
             topics = metadata.get("topics", [])

        response = {
            "success": success,
            "clusters": clusters,
            "n_clusters": n_clusters_out,
            "articles_processed": articles_processed,
            "method": method,
            "model_used": model_used,
            "confidence": confidence,
            "processing_time": processing_time,
        }

        # Add topics if available
        if topics:
            response["topics"] = topics
            
        # Collect prediction for training
        try:
            from training_system import collect_prediction
            # Create a summary of input for clustering (too big to log all)
            input_summary = f"Clustering {len(article_texts)} articles. Sample: {article_texts[0][:200]}..." if article_texts else "Empty input"
            collect_prediction(
                agent_name="synthesizer",
                task_type="cluster_articles",
                input_text=input_summary,
                prediction=response,
                confidence=confidence,
                source_url="",
            )
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to collect training data for clustering: {e}")

        return response

    except Exception as e:
        logger.error(f"❌ Clustering failed: {e}")
        return {
            "success": False,
            "clusters": [
                list(range(len(article_texts)))
            ],  # Fallback: all in one cluster
            "n_clusters": 1,
            "articles_processed": len(article_texts),
            "method": "error_fallback",
            "error": str(e),
            "processing_time": time.time() - start_time,
        }


async def summarize_article(engine: SynthesizerEngine, article_id: int) -> dict[str, Any]:
    """Summarize a single article by ID and update the database."""
    logger.info(f"📝 Summarizing article {article_id}")
    
    from database.utils.migrated_database_utils import create_database_service
    
    db_service = None
    try:
        db_service = create_database_service()
        db_service.ensure_conn()
        
        cursor = db_service.mb_conn.cursor()
        cursor.execute("SELECT content FROM articles WHERE id = %s", (article_id,))
        row = cursor.fetchone()
        
        if not row or not row[0]:
            cursor.close()
            return {"status": "error", "error": f"Article {article_id} not found or empty"}
            
        content = row[0]
        
        # Summarization logic
        summary = ""
        # Use engine's summarization (Qwen or fallback)
        try:
            res = await engine._summarize_text(content)
            if res and res.success:
                summary = res.content
            else:
                summary = content[:500] + "..." if len(content) > 500 else content
        except Exception as e:
            logger.warning(f"Engine summarization failed: {e}")
            summary = content[:500] + "..." if len(content) > 500 else content

        # Collect prediction for training
        try:
            from training_system import collect_prediction
            collect_prediction(
                agent_name="synthesizer",
                task_type="summarize_article",
                input_text=content[:5000],
                prediction={"summary": summary},
                confidence=1.0,
                source_url=f"article_id:{article_id}",
            )
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to collect training data for summarizer: {e}")

        cursor.execute("UPDATE articles SET summary = %s WHERE id = %s", (summary, article_id))
        db_service.mb_conn.commit()
        cursor.close()
        
        logger.info(f"✅ Article {article_id} summarized.")
        return {"status": "success", "article_id": article_id}
    except Exception as e:
        logger.error(f"❌ Summarization failed: {e}")
        return {"status": "error", "error": str(e)}



async def neutralize_text_tool(engine: SynthesizerEngine, text: str) -> dict[str, Any]:
    """
    Neutralize text for bias and aggressive language.

    Args:
        engine: SynthesizerEngine instance
        text: Text to neutralize

    Returns:
        Neutralized text results
    """
    logger.info(f"⚖️ Neutralizing text ({len(text)} chars)")

    # start_time is outside the try/except so we can compute elapsed on exception paths
    start_time = time.time()
    try:
        # Validate input
        if not text or not text.strip():
            return {
                "success": False,
                "neutralized_text": "",
                "original_text": text,
                "error": "Empty text provided",
            }

        # Perform neutralization
        result = await engine.neutralize_text(text)

        processing_time = time.time() - start_time

        response = {
            "success": result.success,
            "neutralized_text": result.content,
            "original_text": text,
            "method": result.method,
            "model_used": result.model_used,
            "confidence": result.confidence,
            "processing_time": processing_time,
        }

        # Add bias score if available
        if hasattr(result, "bias_score"):
            response["bias_score"] = result.bias_score

        # Collect prediction for training
        try:
            from training_system import collect_prediction
            collect_prediction(
                agent_name="synthesizer",
                task_type="neutralize_text",
                input_text=text[:5000],
                prediction=response,
                confidence=result.confidence,
                source_url="",
            )
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to collect training data for neutralization: {e}")

        return response

    except Exception as e:
        logger.error(f"❌ Neutralization failed: {e}")
        return {
            "success": False,
            "neutralized_text": text,  # Return original on error
            "original_text": text,
            "method": "error_fallback",
            "error": str(e),
            "processing_time": time.time() - start_time,
        }


async def aggregate_cluster_tool(
    engine: SynthesizerEngine, 
    article_texts: list[str], 
    aggregation_type: str = "full",
    previous_context: str | None = None
) -> dict[str, Any]:
    """
    Aggregate a cluster of articles into a synthesis.

    Args:
        engine: SynthesizerEngine instance
        article_texts: List of article texts to aggregate
        aggregation_type: 'full' (default) or 'brief'
        previous_context: Optional summary of previous coverage

    Returns:
        Aggregation results with synthesized content
    """
    logger.info(f"📝 Aggregating {len(article_texts)} articles (type={aggregation_type}, has_context={bool(previous_context)})")

    # start_time is outside the try/except so we can compute elapsed on exception paths
    start_time = time.time()
    try:
        # Validate input
        if not article_texts:
            return {
                "success": False,
                "summary": "",
                "key_points": [],
                "error": "No articles provided",
            }

        # Perform aggregation
        result = await engine.aggregate_cluster(article_texts, previous_context=previous_context)
        
        processing_time = time.time() - start_time

        # Check if it behaves like a dict (safe fallback)
        if isinstance(result, dict) or (hasattr(result, "get") and hasattr(result, "__getitem__")):
            # Compatibility for when engine returns a dict
            response = {
                "success": result.get("status") == "success",
                "body": result.get("body") or result.get("summary", ""),
                "summary": result.get("summary", ""),
                "key_points": result.get("key_points", []),
                "articles_processed": result.get("article_count", len(article_texts)),
                "processing_time": processing_time,
                "error": result.get("error")
            }
        else:
            metadata_summary = ""
            if getattr(result, "metadata", None) and isinstance(result.metadata, dict):
                metadata_summary = str(result.metadata.get("summary") or "")
            response = {
                "success": result.success,
                "body": result.content,
                "summary": result.content,
                "method": result.method,
                "model_used": result.model_used,
                "confidence": result.confidence,
                "articles_processed": len(article_texts),
                "processing_time": processing_time,
            }
            if metadata_summary:
                response["summary"] = metadata_summary

            # Add key points if available
            if result.metadata and "key_points" in result.metadata:
                response["key_points"] = result.metadata["key_points"]

        # Collect prediction for training
        try:
            from training_system import collect_prediction
            method_val = result.get("method", "unknown") if isinstance(result, dict) else getattr(result, "method", "unknown")
            confidence_val = result.get("confidence", 0.0) if isinstance(result, dict) else getattr(result, "confidence", 1.0)
            
            # Create input summary
            input_summary = f"Aggregating {len(article_texts)} articles. Type: {aggregation_type}. Samples: {article_texts[0][:200] if article_texts else 'None'}"

            collect_prediction(
                agent_name="synthesizer",
                task_type="aggregate_cluster",
                input_text=input_summary,
                prediction=response,
                confidence=confidence_val,
                source_url="",
            )
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to collect training data for aggregation: {e}")

        return response

    except Exception as e:
        logger.error(f"❌ Aggregation failed: {e}", exc_info=True)
        # Fallback: simple concatenation
        combined = " ".join(article_texts[:3]) if article_texts else ""
        return {
            "success": False,
            "body": combined,
            "summary": combined,
            "method": "error_fallback",
            "articles_processed": len(article_texts),
            "error": str(e),
            "processing_time": time.time() - start_time,
        }


async def synthesize_gpu_tool(
    engine: SynthesizerEngine,
    articles: list[dict[str, Any]],
    max_clusters: int = 5,
    context: str = "news analysis",
    cluster_id: str | None = None,
) -> dict[str, Any]:
    """
    GPU-accelerated full synthesis pipeline.

    Args:
        engine: SynthesizerEngine instance
        articles: List of article dictionaries
        max_clusters: Maximum number of clusters
        context: Synthesis context

    Returns:
        Full synthesis results
    """
    logger.info(
        f"🚀 GPU synthesis: {len(articles)} articles, max_clusters={max_clusters}"
    )

    # start_time is outside the try/except so we can compute elapsed on exception paths
    start_time = time.time()
    try:
        # Validate input
        if not articles:
            return {"success": False, "synthesis": "", "error": "No articles provided"}

        # Perform GPU-accelerated synthesis
        # Allow caller to provide `cluster_id` in kwargs for cluster-driven synthesis
        options = {}
        if cluster_id:
            options["cluster_id"] = cluster_id
        # if caller passed kwargs with cluster_id, prefer that
        # (compatibility: some callers pass `cluster_id` via keyword args)
        # Check the engine argument list or kwargs passed to this function
        # This tool is typically called from endpoints which we update accordingly.
        cluster_id = None
        if "cluster_id" in locals() and locals().get("cluster_id"):
            cluster_id = locals().get("cluster_id")
        # Some engine implementations accept an `options` kwarg; older ones
        # don't — detect and call accordingly for compatibility with tests
        import inspect

        try:
            sig = inspect.signature(engine.synthesize_gpu)
            if "options" in sig.parameters:
                result = await engine.synthesize_gpu(
                    articles, max_clusters, context, options=options
                )
            else:
                result = await engine.synthesize_gpu(articles, max_clusters, context)
        except (ValueError, TypeError):
            # If signature inspection fails (e.g. C-bound function), fall back to
            # attempting a kwargs call and then a positional-only call.
            try:
                result = await engine.synthesize_gpu(
                    articles, max_clusters, context, options=options
                )
            except TypeError:
                result = await engine.synthesize_gpu(articles, max_clusters, context)

        processing_time = time.time() - start_time

        response = {
            "success": result.success,
            "synthesis": result.content,
            "method": result.method,
            "model_used": result.model_used,
            "confidence": result.confidence,
            "processing_time": processing_time,
            "gpu_used": result.metadata.get("gpu_used", False),
            "articles_processed": result.metadata.get("articles_processed", 0),
            "clusters_found": result.metadata.get("clusters_found", 0),
        }

        # Add themes if available
        if result.metadata and "themes" in result.metadata:
            response["themes"] = result.metadata["themes"]

        # Calculate performance metrics
        articles_per_sec = result.metadata.get("articles_processed", 0) / max(
            processing_time, 0.001
        )

        # Log feedback for training
        engine.log_feedback(
            "synthesize_gpu",
            {
                "method": result.method,
                "articles_processed": response["articles_processed"],
                "clusters_found": response["clusters_found"],
                "synthesis_length": len(result.content),
                "confidence": result.confidence,
                "gpu_used": response["gpu_used"],
                "articles_per_sec": articles_per_sec,
                "processing_time": processing_time,
                "context": context,
            },
        )

        # Add performance metrics to response
        response["performance"] = {
            "articles_per_sec": articles_per_sec,
            "gpu_used": response["gpu_used"],
            "processing_time": processing_time,
        }

        return response

    except Exception as e:
        logger.error(f"❌ GPU synthesis failed: {e}")
        # Emergency fallback
        combined = " ".join(
            [
                article.get("content", "")
                for article in articles[:3]
                if isinstance(article, dict)
            ]
        )
        return {
            "success": False,
            "synthesis": combined,
            "method": "emergency_fallback",
            "articles_processed": len(articles),
            "error": str(e),
            "processing_time": time.time() - start_time,
        }


def synthesize_content(
    engine: SynthesizerEngine,
    articles: list[dict[str, Any]],
    max_clusters: int = 5,
    context: str = "news analysis",
) -> Any:
    """Backward compatible wrapper that drives the async synthesis pipeline."""

    async def _run():
        return await synthesize_gpu_tool(
            engine, articles, max_clusters=max_clusters, context=context
        )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_run())

    if loop.is_running():
        return loop.create_task(_run())

    # If the loop exists but isn't running, prefer asyncio.run which manages lifecycle
    # and is the modern recommended API. This avoids calling run_until_complete on a
    # potentially non-running loop object.
    return asyncio.run(_run())


async def health_check(engine: SynthesizerEngine) -> dict[str, Any]:
    """
    Perform comprehensive health check on synthesizer components.

    Args:
        engine: SynthesizerEngine instance

    Returns:
        Health check results
    """
    logger.info("🏥 Performing Synthesizer health check")

    try:
        health_status = {
            "timestamp": time.time(),
            "overall_status": "healthy",
            "components": {},
            "issues": [],
        }

        # Check model status
        model_status = engine.get_model_status()

        health_status["components"]["bertopic_model"] = {
            "status": "healthy" if model_status.get("bertopic", False) else "unhealthy",
            "loaded": model_status.get("bertopic", False),
        }

        health_status["components"]["bart_model"] = {
            "status": "healthy" if model_status.get("bart", False) else "unhealthy",
            "loaded": model_status.get("bart", False),
        }

        health_status["components"]["flan_t5_model"] = {
            "status": "healthy" if model_status.get("flan_t5", False) else "unhealthy",
            "loaded": model_status.get("flan_t5", False),
        }

        health_status["components"]["embedding_model"] = {
            "status": "healthy"
            if model_status.get("embeddings", False)
            else "unhealthy",
            "loaded": model_status.get("embeddings", False),
        }

        health_status["components"]["gpu_allocation"] = {
            "status": "healthy"
            if model_status.get("gpu_allocated", False)
            else "degraded",
            "allocated": model_status.get("gpu_allocated", False),
        }

        # Get processing stats
        stats = engine.get_processing_stats()
        health_status["components"]["processing_stats"] = {
            "status": "healthy",
            "total_processed": stats.get("total_processed", 0),
            "avg_processing_time": stats.get("avg_processing_time", 0.0),
        }

        # Determine overall status
        unhealthy_components = [
            k
            for k, v in health_status["components"].items()
            if v["status"] == "unhealthy"
        ]
        if unhealthy_components:
            health_status["overall_status"] = "unhealthy"
            health_status["issues"] = [
                f"Component {comp} is unhealthy" for comp in unhealthy_components
            ]

        degraded_components = [
            k
            for k, v in health_status["components"].items()
            if v["status"] == "degraded"
        ]
        if degraded_components and health_status["overall_status"] == "healthy":
            health_status["overall_status"] = "degraded"
            health_status["issues"] = [
                f"Component {comp} is degraded" for comp in degraded_components
            ]

        # Add model counts
        health_status["model_count"] = model_status.get("total_models", 0)
        health_status["gpu_available"] = model_status.get("gpu_allocated", False)

        logger.info(
            f"🏥 Health check completed: {health_status['overall_status']} ({health_status['model_count']} models)"
        )
        return health_status

    except Exception as e:
        logger.error(f"🏥 Health check failed: {e}")
        return {
            "timestamp": time.time(),
            "overall_status": "unhealthy",
            "error": str(e),
        }


async def get_stats(engine: SynthesizerEngine) -> dict[str, Any]:
    """
    Get comprehensive processing statistics and performance metrics.

    Args:
        engine: SynthesizerEngine instance

    Returns:
        Statistics data
    """
    try:
        stats = engine.get_processing_stats()
        model_status = engine.get_model_status()

        return {
            "total_processed": stats.get("total_processed", 0),
            "gpu_processed": stats.get("gpu_processed", 0),
            "cpu_processed": stats.get("cpu_processed", 0),
            "avg_processing_time": stats.get("avg_processing_time", 0.0),
            "gpu_memory_usage_gb": stats.get("gpu_memory_usage_gb", 0.0),
            "model_status": model_status,
            "gpu_available": model_status.get("gpu_allocated", False),
            "models_loaded": model_status.get("total_models", 0),
            "last_performance_check": stats.get("last_performance_check").isoformat()
            if stats.get("last_performance_check")
            else None,
        }

    except Exception as e:
        logger.error(f"❌ Stats retrieval failed: {e}")
        return {
            "total_processed": 0,
            "gpu_processed": 0,
            "cpu_processed": 0,
            "avg_processing_time": 0.0,
            "gpu_memory_usage_gb": 0.0,
            "error": str(e),
        }


def validate_clustering_request(
    article_texts: list[str], n_clusters: int
) -> tuple[bool, str]:
    """
    Validate clustering request parameters.

    Args:
        article_texts: List of article texts
        n_clusters: Number of clusters

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        if not article_texts:
            return False, "Article texts list cannot be empty"

        if not isinstance(article_texts, list):
            return False, "Article texts must be a list"

        if len(article_texts) == 0:
            return False, "At least one article text is required"

        if n_clusters < 1:
            return False, "Number of clusters must be at least 1"

        if n_clusters > len(article_texts):
            return (
                False,
                f"Cannot create {n_clusters} clusters from {len(article_texts)} articles",
            )

        # Check for empty texts
        empty_texts = sum(1 for text in article_texts if not text or not text.strip())
        if empty_texts > 0:
            return (
                False,
                f"{empty_texts} article(s) have empty or whitespace-only content",
            )

        return True, ""

    except Exception as e:
        return False, f"Validation error: {e}"


def validate_synthesis_request(articles: list[dict[str, Any]]) -> tuple[bool, str]:
    """
    Validate synthesis request parameters.

    Args:
        articles: List of article dictionaries

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        if not articles:
            return False, "Articles list cannot be empty"

        if not isinstance(articles, list):
            return False, "Articles must be a list"

        if len(articles) == 0:
            return False, "At least one article is required"

        # Check article structure
        invalid_articles = 0
        for i, article in enumerate(articles):
            if not isinstance(article, dict):
                return False, f"Article at index {i} is not a dictionary"

            content = article.get("content", "")
            if not content or not content.strip():
                invalid_articles += 1

        if invalid_articles > 0:
            return False, f"{invalid_articles} article(s) have empty or missing content"

        return True, ""

    except Exception as e:
        return False, f"Validation error: {e}"


def format_clustering_result(result: dict[str, Any], format_type: str = "json") -> str:
    """
    Format clustering result for output.

    Args:
        result: Clustering result to format
        format_type: Output format ("json", "text", "markdown")

    Returns:
        Formatted output string
    """
    import json

    try:
        if format_type == "json":
            return json.dumps(result, indent=2, default=str)

        elif format_type == "text":
            lines = [
                f"Success: {result.get('success', False)}",
                f"Clusters: {result.get('n_clusters', 0)}",
                f"Articles Processed: {result.get('articles_processed', 0)}",
                f"Method: {result.get('method', 'unknown')}",
                f"Model: {result.get('model_used', 'unknown')}",
                f"Confidence: {result.get('confidence', 0.0):.2f}",
                f"Processing Time: {result.get('processing_time', 0.0):.2f}s",
                "",
                "Clusters:",
            ]

            clusters = result.get("clusters", [])
            for i, cluster in enumerate(clusters):
                lines.append(
                    f"  Cluster {i}: {len(cluster)} articles (indices: {cluster})"
                )

            return "\n".join(lines)

        elif format_type == "markdown":
            success_emoji = "✅" if result.get("success", False) else "❌"
            lines = [
                f"# Clustering Result {success_emoji}",
                "",
                f"**Clusters:** {result.get('n_clusters', 0)}",
                f"**Articles Processed:** {result.get('articles_processed', 0)}",
                f"**Method:** {result.get('method', 'unknown')}",
                f"**Model:** {result.get('model_used', 'unknown')}",
                f"**Confidence:** {result.get('confidence', 0.0):.2f}",
                f"**Processing Time:** {result.get('processing_time', 0.0):.2f}s",
                "",
                "## Cluster Details",
            ]

            clusters = result.get("clusters", [])
            for i, cluster in enumerate(clusters):
                lines.append(
                    f"- **Cluster {i}:** {len(cluster)} articles (indices: {cluster})"
                )

            return "\n".join(lines)

        else:
            return f"Unsupported format: {format_type}"

    except Exception as e:
        return f"Formatting error: {e}"


def format_synthesis_result(result: dict[str, Any], format_type: str = "json") -> str:
    """
    Format synthesis result for output.

    Args:
        result: Synthesis result to format
        format_type: Output format ("json", "text", "markdown")

    Returns:
        Formatted output string
    """
    import json

    try:
        if format_type == "json":
            return json.dumps(result, indent=2, default=str)

        elif format_type == "text":
            lines = [
                f"Success: {result.get('success', False)}",
                f"Articles Processed: {result.get('articles_processed', 0)}",
                f"Clusters Found: {result.get('clusters_found', 0)}",
                f"GPU Used: {result.get('gpu_used', False)}",
                f"Method: {result.get('method', 'unknown')}",
                f"Model: {result.get('model_used', 'unknown')}",
                f"Confidence: {result.get('confidence', 0.0):.2f}",
                f"Processing Time: {result.get('processing_time', 0.0):.2f}s",
                "",
                "Synthesis:",
            ]

            synthesis = result.get("synthesis", "")
            if len(synthesis) > 500:
                lines.append(synthesis[:500] + "...")
            else:
                lines.append(synthesis)

            return "\n".join(lines)

        elif format_type == "markdown":
            success_emoji = "✅" if result.get("success", False) else "❌"
            gpu_emoji = "🚀" if result.get("gpu_used", False) else "💻"

            lines = [
                f"# Synthesis Result {success_emoji} {gpu_emoji}",
                "",
                f"**Articles Processed:** {result.get('articles_processed', 0)}",
                f"**Clusters Found:** {result.get('clusters_found', 0)}",
                f"**GPU Used:** {result.get('gpu_used', False)}",
                f"**Method:** {result.get('method', 'unknown')}",
                f"**Model:** {result.get('model_used', 'unknown')}",
                f"**Confidence:** {result.get('confidence', 0.0):.2f}",
                f"**Processing Time:** {result.get('processing_time', 0.0):.2f}s",
                "",
                "## Synthesized Content",
            ]

            synthesis = result.get("synthesis", "")
            if synthesis:
                lines.extend(["", "```", synthesis, "```"])
            else:
                lines.append("*No synthesis generated*")

            return "\n".join(lines)

        else:
            return f"Unsupported format: {format_type}"

    except Exception as e:
        return f"Formatting error: {e}"


# Export main functions
__all__ = [
    "cluster_articles_tool",
    "neutralize_text_tool",
    "aggregate_cluster_tool",
    "synthesize_gpu_tool",
    "synthesize_content",
    "health_check",
    "get_stats",
    "validate_clustering_request",
    "validate_synthesis_request",
    "format_clustering_result",
    "format_synthesis_result",
]
