import asyncio
from datetime import timezone, datetime
from unittest.mock import AsyncMock, patch

import pytest

from monitoring.core.log_aggregator import (
    AggregationStrategy,
    LogAggregator,
)
from monitoring.core.log_collector import LogEntry, LogLevel


@pytest.fixture
def mock_log_entry():
    return LogEntry(
        timestamp=datetime.now(timezone.utc),
        level=LogLevel.INFO,
        logger_name="test",
        message="msg",
        agent_name="agent"
    )

@pytest.fixture
def aggregator():
    agg = LogAggregator()
    # Clear default backends (File backend)
    agg._storage_backends = []
    return agg

@pytest.mark.asyncio
class TestLogAggregator:

    async def test_initialization(self, aggregator):
        assert aggregator.aggregation_config.strategy == AggregationStrategy.TIME_WINDOW
        assert len(aggregator._log_buffer) == 0

    async def test_aggregate_log_buffer(self, aggregator, mock_log_entry):
        await aggregator.aggregate_log(mock_log_entry)
        assert len(aggregator._log_buffer) == 1
        assert aggregator._log_buffer[0] == mock_log_entry
        assert aggregator._logs_processed == 1

    async def test_flush_size_based(self, mock_log_entry):
        config = {"aggregation": {"strategy": "size_based", "max_batch_size": 2}}
        agg = LogAggregator(config=config)
        agg._storage_backends = [AsyncMock()]
        mock_backend = agg._storage_backends[0]

        # Add 1st log - no flush
        await agg.aggregate_log(mock_log_entry)
        assert len(agg._log_buffer) == 1
        mock_backend.assert_not_called()

        # Add 2nd log - flush triggered
        await agg.aggregate_log(mock_log_entry)
        assert len(agg._log_buffer) == 0 # Flush clears buffer
        mock_backend.assert_called_once()

    async def test_flush_event_count(self, mock_log_entry):
        config = {"aggregation": {"strategy": "event_count", "max_batch_size": 2}}
        agg = LogAggregator(config=config)
        agg._storage_backends = [AsyncMock()]
        mock_backend = agg._storage_backends[0]

        # Similar logic to size_based in implementation usually
        await agg.aggregate_log(mock_log_entry)
        await agg.aggregate_log(mock_log_entry)

        mock_backend.assert_called_once()

    async def test_flush_buffer_calls_backends(self, aggregator, mock_log_entry):
        mock_backend = AsyncMock()
        aggregator._storage_backends.append(mock_backend)

        aggregator._log_buffer.append(mock_log_entry)
        await aggregator._flush_buffer()

        assert len(aggregator._log_buffer) == 0
        mock_backend.assert_called_once()
        args = mock_backend.call_args[0][0] # First arg should be list of entries
        assert len(args) == 1
        assert args[0] == mock_log_entry.to_dict()

    async def test_shutdown(self, aggregator):
        async def dummy(): pass
        aggregator._flush_task = asyncio.create_task(dummy())

        # Mock _flush_buffer to ensure it's called
        with patch.object(aggregator, '_flush_buffer', new_callable=AsyncMock) as mock_flush:
            await aggregator.shutdown()

            assert aggregator._shutdown_event.is_set()
            mock_flush.assert_called()

