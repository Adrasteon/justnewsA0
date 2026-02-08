"""
NewsReader Tools - Utility Functions for Content Processing

This module provides utility functions for news content processing, memory monitoring,
and health checks. Simplified for the refactored newsreader agent.

Key Functions:
- process_article_content: Main async processing function
- Memory monitoring and health checks
- Content validation and formatting
"""

import json
import os
import threading
import time
from typing import Any

from common.observability import get_logger

from .newsreader_engine import NewsReaderEngine, ProcessingMode

logger = get_logger(__name__)


class MemoryMonitor:
    """Simple memory monitoring for GPU operations."""

    def __init__(self, check_interval: float = 5.0):
        self.check_interval = check_interval
        self.monitoring = False
        self.thread: threading.Thread | None = None
        self.memory_stats: list[dict[str, Any]] = []

    def start_monitoring(self):
        """Start memory monitoring thread."""
        if self.monitoring:
            return

        self.monitoring = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logger.info("🧠 Memory monitoring started")

    def stop_monitoring(self):
        """Stop memory monitoring."""
        self.monitoring = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        logger.info("🧠 Memory monitoring stopped")

    def _monitor_loop(self):
        """Memory monitoring loop."""
        try:
            while self.monitoring:
                try:
                    self._record_memory_stats()
                except Exception as e:
                    logger.warning(f"Memory monitoring error: {e}")
                time.sleep(self.check_interval)
        except Exception as e:
            logger.error(f"Memory monitoring thread error: {e}")

    def _record_memory_stats(self):
        """Record current memory statistics."""
        try:
            import torch

            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / 1e6
                reserved = torch.cuda.memory_reserved() / 1e6
                free = (
                    torch.cuda.get_device_properties(0).total_memory / 1e6 - allocated
                )

                stats = {
                    "timestamp": time.time(),
                    "allocated_mb": allocated,
                    "reserved_mb": reserved,
                    "free_mb": free,
                    "utilization_percent": (
                        allocated / torch.cuda.get_device_properties(0).total_memory
                    )
                    * 100,
                }

                self.memory_stats.append(stats)

                # Keep only last 100 entries
                if len(self.memory_stats) > 100:
                    self.memory_stats = self.memory_stats[-100:]

        except ImportError:
            pass  # torch not available
        except Exception as e:
            logger.warning(f"Failed to record memory stats: {e}")

    def get_memory_stats(self) -> list[dict[str, Any]]:
        """Get current memory statistics."""
        return self.memory_stats.copy()


# Global memory monitor instance
memory_monitor = MemoryMonitor()


async def process_article_content(
    url: str,
    engine: NewsReaderEngine,
    mode: ProcessingMode = ProcessingMode.COMPREHENSIVE,
    screenshot_path: str | None = None,
    custom_prompt: str | None = None,
) -> dict[str, Any]:
    """
    Process article content from URL using NewsReader engine.

    This is the main processing function that coordinates screenshot capture
    and LLaVA analysis for news content extraction.

    Args:
        url: Article URL to process
        engine: NewsReaderEngine instance
        mode: Processing mode (fast or comprehensive)
        screenshot_path: Optional path for screenshot
        custom_prompt: Optional custom analysis prompt

    Returns:
        Processing results with extracted content
    """
    logger.info(f"🔄 Processing article content: {url}")

    try:
        # Validate inputs
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Invalid URL provided")

        if not url.lower().startswith(("http://", "https://")):
            raise ValueError(f"URL must start with http:// or https://: {url}")

        # Start memory monitoring if not already running
        memory_monitor.start_monitoring()

        # Process with engine
        result = await engine.process_news_url(url, screenshot_path, mode)

        # Format response
        response = {
            "success": result.confidence_score > 0.0,
            "url": url,
            "content_type": result.content_type.value,
            "extracted_text": result.extracted_text,
            "visual_description": result.visual_description,
            "confidence_score": result.confidence_score,
            "processing_time": result.processing_time,
            "model_outputs": result.model_outputs,
            "metadata": result.metadata,
            "timestamp": time.time(),
            "processing_mode": mode.value,
        }

        # Add memory stats if available
        if memory_monitor.memory_stats:
            response["memory_stats"] = memory_monitor.get_memory_stats()[-1]

        logger.info(f"✅ Article processing completed: {result.processing_time:.2f}s")
        return response

    except Exception as e:
        logger.error(f"❌ Article processing failed: {e}")
        return {
            "success": False,
            "url": url,
            "error": str(e),
            "timestamp": time.time(),
            "processing_mode": mode.value,
        }


