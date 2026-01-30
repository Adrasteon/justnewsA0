"""
Fact Checker Tools - Utility Functions for Fact Verification

This module provides utility functions for fact verification and source credibility assessment,
focusing on claim validation, evidence evaluation, and source reliability analysis.

Key Functions:
- verify_facts: Primary fact verification using AI models
- validate_sources: Source credibility assessment
- comprehensive_fact_check: Full article fact-checking
- extract_claims: Extract verifiable claims from text
- assess_credibility: Evaluate source reliability
- detect_contradictions: Identify logical inconsistencies

All functions include robust error handling, validation, and fallbacks.
"""

import asyncio
import json
from datetime import datetime
from time import perf_counter
from typing import Any

from common.observability import get_logger

from .fact_checker_engine import FactCheckerConfig, FactCheckerEngine

# Configure logging
logger = get_logger(__name__)

# Global engine instance
_engine: Any | None = None

# Operation aliases expected by tests/legacy code
_OPERATION_ALIASES = {
    "verify": "verify_facts",
    "verify_facts": "verify_facts",
    "validate": "validate_sources",
    "validate_sources": "validate_sources",
    "comprehensive": "comprehensive_fact_check",
    "comprehensive_fact_check": "comprehensive_fact_check",
    "extract": "extract_claims",
    "extract_claims": "extract_claims",
    "assess": "assess_credibility",
    "assess_credibility": "assess_credibility",
    "detect": "detect_contradictions",
    "detect_contradictions": "detect_contradictions",
}

_SUPPORTED_TYPES = sorted(set(_OPERATION_ALIASES.values()))


def get_fact_checker_engine():
    """Get or create the global fact checker engine instance."""
    global _engine
    if _engine is None:
        config = FactCheckerConfig()
        _engine = FactCheckerEngine(config)
    return _engine


async def process_fact_check_request(
    content: str, operation_type: str, **kwargs
) -> dict[str, Any]:
    """Process a fact-checking request using the engine."""
    engine = get_fact_checker_engine()
    normalized = _OPERATION_ALIASES.get(operation_type, operation_type)

    if normalized not in _SUPPORTED_TYPES:
        logger.warning("Unknown fact-check operation '%s'", operation_type)
        return {
            "error": f"Unknown operation type: {operation_type}",
            "supported_types": _SUPPORTED_TYPES,
        }

    logger.info(
        "🔍 Processing %s fact-checking operation for %s characters",
        normalized,
        len(content) if content is not None else 0,
    )

    try:
        if normalized == "verify_facts":
            call_kwargs = {}
            if kwargs.get("source_url") is not None:
                call_kwargs["source_url"] = kwargs["source_url"]
            if kwargs.get("context") is not None:
                call_kwargs["context"] = kwargs["context"]
            result = await engine.verify_facts(content, **call_kwargs)
        elif normalized == "validate_sources":
            call_kwargs = {}
            if kwargs.get("source_url") is not None:
                call_kwargs["source_url"] = kwargs["source_url"]
            if kwargs.get("domain") is not None:
                call_kwargs["domain"] = kwargs["domain"]
            if kwargs.get("sources") is not None:
                call_kwargs["sources"] = kwargs["sources"]
            result = engine.validate_sources(content, **call_kwargs)
        elif normalized == "comprehensive_fact_check":
            call_kwargs = {}
            if kwargs.get("source_url") is not None:
                call_kwargs["source_url"] = kwargs["source_url"]
            if kwargs.get("context") is not None:
                call_kwargs["context"] = kwargs["context"]
            if kwargs.get("metadata") is not None:
                call_kwargs["metadata"] = kwargs["metadata"]
            result = await engine.comprehensive_fact_check(content, **call_kwargs)
        elif normalized == "extract_claims":
            result = engine.extract_claims(content)
        elif normalized == "assess_credibility":
            call_kwargs = {}
            if kwargs.get("domain") is not None:
                call_kwargs["domain"] = kwargs["domain"]
            if kwargs.get("source_url") is not None:
                call_kwargs["source_url"] = kwargs["source_url"]
            result = engine.assess_credibility(content, **call_kwargs)
        elif normalized == "detect_contradictions":
            passages = kwargs.get("text_passages") or kwargs.get("passages") or []
            result = engine.detect_contradictions(passages)
        else:  # pragma: no cover - safeguard
            result = {"error": f"Operation '{normalized}' not implemented"}

        logger.info("✅ %s fact-checking operation completed", normalized)
        return result

    except Exception as exc:  # noqa: BLE001
        logger.error("❌ %s fact-checking operation failed: %s", normalized, exc)
        return {"error": str(exc), "details": str(exc)}


