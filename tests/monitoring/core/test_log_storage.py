from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitoring.core.log_collector import LogEntry, LogLevel
from monitoring.core.log_storage import LogQuery, LogStorage, QueryOperator


# Sample Data
def create_sample_entry(timestamp=None, level=LogLevel.INFO, msg="test"):
    if timestamp is None:
        timestamp = datetime.now(UTC)
    return LogEntry(
        timestamp=timestamp,
        level=level,
        logger_name="test_logger",
        message=msg,
        agent_name="test_agent"
    )

@pytest.fixture
def mock_aiofiles():
    with patch("aiofiles.open", new_callable=MagicMock) as mock:
        file_handle = AsyncMock()
        # Setup file handle context manager
        file_handle.__aenter__.return_value = file_handle
        file_handle.__aexit__.return_value = None

        # Setup read/write mocks
        file_handle.read.return_value = "[]" # Default empty json list
        file_handle.write = AsyncMock()

        mock.return_value = file_handle
        yield mock, file_handle

@pytest.fixture
def storage(tmp_path):
    # Use tmp_path to allow Path operations to work generally,
    # though we might mock specific method calls if needed.
    config = {
        "storage_path": str(tmp_path / "logs"),
        "index_enabled": True,
        "compression_enabled": False,
        "cache_ttl_seconds": 60,
        "max_query_time_seconds": 5,
        "index_fields": ["level", "agent_name"],
        "retention_days": 10
    }

    # Patch create_task to prevent __init__ from spawning background task
    # which fails because no loop is running in sync fixture
    # Also patch _load_index to avoid unawaited coroutine warnings and ensure it doesn't run
    with patch("asyncio.create_task"), \
         patch.object(LogStorage, '_load_index', new_callable=MagicMock) as mock_load_idx:
        # Make sure the mock returns an awaitable if it's awaited somewhere,
        # but create_task just takes the coroutine object.
        # Since we patch create_task, the result of _load_index is passed to the mock create_task.
        # If _load_index is defined as async, calling it returns a coroutine.
        # By mocking it with MagicMock (not AsyncMock) we avoid creating a coroutine that needs awaiting.
        return LogStorage(config)

