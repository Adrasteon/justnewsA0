import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
import uvicorn

# Ensure LOG_DIR path is correct
LOG_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
)
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def setup_agent_logging(agent_name: str, log_level: str):
    """
    Configures root and uvicorn loggers to write to a rotating file.
    """
    log_file = os.path.join(LOG_DIR, f"{agent_name}.log")
    
    max_bytes = int(os.environ.get("LOG_MAX_BYTES", 512000))
    backup_count = int(os.environ.get("LOG_BACKUP_COUNT", 3))

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Create a shared handler
    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    # Loggers to configure
    # Configure root logger and uvicorn loggers
    loggers_to_configure = [
        logging.getLogger(),              # Root logger
        logging.getLogger("uvicorn"),     # Uvicorn general
        logging.getLogger("uvicorn.access"), # Access logs
        logging.getLogger("uvicorn.error"),  # Error logs
    ]

    for logger in loggers_to_configure:
        # Clear existing handlers to avoid duplication/console output if not desired
        logger.handlers = []
        logger.addHandler(file_handler)
        logger.setLevel(log_level.upper())
    
    # Ensure uvicorn.access doesn't propagate to avoid double logging if root captures it
    logging.getLogger("uvicorn.access").propagate = False
    logging.getLogger("uvicorn.error").propagate = False

def main():
    parser = argparse.ArgumentParser(description="JustNews Agent Runner")
    parser.add_argument("app", help="App string (module:attrib)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--log-level", default="info")
    parser.add_argument("--agent-name", required=True, help="Name of the agent for logging")

    args = parser.parse_args()

    # Setup logging BEFORE uvicorn starts
    setup_agent_logging(args.agent_name, args.log_level)

    # Run uvicorn
    # log_config=None prevents uvicorn from overwriting our logging setup
    uvicorn.run(
        args.app,
        host=args.host,
        port=args.port,
        workers=args.workers,
        log_level=args.log_level.lower(),
        log_config=None
    )

if __name__ == "__main__":
    main()
