import asyncio
from datetime import timezone, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from monitoring.core.log_collector import (
    LogCollector,
    LogEntry,
    LogLevel,
)


@pytest_asyncio.fixture
async def collector():
    # Patch setup_structured_logger to avoid real logging side effects during init
    with patch('monitoring.core.log_collector.LogCollector._setup_structured_logger') as mock_setup:
        mock_logger = MagicMock()
        mock_setup.return_value = mock_logger

        # Initialize
        col = LogCollector(agent_name="test_agent")

        # Ensure we clean up tasks if started
        yield col
        await col.shutdown()

@pytest.mark.asyncio
async def test_initialization():
    """Test default config and initialization."""
    with patch('monitoring.core.log_collector.LogCollector._setup_structured_logger') as mock_setup:
        col = LogCollector("test_agent")
        assert col.agent_name == "test_agent"
        assert col.config["log_level"] == "INFO"
        assert col.config["buffer_size"] == 100
        assert isinstance(col._log_queue, asyncio.Queue)

@pytest.mark.asyncio
async def test_log_queuing(collector):
    """Test that log() puts entry into queue when async is enabled."""
    collector.config["enable_async"] = True

    # Mock queue.put_nowait
    with patch.object(collector._log_queue, 'put_nowait') as mock_put:
        collector.log(LogLevel.INFO, "test message", extra_data={"extra": "value"})

        mock_put.assert_called_once()
        entry = mock_put.call_args[0][0]
        assert isinstance(entry, LogEntry)
        assert entry.level == LogLevel.INFO
        assert entry.message == "test message"
        assert entry.agent_name == "test_agent"
        assert entry.extra_data.get("extra") == "value"

@pytest.mark.asyncio
async def test_log_sync_fallback(collector):
    """Test fallback to sync logging if queue is full."""
    collector.config["enable_async"] = True

    # Mock queue to raise QueueFull
    with patch.object(collector._log_queue, 'put_nowait', side_effect=asyncio.QueueFull):
        # Mock _log_sync
        collector._log_sync = MagicMock()

        collector.log(LogLevel.INFO, "fallback test")

        collector._log_sync.assert_called_once()
        entry = collector._log_sync.call_args[0][0]
        assert entry.message == "fallback test"

@pytest.mark.asyncio
async def test_log_sync_direct(collector):
    """Test direct sync logging when async is disabled."""
    collector.config["enable_async"] = False
    collector._log_sync = MagicMock()

    # We patch the queue just to verify it's NOT called
    with patch.object(collector._log_queue, 'put_nowait') as mock_put:
        collector.log(LogLevel.INFO, "sync test")

        mock_put.assert_not_called()

    # We verify _log_sync called
    collector._log_sync.assert_called_once()

@pytest.mark.asyncio
async def test_process_worker_flush(collector):
    """Test that the worker flushes buffer when size limit is reached."""
    collector.config["buffer_size"] = 2
    collector.config["flush_interval"] = 100 # Long interval

    # Create entries
    e1 = LogEntry(datetime.now(timezone.utc), LogLevel.INFO, "l", "m1")
    e2 = LogEntry(datetime.now(timezone.utc), LogLevel.INFO, "l", "m2")

    # Mock flush buffer - we need to capture the list CONTENT because the list object is cleared
    captured_buffer = []
    async def side_effect(buf):
        captured_buffer.extend(buf[:]) # Copy

    collector._flush_buffer = AsyncMock(side_effect=side_effect)

    # Start worker
    task = asyncio.create_task(collector._process_log_queue())

    # Put 2 items
    await collector._log_queue.put(e1)
    await collector._log_queue.put(e2)

    # Yield control to let processing task run
    # Needs a few cycles to ensure wait_for triggers and loop runs
    await asyncio.sleep(0.01)
    await asyncio.sleep(0.01)

    # Should have flushed
    collector._flush_buffer.assert_called()
    assert len(captured_buffer) == 2
    assert captured_buffer[0].message == "m1"

    # Cleanup
    collector._shutdown_event.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

@pytest.mark.asyncio
async def test_setup_structured_logger():
    """Test logger configuration."""
    # We need to test the real method, not the mock in fixture
    with patch("logging.getLogger") as mock_get_logger, \
         patch("logging.StreamHandler") as mock_stream, \
         patch("logging.handlers.RotatingFileHandler", create=True) as mock_file:

        mock_logger = MagicMock()
        mock_logger.handlers = [] # No existing handlers
        mock_get_logger.return_value = mock_logger

        col = LogCollector("test_agent")

        # Verify handlers added
        assert mock_logger.addHandler.call_count == 2 # Console + File
        mock_stream.assert_called()
        mock_file.assert_called()

@pytest.mark.asyncio
async def test_custom_handler(collector):
    """Test adding custom handlers (e.g. storage)."""
    custom_handler = AsyncMock()
    collector.add_log_handler(custom_handler)

    entry = LogEntry(datetime.now(timezone.utc), LogLevel.INFO, "l", "msg")

    # Manually trigger flush buffer
    await collector._flush_buffer([entry])

    custom_handler.assert_called_once_with(entry)

@pytest.mark.asyncio
async def test_convenience_methods(collector):
    """Test debug, info, etc."""
    collector.log = MagicMock()

    collector.info("info msg", foo="bar")
    collector.log.assert_called_with(LogLevel.INFO, "info msg", foo="bar")

    collector.error("err msg")
    collector.log.assert_called_with(LogLevel.ERROR, "err msg")

@pytest.mark.asyncio
async def test_log_error_method(collector):
    """Test log_error serialization."""
    collector.log = MagicMock()
    try:
        raise ValueError("oops")
    except ValueError as e:
        collector.log_error(e, context="ctx")

    collector.log.assert_called()
    call_kwargs = collector.log.call_args[1]
    assert call_kwargs["error_type"] == "ValueError"
    assert "oops" in collector.log.call_args[0]
    assert "stack_trace" in call_kwargs