def validate_processing_result(result: dict[str, Any]) -> tuple[bool, str]:
    """
    Validate processing result structure and content.

    Args:
        result: Processing result to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        required_fields = [
            "success",
            "url",
            "content_type",
            "extracted_text",
            "confidence_score",
        ]

        for field in required_fields:
            if field not in result:
                return False, f"Missing required field: {field}"

        if not isinstance(result["success"], bool):
            return False, "success field must be boolean"

        if not isinstance(result["url"], str) or not result["url"].strip():
            return False, "url field must be non-empty string"

        if not isinstance(result["confidence_score"], (int, float)):
            return False, "confidence_score must be numeric"

        if result["confidence_score"] < 0.0 or result["confidence_score"] > 1.0:
            return False, "confidence_score must be between 0.0 and 1.0"

        return True, ""

    except Exception as e:
        return False, f"Validation error: {e}"


def format_processing_output(result: dict[str, Any], format_type: str = "json") -> str:
    """
    Format processing result for output.

    Args:
        result: Processing result to format
        format_type: Output format ("json", "text", "markdown")

    Returns:
        Formatted output string
    """
    try:
        if format_type == "json":
            return json.dumps(result, indent=2, default=str)

        elif format_type == "text":
            lines = [
                f"URL: {result.get('url', 'N/A')}",
                f"Success: {result.get('success', False)}",
                f"Content Type: {result.get('content_type', 'N/A')}",
                f"Confidence: {result.get('confidence_score', 0.0):.2f}",
                f"Processing Time: {result.get('processing_time', 0.0):.2f}s",
                "",
                "Extracted Text:",
                result.get("extracted_text", "N/A"),
                "",
                "Visual Description:",
                result.get("visual_description", "N/A"),
            ]
            return "\n".join(lines)

        elif format_type == "markdown":
            success_emoji = "✅" if result.get("success", False) else "❌"
            lines = [
                f"# News Article Processing Result {success_emoji}",
                "",
                f"**URL:** {result.get('url', 'N/A')}",
                f"**Content Type:** {result.get('content_type', 'N/A')}",
                f"**Confidence Score:** {result.get('confidence_score', 0.0):.2f}",
                f"**Processing Time:** {result.get('processing_time', 0.0):.2f}s",
                "",
                "## Extracted Text",
                "```",
                result.get("extracted_text", "N/A"),
                "```",
                "",
                "## Visual Description",
                result.get("visual_description", "N/A"),
            ]
            return "\n".join(lines)

        else:
            return f"Unsupported format: {format_type}"

    except Exception as e:
        return f"Formatting error: {e}"


async def health_check(engine: NewsReaderEngine) -> dict[str, Any]:
    """
    Perform health check on NewsReader components.

    Args:
        engine: NewsReaderEngine instance to check

    Returns:
        Health check results
    """
    logger.info("🏥 Performing health check")

    health_status = {
        "timestamp": time.time(),
        "overall_status": "healthy",
        "components": {},
        "issues": [],
    }

    try:
        # Check LLaVA model
        llava_available = engine.is_llava_available()
        health_status["components"]["llava_model"] = {
            "status": "healthy" if llava_available else "unhealthy",
            "available": llava_available,
        }

        if not llava_available:
            health_status["issues"].append("LLaVA model not available")
            health_status["overall_status"] = "degraded"

        # Check screenshot system
        screenshot_available = engine.models.get("screenshot_system") is not None
        health_status["components"]["screenshot_system"] = {
            "status": "healthy" if screenshot_available else "unhealthy",
            "available": screenshot_available,
        }

        if not screenshot_available:
            health_status["issues"].append("Screenshot system not available")
            health_status["overall_status"] = "degraded"

        # Check memory monitor
        memory_stats = memory_monitor.get_memory_stats()
        health_status["components"]["memory_monitor"] = {
            "status": "healthy",
            "active": memory_monitor.monitoring,
            "stats_count": len(memory_stats),
        }

        # Check processing stats
        health_status["components"]["processing_stats"] = {
            "status": "healthy",
            "stats": engine.processing_stats,
        }

        logger.info(f"🏥 Health check completed: {health_status['overall_status']}")
        return health_status

    except Exception as e:
        logger.error(f"🏥 Health check failed: {e}")
        health_status["overall_status"] = "unhealthy"
        health_status["issues"].append(f"Health check error: {e}")
        return health_status


def cleanup_temp_files(temp_dir: str = "./temp", max_age_hours: int = 24):
    """
    Clean up temporary files older than specified age.

    Args:
        temp_dir: Directory to clean
        max_age_hours: Maximum age in hours for files to keep
    """
    try:
        if not os.path.exists(temp_dir):
            return

        max_age_seconds = max_age_hours * 3600
        current_time = time.time()

        cleaned_count = 0
        for filename in os.listdir(temp_dir):
            filepath = os.path.join(temp_dir, filename)
            if os.path.isfile(filepath):
                file_age = current_time - os.path.getmtime(filepath)
                if file_age > max_age_seconds:
                    try:
                        os.remove(filepath)
                        cleaned_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to remove temp file {filepath}: {e}")

        if cleaned_count > 0:
            logger.info(f"🧹 Cleaned {cleaned_count} temporary files from {temp_dir}")

    except Exception as e:
        logger.error(f"Error cleaning temp files: {e}")


# Export main functions
__all__ = [
    "process_article_content",
    "validate_processing_result",
    "format_processing_output",
    "health_check",
    "cleanup_temp_files",
    "memory_monitor",
    "MemoryMonitor",
]
