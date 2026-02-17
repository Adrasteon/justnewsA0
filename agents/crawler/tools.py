"""
Tools and utilities for the Crawler Agent.
"""

from datetime import datetime
from typing import Any

from .crawler_engine import CrawlerEngine
from .extraction import extract_article_content


def get_crawler_info(*args, **kwargs) -> dict[str, Any]:
    """
    Get information about the crawler configuration and capabilities.
    This is a standalone function for external access to crawler info.
    """
    crawler = CrawlerEngine()

    return {
        "crawler_type": "UnifiedProductionCrawler",
        "version": "3.0",
        "capabilities": [
            "ai_enhanced_crawling",
            "generic_crawling",
            "multi_site_concurrent_crawling",
            "performance_monitoring",
            "database_driven_source_management",
        ],
        "supported_strategies": ["ai_enhanced", "generic"],
        "performance_metrics": crawler.get_performance_report(),
        "database_connected": True,  # Assume connected if no exception
        "timestamp": datetime.now().isoformat(),
    }


def reset_performance_metrics():
    """Reset performance metrics for the crawler"""
    try:
        from ..performance_monitoring import reset_performance_metrics as reset

        reset()
    except ImportError:
        # Performance monitoring might not be available
        pass


__all__ = [
    "get_crawler_info",
    "reset_performance_metrics",
    "extract_article_content",
]
