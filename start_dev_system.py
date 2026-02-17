#!/usr/bin/env python3
"""
start_dev_system.py - Start the JustNews system for development/simulation

Starts the essential agents in the correct order:
1. MCP Bus (message broker for all agents)
2. Crawler (main crawling engine)
3. Workflow Orchestrator (manages crawl workflows)
4. Memory Agent (data storage - already running)

Usage:
    python start_dev_system.py

Environment variables:
    VERBOSE=1  - Show verbose logging
    AGENTS="mcp_bus,crawler,workflow_orchestrator"  - Custom agent list
"""

import os
import sys
import time
import subprocess
import signal
from pathlib import Path

# Add app to path
sys.path.insert(0, os.getcwd())

# Set base environment variables
os.environ["JUSTNEWS_DISABLE_TEST_DB_FALLBACK"] = "1"
os.environ["CHROMADB_REQUIRE_CANONICAL"] = "0"  # Allow operation without ChromaDB

# Disable CUDA if requested
if os.environ.get("DEV_CPU_ONLY", "") == "1" or os.environ.get("FORCE_CPU", "") == "1":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

VERBOSE = os.environ.get("VERBOSE", "").lower() in ("1", "true", "yes")
LOG_DIR = Path("/tmp/justnews_dev_logs")
LOG_DIR.mkdir(exist_ok=True)

# Essential agents for crawling workflow
ESSENTIAL_AGENTS = [
    "mcp_bus",              # Communication bus - MUST be first
    "crawler",              # Main crawler engine - MUST be second
    "workflow_orchestrator", # Workflow management
]

# Optional agents
OPTIONAL_AGENTS = [
    "crawler_control",      # Crawler web UI
    "gpu_orchestrator",     # GPU management (optional if no GPU)
]

# Memory agent runs separately (already configured)

AGENT_CONFIG = {
    "mcp_bus": {
        "port": 8000,
        "path": "agents/mcp_bus/main.py",
        "module": "agents.mcp_bus.main",
        "app_var": "app",
        "host": "0.0.0.0",
    },
    "crawler": {
        "port": 8009,
        "path": "agents/crawler/main.py",
        "module": "agents.crawler.main",
        "app_var": "app",
        "host": "0.0.0.0",
        "env": {"CRAWLER_HOST": "0.0.0.0", "CRAWLER_AGENT_PORT": "8009"},
    },
    "workflow_orchestrator": {
        "port": 8020,
        "path": "agents/workflow_orchestrator/main.py",
        "module": "agents.workflow_orchestrator.main",
        "app_var": "app",
        "host": "0.0.0.0",
        "env": {"WORKFLOW_HOST": "0.0.0.0", "WORKFLOW_PORT": "8020"},
    },
    "crawler_control": {
        "port": 8016,
        "path": "agents/crawler_control/main.py",
        "module": "agents.crawler_control.main",
        "app_var": "app",
        "host": "0.0.0.0",
        "env": {"CRAWLER_CONTROL_HOST": "0.0.0.0", "CRAWLER_CONTROL_PORT": "8016"},
    },
}

processes = {}


def log_info(msg: str):
    """Log info message"""
    print(f"\033[0;34m[INFO]\033[0m {msg}")


def log_success(msg: str):
    """Log success message"""
    print(f"\033[0;32m[SUCCESS]\033[0m {msg}")


def log_warn(msg: str):
    """Log warning message"""
    print(f"\033[1;33m[WARN]\033[0m {msg}")


def log_error(msg: str):
    """Log error message"""
    print(f"\033[0;31m[ERROR]\033[0m {msg}")


def check_port(port: int) -> bool:
    """Check if a port is already in use"""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(("localhost", port))
    sock.close()
    return result == 0


def start_agent(name: str, config: dict) -> subprocess.Popen | None:
    """Start a single agent"""
    port = config["port"]
    log_info(f"Starting {name} on port {port}...")

    # Check if port is already in use
    if check_port(port):
        log_warn(f"Port {port} already in use - {name} might already be running")
        return None

    log_file = LOG_DIR / f"{name}.log"

    # Prepare environment
    env = os.environ.copy()
    env.update(config.get("env", {}))

    # Start with uvicorn
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        f"{config['module']}:{config['app_var']}",
        "--host",
        config.get("host", "0.0.0.0"),
        "--port",
        str(port),
    ]

    if VERBOSE:
        print(f"  Command: {' '.join(cmd)}")

    try:
        with open(log_file, "w") as log:
            proc = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd="/app",
                env=env,
            )
        log_success(f"{name} started (PID: {proc.pid}, logs: {log_file})")
        return proc
    except Exception as e:
        log_error(f"Failed to start {name}: {e}")
        return None


