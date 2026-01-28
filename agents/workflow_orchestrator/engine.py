"""
Workflow Engine for the Orchestrator.

Executes the main orchestration loop.
"""

import asyncio
import json
import os
import time
from typing import List

from common.observability import get_logger
from .policies import (
    WorkflowPolicy,
    IngestionToAnalysisPolicy,
    AnalysisToEmbeddingPolicy,
    AnalysisToSummaryPolicy,
    SummaryToFactCheckPolicy,
    FactCheckToClusterPolicy,
    ClusterToSynthesisPolicy,
)
from .resources import ResourceMonitor

logger = get_logger(__name__)

class OrchestratorEngine:
    def __init__(self):
        self.running = False
        self.resource_monitor = ResourceMonitor()
        self.policies: List[WorkflowPolicy] = []
        self._load_config()
        self._init_policies()

    def _load_config(self):
        self.mcp_bus_url = os.environ.get("MCP_BUS_URL", "http://localhost:8000")
        
        # Default Config
        self.config = {
            "polling_interval_seconds": 10,
            "max_concurrent_tasks": 5,
            "resource_limits": {
                "max_cpu_percent": 80,
                "max_memory_percent": 85,
                "max_gpu_utilization": 90,
                "max_gpu_memory_percent": 90
            }
        }
        
        # Override from system_config.json if available
        try:
            config_path = os.path.join(os.getcwd(), "config", "system_config.json")
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    sys_config = json.load(f)
                    orch_config = sys_config.get("orchestrator", {})
                    self.config.update(orch_config)
        except Exception as e:
            logger.warning(f"Failed to load system_config.json: {e}")

    def _init_policies(self):
        # Register enabled policies
        self.policies.append(IngestionToAnalysisPolicy(self.mcp_bus_url))
        self.policies.append(AnalysisToEmbeddingPolicy(self.mcp_bus_url))
        self.policies.append(AnalysisToSummaryPolicy(self.mcp_bus_url))
        self.policies.append(SummaryToFactCheckPolicy(self.mcp_bus_url))
        self.policies.append(FactCheckToClusterPolicy(self.mcp_bus_url))
        self.policies.append(ClusterToSynthesisPolicy(self.mcp_bus_url))
        logger.info(f"Initialized {len(self.policies)} policies.")

    async def start(self):
        """Start the orchestration loop."""
        self.running = True
        logger.info("Orchestrator Engine started.")
        asyncio.create_task(self._run_loop())

    async def stop(self):
        """Stop the orchestration loop."""
        self.running = False
        logger.info("Orchestrator Engine stopping...")

    async def _run_loop(self):
        while self.running:
            start_time = time.time()
            try:
                await self._process_tick()
            except Exception as e:
                logger.error(f"Error in orchestration loop: {e}", exc_info=True)
            
            # Sleep remainder of interval
            elapsed = time.time() - start_time
            sleep_time = max(1.0, self.config["polling_interval_seconds"] - elapsed)
            await asyncio.sleep(sleep_time)

    async def _process_tick(self):
        # 1. Check Resources
        thresholds = self.config["resource_limits"]
        if not self.resource_monitor.check_health(thresholds):
            logger.info("Resources saturated. Skipping tick.")
            return

        # 2. Iterate Policies
        max_tasks = self.config["max_concurrent_tasks"]
        
        for policy in self.policies:
            # We treat max_tasks as a per-policy limit for simplicity v1
            try:
                items = policy.check_condition(limit=max_tasks)
                if items:
                    logger.info(f"Policy '{policy.name()}' matched {len(items)} items.")
                    await policy.execute(items)
                else:
                    # Debug log only to avoid spam
                    # logger.debug(f"Policy '{policy.name()}' matched 0 items.")
                    pass
            except Exception as e:
                logger.error(f"Policy '{policy.name()}' failure: {e}")
