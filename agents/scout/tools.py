"""
Scout Tools - Utility Functions for Web Crawling and Analysis

This module provides utility functions for the Scout agent, including
source discovery, web crawling, sentiment analysis, and bias detection.

Key Functions:
- discover_sources_tool: Discover news sources
- crawl_url_tool: Crawl specific URLs
- deep_crawl_tool: Perform deep site crawling
- analyze_sentiment_tool: AI-powered sentiment analysis
- detect_bias_tool: AI-powered bias detection
- health_check: System health monitoring
- get_stats: Performance statistics

All functions include robust error handling and fallbacks.
"""

import time
from typing import Any

from common.observability import get_logger

from .scout_engine import CrawlMode, ScoutEngine

logger = get_logger(__name__)


async def discover_sources_tool(
    engine: ScoutEngine,
    domains: list[str] | None = None,
    max_sources: int = 10,
    include_social: bool = True,
) -> dict[str, Any]:
    """
    Discover news sources using intelligent algorithms.

    Args:
        engine: ScoutEngine instance
        domains: Specific domains to search
        max_sources: Maximum sources to discover
        include_social: Include social media sources

    Returns:
        Discovery results
    """
    logger.info(f"🔍 Discovering sources: domains={domains}, max_sources={max_sources}")

    # start_time is outside the try/except so we can compute elapsed on exception paths as well
    start_time = time.time()
    try:
        # Discover sources
        sources = await engine.discover_sources(domains, max_sources)

        processing_time = time.time() - start_time

        return {
            "success": True,
            "sources": sources,
            "total_found": len(sources),
            "processing_time": processing_time,
            "include_social": include_social,
        }

    except Exception as e:
        logger.error(f"❌ Source discovery failed: {e}")
        return {
            "success": False,
            "sources": [],
            "total_found": 0,
            "error": str(e),
            "processing_time": time.time() - start_time,
        }


async def crawl_url_tool(
    engine: ScoutEngine,
    url: str,
    mode: CrawlMode = CrawlMode.STANDARD,
    max_depth: int = 2,
    follow_external: bool = False,
) -> dict[str, Any]:
    """
    Crawl a specific URL for content extraction.

    Args:
        engine: ScoutEngine instance
        url: URL to crawl
        mode: Crawling mode
        max_depth: Maximum crawl depth
        follow_external: Follow external links

    Returns:
        Crawling results
    """
    logger.info(f"🕷️ Crawling URL: {url} (mode: {mode.value})")

    try:
        # Crawl the URL
        result = await engine.crawl_url(url, mode)

        return {
            "success": result.success,
            "url": result.url,
            "content_type": "webpage",
            "extracted_text": result.content,
            "title": result.title,
            "links_found": result.links,
            "processing_time": result.processing_time,
            "metadata": result.metadata,
        }

    except Exception as e:
        logger.error(f"❌ URL crawling failed: {e}")
        return {"success": False, "url": url, "error": str(e), "processing_time": 0.0}


async def deep_crawl_tool(
    engine: ScoutEngine,
    site_url: str,
    max_pages: int = 50,
    concurrent_requests: int = 5,
) -> dict[str, Any]:
    """
    Perform deep crawling of a website.

    Args:
        engine: ScoutEngine instance
        site_url: Site URL to crawl
        max_pages: Maximum pages to crawl
        concurrent_requests: Concurrent request limit

    Returns:
        Deep crawl results
    """
    logger.info(f"🔬 Deep crawling site: {site_url} (max_pages: {max_pages})")

    # start_time is outside the try/except to compute elapsed time on failure paths
    start_time = time.time()
    try:
        # Perform deep crawl
        result = await engine.deep_crawl_site(site_url, max_pages)

        processing_time = time.time() - start_time

        return {
            "success": result.get("success", False),
            "site_url": site_url,
            "pages_crawled": result.get("pages_crawled", 0),
            "articles_found": result.get("articles_found", []),
            "processing_time": processing_time,
        }

    except Exception as e:
        logger.error(f"❌ Deep crawl failed: {e}")
        return {
            "success": False,
            "site_url": site_url,
            "pages_crawled": 0,
            "articles_found": [],
            "error": str(e),
            "processing_time": time.time() - start_time,
        }