def wait_for_port(port: int, timeout: int = 30) -> bool:
    """Wait for a port to become available"""
    import socket

    start_time = time.time()
    while time.time() - start_time < timeout:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(("localhost", port))
        sock.close()
        if result == 0:
            return True
        time.sleep(0.5)
    return False


def verify_agent(name: str, port: int) -> bool:
    """Verify an agent is running and responding"""
    if not wait_for_port(port, timeout=15):
        log_error(f"{name} did not start responding on port {port}")
        return False

    try:
        # Try to reach the health endpoint
        import requests

        response = requests.get(f"http://localhost:{port}/health", timeout=5)
        if response.status_code == 200:
            log_success(f"{name} verified on port {port}")
            return True
        else:
            log_warn(f"{name} returned non-200 status: {response.status_code}")
            return True  # Still consider it started
    except Exception as e:
        # Port is open but /health might not be available on all agents
        log_warn(f"Could not verify {name} with HTTP probe: {e} (but port is open)")
        return True


def start_agents(agent_list: list[str] | None = None) -> bool:
    """Start all required agents in order"""
    if agent_list is None:
        agent_list = ESSENTIAL_AGENTS

    log_info(f"Starting {len(agent_list)} agents: {', '.join(agent_list)}")
    print()

    for agent in agent_list:
        if agent not in AGENT_CONFIG:
            log_error(f"Unknown agent: {agent}")
            return False

        config = AGENT_CONFIG[agent]

        # Start the agent
        proc = start_agent(agent, config)
        if proc is None:
            log_error(f"Failed to start {agent}")
            return False

        processes[agent] = proc

        # Wait a bit for it to initialize
        time.sleep(1)

        # Verify it's running
        if not verify_agent(agent, config["port"]):
            log_error(f"Failed to verify {agent}")
            return False

        # Add inter-service delay for sequential startup
        if agent != agent_list[-1]:
            time.sleep(1)

    return True


def stop_agents():
    """Stop all running agents"""
    log_info("Stopping agents...")
    for name, proc in reversed(list(processes.items())):
        if proc and proc.poll() is None:  # Still running
            log_info(f"Stopping {name} (PID: {proc.pid})...")
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                log_success(f"Stopped {name}")
            except Exception as e:
                log_error(f"Error stopping {name}: {e}")


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    log_info("\nReceived interrupt signal")
    stop_agents()
    sys.exit(0)


def main():
    """Main entry point"""
    log_info("JustNews Development System Startup")
    log_info(f"Logs directory: {LOG_DIR}")
    print()

    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Determine which agents to start
    agent_list = os.environ.get("AGENTS", "").split(",") if os.environ.get("AGENTS") else ESSENTIAL_AGENTS
    agent_list = [a.strip() for a in agent_list if a.strip()]

    # Start the agents
    if not start_agents(agent_list):
        log_error("Failed to start all agents")
        stop_agents()
        return 1

    print()
    log_success("All agents started successfully!")
    print()
    log_info("System readiness summary:")
    print(f"  • MCP Bus:               http://localhost:8000")
    print(f"  • Crawler:               http://localhost:8009")
    print(f"  • Workflow Orchestrator: http://localhost:8020")
    print(f"  • Crawler Control:       http://localhost:8016")
    print(f"  • Memory Agent:          http://localhost:8007")
    print()
    log_info("Keeping agents running. Press Ctrl+C to stop.")
    print()

    # Keep the script running
    try:
        while True:
            # Check if any process has died
            for name, proc in processes.items():
                if proc and proc.poll() is not None:
                    log_warn(f"Agent {name} died with exit code {proc.returncode}")
                    # Optionally restart or exit
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        stop_agents()

    return 0


if __name__ == "__main__":
    sys.exit(main())
