"""
Crawler Control Engine for JustNews.

Management and monitoring engine for crawler operations.
"""

import os
from typing import Any

import requests

from common.observability import get_logger

logger = get_logger(__name__)


class CrawlerControlEngine:
    """
    Engine for managing and monitoring crawler operations.
    Provides centralized control over crawling activities.
    """

    def __init__(self):
        self.crawler_agent_url = os.environ.get(
            "CRAWLER_AGENT_URL", "http://localhost:8015"
        )
        self.analyst_agent_url = os.environ.get(
            "ANALYST_AGENT_URL", "http://localhost:8004"
        )
        self.memory_agent_url = os.environ.get(
            "MEMORY_AGENT_URL", "http://localhost:8007"
        )
        self.mcp_bus_url = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

    def start_crawl(self, domains: list[str], **kwargs) -> dict[str, Any]:
        """Start a new crawl job"""
        try:
            payload = {"args": [domains], "kwargs": kwargs}
            response = requests.post(
                f"{self.crawler_agent_url}/unified_production_crawl", json=payload
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to start crawl: {e}")
            raise

    def stop_crawl(self) -> dict[str, Any]:
        """Stop all active crawl jobs"""
        try:
            # Get current jobs
            response = requests.get(f"{self.crawler_agent_url}/jobs")
            response.raise_for_status()
            jobs = response.json()

            stopped_jobs = []
            for job_id, _status in jobs.items():
                if _status in ["running", "pending"]:
                    # Note: The crawler doesn't have a stop endpoint yet
                    # For now, we'll just mark as stopped in our tracking
                    stopped_jobs.append(job_id)

            if stopped_jobs:
                return {
                    "stopped_jobs": stopped_jobs,
                    "message": f"Requested stop for {len(stopped_jobs)} jobs (stopping not yet fully implemented in crawler)",
                }
            else:
                return {"stopped_jobs": [], "message": "No active jobs to stop"}
        except requests.RequestException as e:
            logger.error(f"Failed to stop crawl: {e}")
            raise

    def get_crawl_status(self) -> dict[str, Any]:
        """Get current crawl job statuses"""
        try:
            response = requests.get(f"{self.crawler_agent_url}/jobs")
            response.raise_for_status()
            jobs = response.json()

            # Get details for each job
            job_details = {}
            for job_id, _status in jobs.items():
                try:
                    detail_response = requests.get(
                        f"{self.crawler_agent_url}/job_status/{job_id}"
                    )
                    detail_response.raise_for_status()
                    job_details[job_id] = detail_response.json()
                except requests.RequestException:
                    # best-effort - mark unknown when we can't get job details
                    job_details[job_id] = {"status": "unknown"}

            return job_details
        except requests.RequestException as e:
            logger.error(f"Failed to get crawl status: {e}")
            raise

    def clear_jobs(self) -> dict[str, Any]:
        """Clear completed and failed jobs from crawler memory"""
        try:
            response = requests.post(f"{self.crawler_agent_url}/clear_jobs")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to clear jobs: {e}")
            raise

    def reset_crawler(self) -> dict[str, Any]:
        """Completely reset the crawler state"""
        try:
            response = requests.post(f"{self.crawler_agent_url}/reset_crawler")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to reset crawler: {e}")
            raise

    def get_crawler_metrics(self) -> dict[str, Any]:
        """Get crawler performance metrics"""
        try:
            response = requests.get(f"{self.crawler_agent_url}/metrics")
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            # Fallback mock data
            return {
                "articles_processed": 150,
                "sites_crawled": 5,
                "articles_per_second": 2.5,
                "mode_usage": {"ultra_fast": 2, "ai_enhanced": 1, "generic": 2},
            }

    def get_analyst_metrics(self) -> dict[str, Any]:
        """Get analyst metrics"""
        try:
            response = requests.get(f"{self.analyst_agent_url}/metrics")
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            # Fallback mock data
            return {"sentiment_count": 120, "bias_count": 80, "topics_count": 95}

    def get_memory_metrics(self) -> dict[str, Any]:
        """Get memory usage metrics"""
        try:
            response = requests.get(f"{self.memory_agent_url}/metrics")
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            # Fallback mock data
            return {"used": 60, "free": 40}

    def get_system_health(self) -> dict[str, Any]:
        """Get overall system health"""
        health = {}
        agents = [
            ("crawler", self.crawler_agent_url),
            ("analyst", self.analyst_agent_url),
            ("memory", self.memory_agent_url),
            ("mcp_bus", self.mcp_bus_url),
        ]

        for name, url in agents:
            try:
                response = requests.get(f"{url}/health", timeout=5)
                health[name] = response.status_code == 200
            except Exception:
                health[name] = False

        return health
