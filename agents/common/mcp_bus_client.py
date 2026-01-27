"""
MCP Bus Client for Agent Registration.
Shared logic for all agents to register with the central MCP Bus.
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)

class MCPBusClient:
    """MCP Bus client for agent registration."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    def register_agent(self, agent_name: str, agent_address: str, tools: list[str]) -> None:
        """Register agent with MCP Bus with exponential backoff retry."""
        registration_data = {
            "name": agent_name,
            "address": agent_address,
            "tools": tools
        }

        max_retries = 3
        backoff_factor = 2

        for attempt in range(max_retries):
            try:
                # We assume /register endpoint exists on the bus
                response = requests.post(
                    f"{self.base_url}/register", json=registration_data, timeout=(2, 5)
                )
                response.raise_for_status()
                logger.info(f"Successfully registered {agent_name} with MCP Bus at {self.base_url}.")
                return
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed to register {agent_name} with MCP Bus: {e}"
                )
                if attempt < max_retries - 1:
                    sleep_time = backoff_factor ** attempt
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Failed to register {agent_name} after {max_retries} attempts. Continuing in standalone mode.")
                    # We don't raise here to allow the agent to start in standalone mode
