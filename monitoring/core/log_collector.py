"""
JustNews Centralized Logging System

Provides structured logging, aggregation, and search capabilities for all agents
and services in the JustNews system.
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class LogLevel(Enum):
    """Standardized log levels"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(Enum):
    """Supported log formats"""

    JSON = "json"
    TEXT = "text"
    STRUCTURED = "structured"


@dataclass
class LogEntry:
    """Structured log entry"""

    timestamp: datetime
    level: LogLevel
    logger_name: str
    message: str
    agent_name: str | None = None
    agent_id: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    user_id: int | None = None
    endpoint: str | None = None
    method: str | None = None
    status_code: int | None = None
    duration_ms: float | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    stack_trace: str | None = None
    extra_data: dict[str, Any] | None = None
    correlation_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        # Convert enum to string
        data["level"] = self.level.value
        # Convert datetime to ISO format
        data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LogEntry":
        """Create from dictionary"""
        # Convert string back to enum
        data["level"] = LogLevel(data["level"])
        # Convert ISO string back to datetime
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


class LogCollector:
    """
    Centralized log collector for JustNews.

    Provides structured logging interface, log aggregation, and multiple output
    destinations including console, files, and external systems.
    """

    def __init__(self, agent_name: str, config: dict[str, Any] | None = None):
        self.agent_name = agent_name
        self.agent_id = str(uuid.uuid4())
        self.config = config or self._get_default_config()

        # Initialize logging components
        self._log_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._log_handlers: list[Callable] = []
        self._structured_logger = self._setup_structured_logger()

        # Start background processing
        self._processing_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()

    def _get_default_config(self) -> dict[str, Any]:
        """Get default logging configuration"""
        return {
            "log_level": "INFO",
            "format": "json",
            "console_output": True,
            "file_output": True,
            "file_path": f"logs/{self.agent_name}.log",
            "max_file_size": 100 * 1024 * 1024,  # 100MB
            "max_files": 5,
            "buffer_size": 100,
            "flush_interval": 5.0,
            "enable_async": True,
            "structured_fields": True,
        }

    def _setup_structured_logger(self) -> logging.Logger:
        """Setup structured logger with appropriate handlers"""
        logger = logging.getLogger(f"justnews.{self.agent_name}")
        logger.setLevel(getattr(logging, self.config["log_level"]))

        # Remove existing handlers to avoid duplicates
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # Add console handler if enabled
        if self.config["console_output"]:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(self._get_formatter())
            logger.addHandler(console_handler)

        # Add file handler if enabled
        if self.config["file_output"]:
            from logging.handlers import RotatingFileHandler

            os.makedirs(os.path.dirname(self.config["file_path"]), exist_ok=True)
            file_handler = RotatingFileHandler(
                self.config["file_path"],
                maxBytes=self.config["max_file_size"],
                backupCount=self.config["max_files"],
            )
            file_handler.setFormatter(self._get_formatter())
            logger.addHandler(file_handler)

        return logger

    def _get_formatter(self) -> logging.Formatter:
        """Get appropriate formatter based on configuration"""
        if self.config["format"] == "json":
            return StructuredJSONFormatter()
        elif self.config["format"] == "structured":
            return StructuredTextFormatter()
        else:
            return logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )

    async def start(self) -> None:
        """Start the log collector"""
        if self.config["enable_async"]:
            self._processing_task = asyncio.create_task(self._process_log_queue())
            # Schedule periodic flush
            asyncio.create_task(self._periodic_flush())

    async def shutdown(self) -> None:
        """Shutdown the log collector"""
        self._shutdown_event.set()

        if self._processing_task:
            await self._processing_task

        # Final flush
        await self._flush_logs()

    def log(self, level: LogLevel, message: str, **kwargs) -> None:
        """Log a message with structured data"""
        entry = LogEntry(
            timestamp=datetime.now(UTC),
            level=level,
            logger_name=f"justnews.{self.agent_name}",
            message=message,
            agent_name=self.agent_name,
            agent_id=self.agent_id,
            **kwargs,
        )

        if self.config["enable_async"]:
            # Async logging - add to queue
            try:
                self._log_queue.put_nowait(entry)
            except asyncio.QueueFull:
                # Fallback to sync logging if queue is full
                self._log_sync(entry)
        else:
            # Sync logging
            self._log_sync(entry)

    def _log_sync(self, entry: LogEntry) -> None:
        """Synchronous logging"""
        # Convert to logging level
        log_level = getattr(logging, entry.level.value)

        # Create log record with structured data
        extra = entry.to_dict()
        extra.pop("timestamp")  # Remove timestamp as it's handled by formatter
        extra.pop("level")  # Remove level as it's handled by logging
        extra.pop("logger_name")  # Remove logger_name as it's handled by logging
        extra.pop("message")  # Remove message as it's handled by logging

        self._structured_logger.log(log_level, entry.message, extra=extra)

    async def _process_log_queue(self) -> None:
        """Process log entries from the queue"""
        buffer = []
        buffer_size = self.config["buffer_size"]

        while not self._shutdown_event.is_set():
            try:
                # Wait for log entry or timeout
                try:
                    entry = await asyncio.wait_for(
                        self._log_queue.get(), timeout=self.config["flush_interval"]
                    )
                    buffer.append(entry)
                except TimeoutError:
                    # Flush buffer on timeout
                    if buffer:
                        await self._flush_buffer(buffer)
                        buffer.clear()
                    continue

                # Flush buffer when it reaches size limit
                if len(buffer) >= buffer_size:
                    await self._flush_buffer(buffer)
                    buffer.clear()

            except Exception as e:
                # Log processing error (avoid recursion)
                print(f"Log processing error: {e}", file=sys.stderr)

        # Final flush on shutdown
        if buffer:
            await self._flush_buffer(buffer)

    async def _flush_buffer(self, buffer: list[LogEntry]) -> None:
        """Flush log buffer to all handlers"""
        try:
            # Process each entry
            for entry in buffer:
                self._log_sync(entry)

                # Send to additional handlers
                for handler in self._log_handlers:
                    try:
                        await handler(entry)
                    except Exception as e:
                        print(f"Log handler error: {e}", file=sys.stderr)

        except Exception as e:
            print(f"Buffer flush error: {e}", file=sys.stderr)

    async def _flush_logs(self) -> None:
        """Force flush all pending logs"""
        # Process remaining queue items
        remaining_entries = []
        while not self._log_queue.empty():
            try:
                entry = self._log_queue.get_nowait()
                remaining_entries.append(entry)
            except asyncio.QueueEmpty:
                break

        if remaining_entries:
            await self._flush_buffer(remaining_entries)

    async def _periodic_flush(self) -> None:
        """Periodic flush task"""
        while not self._shutdown_event.is_set():
            await asyncio.sleep(self.config["flush_interval"])
            await self._flush_logs()

    def add_log_handler(self, handler: Callable) -> None:
        """Add additional log handler"""
        self._log_handlers.append(handler)

    def remove_log_handler(self, handler: Callable) -> None:
        """Remove log handler"""
        if handler in self._log_handlers:
            self._log_handlers.remove(handler)

    # Convenience methods for different log levels
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message"""
        self.log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        """Log info message"""
        self.log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message"""
        self.log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        """Log error message"""
        self.log(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs) -> None:
        """Log critical message"""
        self.log(LogLevel.CRITICAL, message, **kwargs)

    def log_request(
        self, method: str, endpoint: str, status_code: int, duration_ms: float, **kwargs
    ) -> None:
        """Log HTTP request"""
        level = (
            LogLevel.INFO
            if status_code < 400
            else LogLevel.WARNING
            if status_code < 500
            else LogLevel.ERROR
        )
        self.log(level, f"{method} {endpoint} {status_code}", **kwargs)

    def log_error(self, error: Exception, **kwargs) -> None:
        """Log exception with context"""
        self.log(
            LogLevel.ERROR,
            str(error),
            error_type=type(error).__name__,
            stack_trace=self._get_stack_trace(error),
            **kwargs,
        )

    def _get_stack_trace(self, error: Exception) -> str:
        """Get formatted stack trace"""
        import traceback

        return "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )


class StructuredJSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        # Create base log entry
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in [
                    "name",
                    "msg",
                    "args",
                    "levelname",
                    "levelno",
                    "pathname",
                    "filename",
                    "module",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                    "lineno",
                    "funcName",
                    "created",
                    "msecs",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "processName",
                    "process",
                    "message",
                ]:
                    log_entry[key] = value

        return json.dumps(log_entry, default=str)


class StructuredTextFormatter(logging.Formatter):
    """Structured text formatter"""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured text"""
        timestamp = datetime.now(UTC).isoformat()
        level = record.levelname
        logger = record.name
        message = record.getMessage()

        # Build structured text
        parts = [f"{timestamp} [{level}] {logger}: {message}"]

        # Add extra fields
        extra_fields = []
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in [
                    "name",
                    "msg",
                    "args",
                    "levelname",
                    "levelno",
                    "pathname",
                    "filename",
                    "module",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                    "lineno",
                    "funcName",
                    "created",
                    "msecs",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "processName",
                    "process",
                    "message",
                ]:
                    extra_fields.append(f"{key}={value}")

        if extra_fields:
            parts.append(" | ".join(extra_fields))

        return " | ".join(parts)


# Global log collector instance
_default_collector: LogCollector | None = None


def get_log_collector(agent_name: str) -> LogCollector:
    """Get or create log collector for an agent"""
    global _default_collector

    if _default_collector is None or _default_collector.agent_name != agent_name:
        _default_collector = LogCollector(agent_name)

    return _default_collector


def init_logging_for_agent(
    agent_name: str, config: dict[str, Any] | None = None
) -> LogCollector:
    """Initialize logging for a specific agent"""
    collector = LogCollector(agent_name, config)
    global _default_collector
    _default_collector = collector
    return collector
