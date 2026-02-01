"""
MCP Bus Client for Agent Registration.
Shared logic for all agents to register with the central MCP Bus.
"""

import logging
import threading
import time

import requests

logger = logging.getLogger(__name__)

class MCPBusClient:
    """MCP Bus client for agent registration."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._stop_event = threading.Event()
        self._monitor_thread = None

    def register_agent(self, agent_name: str, agent_address: str, tools: list[str]) -> None:
        """Register agent with MCP Bus with exponential backoff retry."""
        registration_data = {
            "name": agent_name,
            "address": agent_address,
            "tools": tools
        }
        
        # Initial attempt (synchronous)
        success = self._attempt_registration(registration_data)
        
        # Start background monitor to maintain registration / recover from bus restarts
        self._start_monitor(registration_data)

    def _attempt_registration(self, registration_data: dict) -> bool:
        """Try to register once. Returns True if successful."""
        try:
            response = requests.post(
                f"{self.base_url}/register", json=registration_data, timeout=(5, 10)
            )
            response.raise_for_status()
            logger.info(f"Successfully registered {registration_data['name']} with MCP Bus at {self.base_url}.")
            return True
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to register {registration_data['name']} with MCP Bus: {e}")
            return False

    def _start_monitor(self, registration_data: dict):
        """Start a background thread to maintain registration."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        def monitor_loop():
            logger.info("Starting MCP Bus registration monitor...")
            while not self._stop_event.is_set():
                # Sleep first to avoid spamming if called immediately after initial fail/success
                # Poll interval: 30 seconds
                if self._stop_event.wait(timeout=30):
                    break
                
                # Check health or just re-register?
                # Re-registering is safer as it handles Bus restarts (which clear registry)
                try:
                    # We can optionally check /health first, but POST /register is idempotent enough
                    self._attempt_registration(registration_data)
                except Exception as e:
                    logger.error(f"Error in registration monitor: {e}")

        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True, name="MCPBusMonitor")
        self._monitor_thread.start()

    def stop(self):
        """Stop the monitor thread."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=1.0)
