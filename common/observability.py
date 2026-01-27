"""
Common observability utilities for JustNews
"""

import logging
import os
from logging.handlers import RotatingFileHandler

# Ensure LOG_DIR is defined
LOG_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "logs")
)
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger instance for the given name.
    This function now creates a logger that writes to a dedicated, rotating file.

    Args:
        name: Logger name (typically __name__)
    Returns:
        Configured logger instance
    """
    # Derive a log file name from the logger name. Use the last component
    # after any dots so callers like "test.module" map to "module.log" as
    # expected by tests.
    log_file_name = name.split(".")[-1] if name else "app"
    log_file_path = os.path.join(LOG_DIR, f"{log_file_name}.log")

    logger = logging.getLogger(name)

    # Always ensure the logger has our expected configuration. Do not early-return
    # just because handlers exist; tests rely on specific handlers and levels.
    logger.setLevel(logging.DEBUG)

    # Create or attach a rotating file handler if none present
    has_file = any(isinstance(h, RotatingFileHandler) for h in logger.handlers)
    if not has_file:
        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Ensure a console handler exists. File handlers are also StreamHandlers, so
    # we explicitly ensure we don't treat file handlers as console handlers.
    has_console = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in logger.handlers
    )
    if not has_console:
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


def setup_logging(level: int = logging.INFO, format_string: str | None = None) -> None:
    """
    Setup basic logging configuration for the application.
    This function is now a compatibility wrapper and the main configuration
    is handled by get_logger to ensure file-based logging.
    Args:
        level: Logging level (default: INFO)
        format_string: Custom format string (optional)
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # This basicConfig will apply to any loggers that don't get configured
    # by get_logger, but our goal is to use get_logger everywhere.
    # Configure the root logger to the requested level when requested
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if not root_logger.handlers:
        logging.basicConfig(
            level=level,
            format=format_string,
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[logging.StreamHandler()],  # Default to console
        )


def bootstrap_observability(
    service_name: str, *, level: int = logging.INFO, enable_otel: bool = True
) -> None:
    """Configure logging, metrics, and core monitoring components."""
    # 1. Basic Logging Setup
    setup_logging(level=level)

    # 2. Initialize Core Monitoring Stack (Async-ready)
    try:
        # Import core components locally to avoid circular dependencies
        from monitoring.core.log_aggregator import LogAggregator
        from monitoring.core.trace_processor import TraceProcessor

        # Initialize global instances (idempotent)
        # Note: These require an event loop to run fully, usually provided by the agent using them
        _ = LogAggregator()
        _ = TraceProcessor()

        logging.getLogger(__name__).info(f"Initialized Monitoring Core for {service_name}")
    except ImportError:
        logging.getLogger(__name__).debug("Monitoring Core not found, skipping initialization.")
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to initialize Monitoring Core: {e}")

    # 3. OpenTelemetry (Legacy/External)
    if enable_otel:
        try:
            from common import otel

            initialized = otel.init_telemetry(service_name)
            if not initialized:
                logging.getLogger(__name__).debug(
                    "OpenTelemetry not initialized (missing SDK or disabled)"
                )
        except Exception as exc:  # pragma: no cover - defensive
            logging.getLogger(__name__).warning(
                "Failed to initialize OpenTelemetry: %s", exc
            )

    # 4. Sentry Integration
    try:
        from common import sentry_integration

        sentry_integration.init_sentry(service_name, logger=logging.getLogger(__name__))
    except Exception as exc:  # pragma: no cover - defensive
        logging.getLogger(__name__).warning(
            "Failed to initialize Sentry integration: %s", exc
        )