def _await_if_needed(result: Any) -> Any:
    """Return coroutine result synchronously if required."""
    if asyncio.iscoroutine(result):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(result)
        else:
            # We're inside a running event loop — we cannot block the loop. Instead
            # schedule the coroutine as a Task and return it; callers executing in
            # an async context can await the returned Task, while sync contexts
            # will not hit this branch (they'll use the asyncio.run path above).
            future = asyncio.ensure_future(result, loop=loop)
            return future  # pragma: no cover
    return result


def verify_facts(
    content: str, source_url: str | None = None, context: str | None = None
) -> dict[str, Any]:
    call_kwargs: dict[str, Any] = {"operation_type": "verify_facts", "content": content}
    if source_url is not None:
        call_kwargs["source_url"] = source_url
    if context is not None:
        call_kwargs["context"] = context
    response = _await_if_needed(process_fact_check_request(**call_kwargs))
    return response or {}


def validate_sources(
    content: str,
    sources: list[str] | None = None,
    domain: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    call_kwargs: dict[str, Any] = {
        "operation_type": "validate_sources",
        "content": content,
    }
    if sources is not None:
        call_kwargs["sources"] = sources
    if domain is not None:
        call_kwargs["domain"] = domain
    if source_url is not None:
        call_kwargs["source_url"] = source_url
    response = _await_if_needed(process_fact_check_request(**call_kwargs))
    return response or {}


def comprehensive_fact_check(
    content: str,
    source_url: str | None = None,
    context: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    call_kwargs: dict[str, Any] = {
        "operation_type": "comprehensive_fact_check",
        "content": content,
    }
    if source_url is not None:
        call_kwargs["source_url"] = source_url
    if context is not None:
        call_kwargs["context"] = context
    if metadata is not None:
        call_kwargs["metadata"] = metadata
    response = _await_if_needed(process_fact_check_request(**call_kwargs))
    return response or {}


def extract_claims(content: str) -> list[str]:
    response = _await_if_needed(
        process_fact_check_request(
            content=content,
            operation_type="extract_claims",
        )
    )
    if isinstance(response, dict):
        claims = response.get("claims", [])
        return claims if isinstance(claims, list) else []
    if isinstance(response, list):
        return response
    return []


def assess_credibility(
    content: str | None = None,
    domain: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    call_kwargs: dict[str, Any] = {
        "operation_type": "assess_credibility",
        "content": content or "",
    }
    if domain is not None:
        call_kwargs["domain"] = domain
    if source_url is not None:
        call_kwargs["source_url"] = source_url
    response = _await_if_needed(process_fact_check_request(**call_kwargs))
    return response or {}


def detect_contradictions(text_passages: list[str]) -> dict[str, Any]:
    response = _await_if_needed(
        process_fact_check_request(
            content="\n".join(text_passages or []),
            operation_type="detect_contradictions",
            text_passages=text_passages,
        )
    )
    return response or {}


# GPU-accelerated functions with CPU fallbacks
async def validate_is_news_gpu(content: str) -> dict[str, Any]:
    """
    GPU-accelerated news content validation.

    Determines if content qualifies as legitimate news reporting using AI models.
    """
    try:
        engine = get_fact_checker_engine()
        return await engine.validate_is_news_gpu(content)
    except Exception as e:
        logger.warning(f"GPU news validation failed, falling back to CPU: {e}")
        return await validate_is_news_cpu(content)


async def validate_is_news_cpu(content: str) -> dict[str, Any]:
    """
    CPU-based news content validation fallback.

    Basic heuristic-based news validation when GPU is unavailable.
    """
    try:
        start_time = perf_counter()
        # Simple heuristic-based validation
        content_lower = content.lower()

        # News indicators
        news_keywords = [
            "breaking",
            "report",
            "headline",
            "news",
            "announced",
            "according to",
        ]
        news_score = sum(
            1 for keyword in news_keywords if keyword in content_lower
        ) / len(news_keywords)

        # Structure indicators
        has_structure = any(
            indicator in content for indicator in [" - ", " | ", "\n\n"]
        )

        # Length indicator (news articles are typically substantial)
        length_score = min(1.0, len(content) / 1000.0)

        # Combined score
        is_news_score = news_score * 0.5 + has_structure * 0.3 + length_score * 0.2

        processing_time = perf_counter() - start_time
        return {
            "is_news": is_news_score > 0.4,
            "confidence": is_news_score,
            "news_score": news_score,
            "structure_score": has_structure,
            "length_score": length_score,
            "method": "cpu_fallback",
            "analysis_timestamp": datetime.now().isoformat(),
            "processing_time": processing_time,
        }

    except Exception as e:
        logger.error(f"CPU news validation failed: {e}")
        return {"error": str(e), "is_news": False, "method": "cpu_fallback"}


async def verify_claims_gpu(claims: list[str], sources: list[str]) -> dict[str, Any]:
    """
    GPU-accelerated claim verification for multiple claims.
    """
    try:
        engine = get_fact_checker_engine()
        return await engine.verify_claims_gpu(claims, sources)
    except Exception as e:
        logger.warning(f"GPU claims verification failed, falling back to CPU: {e}")
        return await verify_claims_cpu(claims, sources)


async def verify_claims_cpu(claims: list[str], sources: list[str]) -> dict[str, Any]:
    """
    CPU-based claim verification fallback.
    """
    try:
        start_time = perf_counter()
        results = {}
        source_text = "\n".join(sources) if sources else ""

        for claim in claims:
            # Simple verification based on source matching
            verification_score = 0.5

            if source_text:
                # Check if claim elements appear in sources
                claim_words = set(claim.lower().split())
                source_words = set(source_text.lower().split())
                overlap = len(claim_words.intersection(source_words))
                verification_score = min(1.0, overlap / len(claim_words) * 2)

            results[claim] = {
                "verification_score": verification_score,
                "classification": "verified"
                if verification_score > 0.6
                else "questionable",
                "confidence": verification_score,
                "method": "cpu_fallback",
            }

        return {
            "results": results,
            "total_claims": len(claims),
            "verified_claims": sum(
                1 for r in results.values() if r["classification"] == "verified"
            ),
            "method": "cpu_fallback",
            "analysis_timestamp": datetime.now().isoformat(),
            "processing_time": perf_counter() - start_time,
        }

    except Exception as e:
        logger.error(f"CPU claims verification failed: {e}")
        return {"error": str(e), "method": "cpu_fallback"}


# Utility functions
def get_performance_stats() -> dict[str, Any]:
    """Get GPU acceleration performance statistics."""
    try:
        engine = get_fact_checker_engine()
        return engine.get_performance_stats()
    except Exception as e:
        logger.error(f"Error getting performance stats: {e}")
        return {"error": str(e), "gpu_available": False}


def get_model_status() -> dict[str, Any]:
    """Get status of all fact-checking models."""
    try:
        engine = get_fact_checker_engine()
        return engine.get_model_status()
    except Exception as e:
        logger.error(f"Error getting model status: {e}")
        return {"error": str(e), "models_loaded": False}


def log_feedback(feedback_data: dict[str, Any]) -> dict[str, Any]:
    """Log user feedback for model improvement."""
    try:
        engine = get_fact_checker_engine()
        return engine.log_feedback(feedback_data)
    except Exception as e:
        logger.error(f"Error logging feedback: {e}")
        return {"error": str(e), "logged": False}


def correct_verification(
    claim: str,
    context: str | None = None,
    incorrect_classification: str = "",
    correct_classification: str = "",
    priority: int = 2,
) -> dict[str, Any]:
    """Submit user correction for fact verification."""
    try:
        engine = get_fact_checker_engine()
        return engine.correct_verification(
            claim, context, incorrect_classification, correct_classification, priority
        )
    except Exception as e:
        logger.error(f"Error submitting verification correction: {e}")
        return {"error": str(e), "correction_submitted": False}


def correct_credibility(
    source_text: str | None = None,
    domain: str = "",
    incorrect_reliability: str = "",
    correct_reliability: str = "",
    priority: int = 2,
) -> dict[str, Any]:
    """Submit user correction for credibility assessment."""
    try:
        engine = get_fact_checker_engine()
        return engine.correct_credibility(
            source_text, domain, incorrect_reliability, correct_reliability, priority
        )
    except Exception as e:
        logger.error(f"Error submitting credibility correction: {e}")
        return {"error": str(e), "correction_submitted": False}


def get_training_status() -> dict[str, Any]:
    """Get online training status for fact checker models."""
    try:
        engine = get_fact_checker_engine()
        return engine.get_training_status()
    except Exception as e:
        logger.error(f"Error getting training status: {e}")
        return {"error": str(e), "online_training_enabled": False}


def force_model_update() -> dict[str, Any]:
    """Force immediate model update (admin function)."""
    try:
        engine = get_fact_checker_engine()
        return engine.force_model_update()
    except Exception as e:
        logger.error(f"Error forcing model update: {e}")
        return {"error": str(e), "update_triggered": False}


async def health_check() -> dict[str, Any]:
    """
    Perform health check on fact checker components.

    Returns:
        Health check results with component status
    """
    try:
        engine = get_fact_checker_engine()

        model_status = engine.get_model_status()

        health_status = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "components": {
                "engine": "healthy",
                "mcp_bus": "healthy",  # Assume healthy unless proven otherwise
                "fact_checking_models": "healthy",
                "gpu_acceleration": "healthy"
                if model_status.get("gpu_available", False)
                else "degraded",
            },
            "model_status": model_status,
            "processing_stats": getattr(engine, "processing_stats", {}),
        }

        # Check for any unhealthy components
        unhealthy_components = [
            k for k, v in health_status["components"].items() if v == "unhealthy"
        ]
        if unhealthy_components:
            health_status["overall_status"] = "degraded"
            health_status["issues"] = [
                f"Component {comp} is unhealthy" for comp in unhealthy_components
            ]

        # Check model availability
        loaded_models = sum(
            1 for status in model_status.values() if isinstance(status, bool) and status
        )
        if loaded_models < 2:  # Require at least 2 of 4 models for basic functionality
            health_status["overall_status"] = "degraded"
            health_status["issues"] = health_status.get("issues", []) + [
                f"Only {loaded_models}/4 AI models loaded"
            ]

        logger.info(f"🏥 Fact checker health check: {health_status['overall_status']}")
        return health_status

    except Exception as e:
        logger.error(f"🏥 Fact checker health check failed: {e}")
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "unhealthy",
            "error": str(e),
        }


def validate_fact_check_result(
    result: dict[str, Any], expected_fields: list[str] | None = None
) -> bool:
    """
    Validate fact-check result structure.

    Args:
        result: Fact-check result to validate
        expected_fields: List of expected fields (optional)

    Returns:
        True if result is valid, False otherwise
    """
    if not isinstance(result, dict):
        return False

    if "error" in result:
        return True  # Error results are valid

    if expected_fields:
        return all(field in result for field in expected_fields)

    # Basic validation for common fields
    common_fields = ["analysis_metadata", "analysis_timestamp"]
    return any(field in result for field in common_fields)


def format_fact_check_output(result: dict[str, Any], format_type: str = "json") -> str:
    """
    Format fact-check result for output.

    Args:
        result: Fact-check result to format
        format_type: Output format ("json", "text", "markdown")

    Returns:
        Formatted output string
    """
    try:
        if format_type == "json":
            return json.dumps(result, indent=2, default=str)

        elif format_type == "text":
            if "error" in result:
                return f"Error: {result['error']}"

            lines = []
            if "verification_score" in result:
                lines.append(
                    f"Verification Score: {result['verification_score']:.2f}/1.0"
                )
                lines.append(
                    f"Classification: {result.get('classification', 'unknown')}"
                )

            if "credibility_score" in result:
                lines.append(
                    f"Credibility Score: {result['credibility_score']:.2f}/1.0"
                )
                lines.append(f"Reliability: {result.get('reliability', 'unknown')}")

            if "overall_score" in result:
                lines.append(f"Overall Score: {result['overall_score']:.2f}/1.0")
                lines.append(
                    f"Assessment: {result.get('overall_assessment', 'unknown')}"
                )

            if "claim_count" in result:
                lines.append(f"Claims Extracted: {result['claim_count']}")

            if "contradictions_found" in result:
                lines.append(f"Contradictions Found: {result['contradictions_found']}")

            return "\n".join(lines)

        elif format_type == "markdown":
            if "error" in result:
                return f"## Fact Check Error\n\n{result['error']}"

            lines = ["# Fact Check Results\n"]

            if "verification_score" in result:
                lines.append("## Verification Results")
                lines.append(f"- **Score**: {result['verification_score']:.2f}/1.0")
                lines.append(
                    f"- **Classification**: {result.get('classification', 'unknown')}"
                )

            if "credibility_score" in result:
                lines.append("## Source Credibility")
                lines.append(f"- **Score**: {result['credibility_score']:.2f}/1.0")
                lines.append(
                    f"- **Reliability**: {result.get('reliability', 'unknown')}"
                )

            if "overall_score" in result:
                lines.append("## Overall Assessment")
                lines.append(f"- **Score**: {result['overall_score']:.2f}/1.0")
                lines.append(
                    f"- **Assessment**: {result.get('overall_assessment', 'unknown')}"
                )

            if "claims_analysis" in result:
                claims = result["claims_analysis"].get("extracted_claims", [])
                lines.append("## Claims Analysis")
                lines.append(f"- **Total Claims**: {len(claims)}")
                if claims:
                    lines.append("- **Sample Claims**:")
                    for _i, claim in enumerate(claims[:3]):
                        lines.append(
                            f"  - {claim[:100]}{'...' if len(claim) > 100 else ''}"
                        )

            if "contradictions_found" in result and result["contradictions_found"] > 0:
                lines.append("## Contradictions Detected")
                lines.append(
                    f"- **Found**: {result['contradictions_found']} contradictions"
                )

            return "\n".join(lines)

        else:
            return f"Unsupported format: {format_type}"

    except Exception as e:
        return f"Formatting error: {e}"


try:
    from database.utils.migrated_database_utils import create_database_service
except Exception:
    create_database_service = None


async def verify_article_tool(article_id: int) -> dict[str, Any]:
    """
    Verify an article by ID, updating the database with the result.
    
    This is a 'service-level' tool that handles database interaction, intended
    for use by the Workflow Orchestrator.
    
    Args:
        article_id: The ID of the article to verify.
    """
    if create_database_service is None:
        return {"error": "Database service not available", "status": "error"}
    
    try:
        db = create_database_service()
        db.ensure_conn()
        
        # Fetch article
        # using buffered cursor to ensure we read fully
        cursor = db.mb_conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT id, content, source_url as url FROM articles WHERE id = %s", (article_id,))
        article = cursor.fetchone()
        cursor.close()
        
        if not article:
             return {"error": f"Article {article_id} not found", "status": "error"}
             
        # Perform check
        # Convert content to str to be safe
        content = article.get("content") or ""
        url = article.get("url")
        
        # Using comprehensive check
        # Note: comprehensive_fact_check might be async or wrapped sync
        result = comprehensive_fact_check(
            content=content,
            source_url=url
        )
        # In case it returned a coroutine (if called directly vs tool wrapper)
        if asyncio.iscoroutine(result) or asyncio.isfuture(result):
            result = await result
        
        # Update DB
        # We store status and trace
        status = result.get("classification")
        if not status and "fact_verification" in result:
             status = result["fact_verification"].get("classification")
        
        status = status or "unknown"
        
        # Ensure result is serializable
        try:
            trace = json.dumps(result)
        except Exception:
            trace = json.dumps({"error": "Result not serializable", "partial": str(result)[:1000]})
        
        cursor = db.mb_conn.cursor()
        cursor.execute(
            "UPDATE articles SET fact_check_status = %s, fact_check_trace = %s WHERE id = %s",
            (status, trace, article_id)
        )
        db.mb_conn.commit()
        cursor.close()
        
        return {"status": "success", "article_id": article_id, "classification": status}
        
    except Exception as e:
        logger.error(f"verify_article_tool failed for {article_id}: {e}", exc_info=True)
        return {"error": str(e), "status": "error"}


# Export main functions
__all__ = [
    "verify_article_tool",

    "verify_facts",
    "validate_sources",
    "comprehensive_fact_check",
    "extract_claims",
    "assess_credibility",
    "detect_contradictions",
    "validate_is_news_gpu",
    "validate_is_news_cpu",
    "verify_claims_gpu",
    "verify_claims_cpu",
    "get_performance_stats",
    "get_model_status",
    "log_feedback",
    "correct_verification",
    "correct_credibility",
    "get_training_status",
    "force_model_update",
    "health_check",
    "validate_fact_check_result",
    "format_fact_check_output",
    "get_fact_checker_engine",
]