async def analyze_sentiment_tool(
    engine: ScoutEngine, text: str, include_confidence: bool = True
) -> dict[str, Any]:
    """
    Analyze sentiment in text using AI models.

    Args:
        engine: ScoutEngine instance
        text: Text to analyze
        include_confidence: Include confidence scores

    Returns:
        Sentiment analysis results
    """
    logger.info(f"😊 Analyzing sentiment for text ({len(text)} chars)")

    try:
        # Analyze sentiment
        result = await engine.analyze_sentiment(text)

        response = {
            "success": True,
            "sentiment": result.result,
            "confidence": result.confidence if include_confidence else None,
            "model_used": result.model_used,
            "processing_time": result.processing_time,
        }

        # Add detailed scores if available
        if hasattr(result, "detailed_scores"):
            response["scores"] = result.detailed_scores
        else:
            # Create basic scores structure
            response["scores"] = {
                result.result: result.confidence,
                "neutral": 1.0 - result.confidence
                if result.result != "neutral"
                else result.confidence,
            }

        return response

    except Exception as e:
        logger.error(f"❌ Sentiment analysis failed: {e}")
        return {
            "success": False,
            "sentiment": "neutral",
            "confidence": 0.0,
            "error": str(e),
        }


async def detect_bias_tool(
    engine: ScoutEngine, text: str, include_explanation: bool = True
) -> dict[str, Any]:
    """
    Detect bias in text using AI models.

    Args:
        engine: ScoutEngine instance
        text: Text to analyze
        include_explanation: Include bias explanation

    Returns:
        Bias detection results
    """
    logger.info(f"⚖️ Detecting bias for text ({len(text)} chars)")

    try:
        # Detect bias
        result = await engine.detect_bias(text)

        response = {
            "success": True,
            "bias_score": result.result.get("bias_score", 0.0),
            "bias_type": result.result.get("bias_type", "unknown"),
            "model_used": result.model_used,
            "processing_time": result.processing_time,
        }

        # Add explanation if requested
        if include_explanation:
            response["explanation"] = generate_bias_explanation(
                response["bias_score"], response["bias_type"]
            )

        return response

    except Exception as e:
        logger.error(f"❌ Bias detection failed: {e}")
        return {
            "success": False,
            "bias_score": 0.0,
            "bias_type": "unknown",
            "error": str(e),
        }


def generate_bias_explanation(bias_score: float, bias_type: str) -> str:
    """
    Generate human-readable explanation for bias detection results.

    Args:
        bias_score: Bias score (0.0-1.0)
        bias_type: Type of bias detected

    Returns:
        Explanation string
    """
    if bias_score < 0.3:
        return "Text appears to be relatively neutral with minimal detectable bias."
    elif bias_score < 0.6:
        return f"Text shows moderate {bias_type} bias. Consider reviewing multiple sources for balance."
    else:
        return f"Text exhibits strong {bias_type} bias. This content may present information in a one-sided manner."


