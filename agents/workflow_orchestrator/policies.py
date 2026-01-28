"""
Workflow Policies for the Orchestrator.

This module defines the abstract base class and concrete implementations
for data pipeline transitions.
"""

from abc import ABC, abstractmethod
from typing import List, Any
import requests
import asyncio
from concurrent.futures import ThreadPoolExecutor

from common.observability import get_logger
from database.utils.migrated_database_utils import create_database_service

logger = get_logger(__name__)

class WorkflowPolicy(ABC):
    """Abstract base class for a workflow policy."""
    
    def __init__(self, mcp_bus_url: str):
        self.mcp_bus_url = mcp_bus_url
        self.db_service = create_database_service()

    @abstractmethod
    def name(self) -> str:
        """Name of the policy."""
        pass

    @abstractmethod
    def check_condition(self, limit: int) -> List[Any]:
        """Return a list of items (IDs) that match the condition."""
        pass

    @abstractmethod
    async def execute(self, items: List[Any]):
        """Execute the workflow action on the items."""
        pass
    
    def _call_mcp_tool_sync(self, agent: str, tool: str, kwargs: dict) -> dict:
        """Synchronous call to MCP Bus."""
        try:
            payload = {
                "agent": agent,
                "tool": tool,
                "kwargs": kwargs,
                "args": []
            }
            response = requests.post(f"{self.mcp_bus_url}/call", json=payload, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to call {agent}.{tool}: {e}")
            return {"status": "error", "error": str(e)}

    async def _call_mcp_tool(self, agent: str, tool: str, kwargs: dict):
        """Async wrapper for MCP tool call."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._call_mcp_tool_sync, agent, tool, kwargs)


class IngestionToAnalysisPolicy(WorkflowPolicy):
    """
    Policy: Ingested -> Analyzed
    Condition: articles.analyzed = 0
    Action: Call 'analyst.analyze_article'
    """

    def name(self) -> str:
        return "ingestion_to_analysis"

    def check_condition(self, limit: int) -> List[int]:
        ids = []
        try:
            self.db_service.ensure_conn()
            cursor = self.db_service.mb_conn.cursor()
            # Select unanalyzed articles, preferring newer ones
            query = """
                SELECT id FROM articles 
                WHERE analyzed = 0 
                ORDER BY created_at DESC 
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            ids = [row[0] for row in rows]
            cursor.close()
        except Exception as e:
            logger.error(f"Error checking DB condition for {self.name()}: {e}")
            # Try to reconnect on next pass
            try:
                self.db_service.ensure_conn()
            except:
                pass
        return ids

    async def execute(self, items: List[int]):
        logger.info(f"Triggering analysis for {len(items)} articles.")
        tasks = []
        for article_id in items:
            # We call the analyst agent via MCP Bus
            # Based on previous investigation, Analyst expects a ToolCall wrapped payload if called directly,
            # but via MCP bus, we send standard args/kwargs.
            # The MCP Bus 'call' endpoint takes: agent, tool, args, kwargs.
            # The Analyst 'analyze_article' tool expects a 'call: ToolCall' object if hitting the endpoint directly,
            # BUT wait.
            # Let's verify how MCP Bus calls the agent.
            # MCP Bus calls `{agent_address}/{tool_name}` with `{"args": ..., "kwargs": ...}`.
            # Analyst `analyze_article` endpoint expects `ToolCall` which has `args` and `kwargs`.
            # So MCP Bus payload matches Analyst expectation exactly.
            
            # Param: article_id via kwargs
            tasks.append(
                self._call_mcp_tool(
                    agent="analyst",
                    tool="analyze_article",
                    kwargs={"article_id": article_id}
                )
            )
        
        # Run concurrent triggers
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success_count = 0
        for res in results:
            if isinstance(res, dict) and res.get("status") == "success":
                success_count += 1
            elif isinstance(res, Exception):
                logger.error(f"Task failed: {res}")
        
        logger.info(f"Triggered batch complete. Success: {success_count}/{len(items)}")

