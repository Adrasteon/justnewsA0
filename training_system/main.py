"""
Main entry point for the JustNews Training System Agent
Provides MCP Bus integration and FastAPI endpoints for online training coordination
"""

import os

import uvicorn

from common.observability import get_logger

# Configure centralized logging
logger = get_logger(__name__)


def main():
    """Main entry point for the training system agent"""
    # Environment variables
    host = os.environ.get("TRAINING_SYSTEM_HOST", "0.0.0.0")
    port = int(os.environ.get("TRAINING_SYSTEM_PORT", 8009))
    workers = int(os.environ.get("TRAINING_SYSTEM_WORKERS", 1))

    logger.info("🚀 Starting JustNews Training System Agent")
    logger.info(f"   📍 Host: {host}")
    logger.info(f"   🔌 Port: {port}")
    logger.info(f"   👷 Workers: {workers}")
    logger.info(
        f"   🔗 MCP Bus URL: {os.environ.get('MCP_BUS_URL', 'http://localhost:8000')}"
    )

    # Start the FastAPI server
    uvicorn.run(
        "training_system.mcp_integration:app",
        host=host,
        port=port,
        workers=workers,
        reload=False,  # Disable reload in production
        log_level="info",
    )


if __name__ == "__main__":
    main()