async def health_check(engine: ScoutEngine) -> dict[str, Any]:
    """
    Perform health check on Scout components.

    Args:
        engine: ScoutEngine instance

    Returns:
        Health check results
    """
    logger.info("🏥 Performing Scout health check")

    try:
        health_status = {
            "timestamp": time.time(),
            "overall_status": "healthy",
            "components": {},
            "issues": [],
        }

        # Check AI models
        model_info = engine.get_model_info()

        health_status["components"]["sentiment_model"] = {
            "status": "healthy"
            if model_info.get("sentiment_model", {}).get("loaded", False)
            else "unhealthy",
            "loaded": model_info.get("sentiment_model", {}).get("loaded", False),
        }

        health_status["components"]["bias_model"] = {
            "status": "healthy"
            if model_info.get("bias_model", {}).get("loaded", False)
            else "unhealthy",
            "loaded": model_info.get("bias_model", {}).get("loaded", False),
        }

        health_status["components"]["crawl4ai"] = {
            "status": "healthy"
            if model_info.get("crawl4ai_available", False)
            else "degraded",
            "available": model_info.get("crawl4ai_available", False),
        }

        # Check processing stats
        stats = engine.get_processing_stats()
        health_status["components"]["processing_stats"] = {
            "status": "healthy",
            "total_crawled": stats.get("total_crawled", 0),
            "total_analyzed": stats.get("total_analyzed", 0),
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

        logger.info(f"🏥 Health check completed: {health_status['overall_status']}")
        return health_status

    except Exception as e:
        logger.error(f"🏥 Health check failed: {e}")
        return {
            "timestamp": time.time(),
            "overall_status": "unhealthy",
            "error": str(e),
        }


async def get_stats(engine: ScoutEngine) -> dict[str, Any]:
    """
    Get processing statistics and performance metrics.

    Args:
        engine: ScoutEngine instance

    Returns:
        Statistics data
    """
    try:
        stats = engine.get_processing_stats()

        return {
            "total_crawled": stats.get("total_crawled", 0),
            "total_discovered": 0,  # Would need to track this separately
            "success_rate": stats.get("success_rate", 0.0),
            "average_processing_time": stats.get("average_crawl_time", 0.0)
            + stats.get("average_analysis_time", 0.0),
            "model_info": engine.get_model_info(),
        }

    except Exception as e:
        logger.error(f"❌ Stats retrieval failed: {e}")
        return {
            "total_crawled": 0,
            "total_discovered": 0,
            "success_rate": 0.0,
            "average_processing_time": 0.0,
            "error": str(e),
        }


def validate_crawl_request(url: str, mode: str) -> tuple[bool, str]:
    """
    Validate crawl request parameters.

    Args:
        url: URL to validate
        mode: Crawl mode to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Validate URL
        if not url or not isinstance(url, str):
            return False, "URL must be a non-empty string"

        if not url.startswith(("http://", "https://")):
            return False, "URL must start with http:// or https://"

        # Validate mode
        valid_modes = [m.value for m in CrawlMode]
        if mode not in valid_modes:
            return False, f"Invalid mode. Must be one of: {', '.join(valid_modes)}"

        return True, ""

    except Exception as e:
        return False, f"Validation error: {e}"


def validate_analysis_request(text: str) -> tuple[bool, str]:
    """
    Validate analysis request parameters.

    Args:
        text: Text to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        if not text or not isinstance(text, str):
            return False, "Text must be a non-empty string"

        if len(text.strip()) == 0:
            return False, "Text cannot be empty or whitespace only"

        if len(text) > 10000:  # Reasonable limit
            return False, "Text is too long (max 10,000 characters)"

        return True, ""

    except Exception as e:
        return False, f"Validation error: {e}"


def format_crawl_result(result: dict[str, Any], format_type: str = "json") -> str:
    """
    Format crawl result for output.

    Args:
        result: Crawl result to format
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
                f"URL: {result.get('url', 'N/A')}",
                f"Success: {result.get('success', False)}",
                f"Title: {result.get('title', 'N/A')}",
                f"Content Length: {len(result.get('extracted_text', ''))}",
                f"Links Found: {len(result.get('links_found', []))}",
                f"Processing Time: {result.get('processing_time', 0.0):.2f}s",
                "",
                "Content Preview:",
                result.get("extracted_text", "N/A")[:500] + "..."
                if len(result.get("extracted_text", "")) > 500
                else result.get("extracted_text", "N/A"),
            ]
            return "\n".join(lines)

        elif format_type == "markdown":
            success_emoji = "✅" if result.get("success", False) else "❌"
            lines = [
                f"# Crawl Result {success_emoji}",
                "",
                f"**URL:** {result.get('url', 'N/A')}",
                f"**Title:** {result.get('title', 'N/A')}",
                f"**Content Length:** {len(result.get('extracted_text', ''))}",
                f"**Links Found:** {len(result.get('links_found', []))}",
                f"**Processing Time:** {result.get('processing_time', 0.0):.2f}s",
                "",
                "## Content Preview",
                "```",
                result.get("extracted_text", "N/A")[:1000] + "..."
                if len(result.get("extracted_text", "")) > 1000
                else result.get("extracted_text", "N/A"),
                "```",
            ]
            return "\n".join(lines)

        else:
            return f"Unsupported format: {format_type}"

    except Exception as e:
        return f"Formatting error: {e}"


def format_analysis_result(result: dict[str, Any], format_type: str = "json") -> str:
    """
    Format analysis result for output.

    Args:
        result: Analysis result to format
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
                f"Result: {result.get('sentiment', result.get('bias_type', 'N/A'))}",
                f"Confidence: {result.get('confidence', result.get('bias_score', 0.0)):.2f}",
                f"Model: {result.get('model_used', 'N/A')}",
                f"Processing Time: {result.get('processing_time', 0.0):.2f}s",
            ]

            if "explanation" in result:
                lines.extend(["", "Explanation:", result["explanation"]])

            return "\n".join(lines)

        elif format_type == "markdown":
            success_emoji = "✅" if result.get("success", False) else "❌"
            result_value = result.get("sentiment", result.get("bias_type", "N/A"))
            confidence_value = result.get("confidence", result.get("bias_score", 0.0))

            lines = [
                f"# Analysis Result {success_emoji}",
                "",
                f"**Result:** {result_value}",
                f"**Confidence:** {confidence_value:.2f}",
                f"**Model:** {result.get('model_used', 'N/A')}",
                f"**Processing Time:** {result.get('processing_time', 0.0):.2f}s",
            ]

            if "explanation" in result:
                lines.extend(["", "## Explanation", result["explanation"]])

            return "\n".join(lines)

        else:
            return f"Unsupported format: {format_type}"

    except Exception as e:
        return f"Formatting error: {e}"


# Export main functions
__all__ = [
    "discover_sources_tool",
    "crawl_url_tool",
    "deep_crawl_tool",
    "analyze_sentiment_tool",
    "detect_bias_tool",
    "health_check",
    "get_stats",
    "validate_crawl_request",
    "validate_analysis_request",
    "format_crawl_result",
    "format_analysis_result",
]