@pytest.mark.asyncio
async def test_store_logs_writes_file(storage, mock_aiofiles):
    """Test that store_logs writes log entries to the correct file."""
    mock_open_fn, mock_handle = mock_aiofiles

    dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    entries = [create_sample_entry(dt, msg="entry1")]

    # Mock _load_log_file to return empty list so we just append our new entry
    with patch.object(storage, '_load_log_file', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = []

        await storage.store_logs(entries)

        # Verify file path format based on timestamp
        expected_filename = f"logs_{dt.strftime('%Y%m%d_%H')}.json"

        # Check if open was called for the log file
        # store_logs calls open twice: once for logs, once for index.
        # We need to find the specific call.
        found_log_file = False
        for call in mock_open_fn.call_args_list:
            args = call[0]
            if str(args[0]).endswith(expected_filename) and args[1] == "w":
                found_log_file = True
                break

        assert found_log_file, f"Expected open call for {expected_filename} not found"

        # Check if write was called with correct data
        # Similarly, find the write call that contains our message
        found_content = False
        for call in mock_handle.write.call_args_list:
            arg = call[0][0]
            if "entry1" in arg:
                found_content = True
                break

        assert found_content, "Expected content 'entry1' not found in any write call"

@pytest.mark.asyncio
async def test_find_relevant_files_no_index(storage):
    """Test finding files without index works (fallback to glob)."""
    storage.index_enabled = False
    with patch.object(Path, "glob") as mock_glob:
        mock_glob.return_value = [Path("logs_mock.json")]

        files = await storage._find_relevant_files(LogQuery())
        assert len(files) == 1
        mock_glob.assert_called()

@pytest.mark.asyncio
async def test_matches_operator(storage):
    """Test the operator matching logic."""
    # EQUALS
    assert storage._matches_operator("foo", "foo", QueryOperator.EQUALS)
    assert not storage._matches_operator("foo", "bar", QueryOperator.EQUALS)

    # CONTAINS
    assert storage._matches_operator("hello world", "world", QueryOperator.CONTAINS)
    assert not storage._matches_operator("hello world", "mars", QueryOperator.CONTAINS)

    # NUMERIC comparison
    assert storage._matches_operator(10, 5, QueryOperator.GREATER_THAN)
    assert storage._matches_operator(5, 10, QueryOperator.LESS_THAN)

    # REGEX
    assert storage._matches_operator("error-123", r"error-\d+", QueryOperator.REGEX)

    # IN
    assert storage._matches_operator("a", ["a", "b"], QueryOperator.IN)

@pytest.mark.asyncio
async def test_query_filtering(storage):
    """Test filtering logic within _query_file."""
    dt = datetime.now(UTC)
    entries = [
        create_sample_entry(dt, LogLevel.INFO, "info msg"),
        create_sample_entry(dt, LogLevel.ERROR, "error msg"),
    ]

    # Mock loading file to return our entries
    with patch.object(storage, '_load_log_file', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = entries

        # Query for ERROR only
        query = LogQuery(filters={"level": LogLevel.ERROR})

        result_entries = await storage._query_file(Path("dummy"), query)

        assert len(result_entries) == 1
        assert result_entries[0].level == LogLevel.ERROR
        assert result_entries[0].message == "error msg"

@pytest.mark.asyncio
async def test_cleanup_old_logs(storage, tmp_path):
    """Test retention policy enforcement using real files in tmp_path."""
    # storage.storage_path is already set to tmp_path/logs by fixture
    # Verify it exists
    log_dir = Path(storage.config["storage_path"])
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create fake files
    old_date = datetime.now(UTC) - timedelta(days=20)
    new_date = datetime.now(UTC)

    old_filename = f"logs_{old_date.strftime('%Y%m%d_%H')}.json"
    new_filename = f"logs_{new_date.strftime('%Y%m%d_%H')}.json"

    old_file = log_dir / old_filename
    new_file = log_dir / new_filename

    old_file.touch()
    new_file.touch()

    # Ensure they exist
    assert old_file.exists()
    assert new_file.exists()

    # Run cleanup with 10 day retention
    # We must patch load_index call inside storage if it runs,
    # but cleanup works on files mostly.
    # The LogStorage _cleanup method deletes from index too, so we might need to mock _index dict
    storage._index = {}
    storage._reverse_index = {}

    count = await storage.cleanup_old_logs(retention_days=10)

    assert count == 1
    assert not old_file.exists()
    assert new_file.exists()

@pytest.mark.asyncio
async def test_query_cache(storage):
    """Test that subsequent identical queries hit the cache."""
    query = LogQuery(filters={"test": "data"})

    # First call - mock cache key generation to simple string
    with patch.object(storage, '_find_relevant_files', return_value=[]), \
         patch.object(storage, '_sort_entries', return_value=[]):

        # Ensure cache is empty
        assert len(storage._query_cache) == 0

        await storage.query_logs(query)

        assert len(storage._query_cache) == 1

        # Modify cache to verify hit (dirty hack)
        key = list(storage._query_cache.keys())[0]
        storage._query_cache[key].total_count = 999

        # Second call
        result = await storage.query_logs(query)
        assert result.total_count == 999

@pytest.mark.asyncio
async def test_update_index(storage, mock_aiofiles):
    """Test that index data structure is updated."""
    _, mock_handle = mock_aiofiles

    # Setup initial index state
    storage._index = {}

    entries = [create_sample_entry(level=LogLevel.ERROR)]
    filename = "test_log.json"

    # Mock saving index file
    with patch("aiofiles.open", return_value=mock_handle):
        await storage._update_index(filename, entries)

    # Check in-memory index update
    # Configured index fields: ["level", "agent_name"]
    assert "level" in storage._index
    # ERROR enum string value
    assert "LogLevel.ERROR" in storage._index["level"] or "ERROR" in storage._index["level"]
    # Check path presence
    paths = list(storage._index["level"].values())[0]
    assert any("test_log.json" in p for p in paths)

