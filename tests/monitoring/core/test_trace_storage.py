from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitoring.core.trace_collector import TraceData, TraceSpan
from monitoring.core.trace_storage import (
    FileTraceStorage,
    TraceQuery,
    TraceStorage,
    TraceStorageBackend,
)


# Helpers
def create_sample_span(trace_id="t1", span_id="s1", name="op1", start_offset=0, duration=100):
    start = datetime.now(UTC) + timedelta(milliseconds=start_offset)
    end = start + timedelta(milliseconds=duration)
    return TraceSpan(
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=None,
        name=name,
        kind="INTERNAL",
        start_time=start,
        end_time=end,
        duration_ms=duration,
        service_name="test_service",
        agent_name="test_agent",
        operation="test_op"
    )

def create_sample_trace(trace_id="t1", num_spans=1):
    spans = [create_sample_span(trace_id, f"s{i}", f"op{i}") for i in range(num_spans)]
    start = spans[0].start_time
    end = spans[-1].end_time
    return TraceData(
        trace_id=trace_id,
        root_span_id=spans[0].span_id,
        spans=spans,
        start_time=start,
        end_time=end,
        duration_ms=(end-start).total_seconds()*1000,
        service_count=1,
        total_spans=len(spans),
        status="ok"
    )

@pytest.fixture
def temp_storage_path(tmp_path):
    return tmp_path / "traces"

@pytest.fixture
def file_storage(temp_storage_path):
    return FileTraceStorage(str(temp_storage_path))

@pytest.fixture
def mocked_backend():
    backend = MagicMock(spec=TraceStorageBackend)
    backend.store_trace = AsyncMock(return_value=True)
    backend.get_trace = AsyncMock(return_value=None)
    backend.query_traces = AsyncMock()
    backend.delete_trace = AsyncMock(return_value=True)
    backend.cleanup = AsyncMock(return_value=0)
    backend.retention_days = 30
    return backend

# --- FileTraceStorage Tests ---

@pytest.mark.asyncio
async def test_store_and_get_trace(file_storage):
    """Test full cycle of storing and retrieving a trace."""
    trace = create_sample_trace("trace_123")

    # Store
    success = await file_storage.store_trace(trace)
    assert success

    # Verify file exists
    expected_path = file_storage._get_trace_path("trace_123")
    assert expected_path.exists()

    # Verify index updated
    assert "trace_123" in file_storage.trace_index
    assert file_storage.trace_index["trace_123"]["status"] == "ok"

    # Get
    loaded_trace = await file_storage.get_trace("trace_123")
    assert loaded_trace is not None
    assert loaded_trace.trace_id == "trace_123"
    assert len(loaded_trace.spans) == 1
    assert loaded_trace.spans[0].name == "op0"
    # Basic date continuity check
    assert loaded_trace.start_time.timestamp() == pytest.approx(trace.start_time.timestamp(), 0.001)

@pytest.mark.asyncio
async def test_query_traces_simple(file_storage):
    """Test querying logic using the in-memory index."""
    t1 = create_sample_trace("t1")
    t1.start_time = datetime.now(UTC) - timedelta(hours=1) # Older
    await file_storage.store_trace(t1)

    t2 = create_sample_trace("t2") # Newer
    await file_storage.store_trace(t2)

    # Query all
    query = TraceQuery()
    result = await file_storage.query_traces(query)
    assert result.total_count == 2
    assert len(result.traces) == 2

    # Query specific ID
    q_id = TraceQuery(trace_id="t1")
    r_id = await file_storage.query_traces(q_id)
    assert r_id.total_count == 1
    assert r_id.traces[0].trace_id == "t1"

@pytest.mark.asyncio
async def test_query_traces_time_range(file_storage):
    """Test start/end time filtering."""
    now = datetime.now(UTC)

    t_old = create_sample_trace("old")
    t_old.start_time = now - timedelta(hours=2)
    t_old.spans[0].start_time = t_old.start_time

    t_new = create_sample_trace("new")
    t_new.start_time = now
    t_new.spans[0].start_time = t_new.start_time

    await file_storage.store_trace(t_old)
    await file_storage.store_trace(t_new)

    # Query matching only new
    q = TraceQuery(start_time=now - timedelta(minutes=10))
    res = await file_storage.query_traces(q)

    assert res.total_count == 1
    assert res.traces[0].trace_id == "new"

@pytest.mark.asyncio
async def test_query_traces_sorting(file_storage):
    """Test sorting of results."""
    t1 = create_sample_trace("t1")
    t1.start_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)

    t2 = create_sample_trace("t2")
    t2.start_time = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)

    await file_storage.store_trace(t1)
    await file_storage.store_trace(t2)

    # Descending (default) -> t2, t1
    q_desc = TraceQuery(sort_by="start_time", sort_order="desc")
    res_desc = await file_storage.query_traces(q_desc)
    assert res_desc.traces[0].trace_id == "t2"
    assert res_desc.traces[1].trace_id == "t1"

    # Ascending -> t1, t2
    q_asc = TraceQuery(sort_by="start_time", sort_order="asc")
    res_asc = await file_storage.query_traces(q_asc)
    assert res_asc.traces[0].trace_id == "t1"
    assert res_asc.traces[1].trace_id == "t2"

@pytest.mark.asyncio
async def test_delete_and_cleanup(file_storage):
    """Test deletion and retention cleanup."""
    # 1. Store trace
    await file_storage.store_trace(create_sample_trace("t_del"))
    assert "t_del" in file_storage.trace_index

    # 2. Delete explicitly
    success = await file_storage.delete_trace("t_del")
    assert success
    assert "t_del" not in file_storage.trace_index
    # Verify file gone
    path = file_storage._get_trace_path("t_del")
    assert not path.exists()

    # 3. Cleanup logic
    # Mock index to contain an old trace without actually writing file (cleanup checks index dates)
    file_storage.trace_index["t_old"] = {
        "trace_id": "t_old",
        "start_time": (datetime.now() - timedelta(days=100)).isoformat(),
        "file_path": str(file_storage.storage_path / "dummy.json")
    }

    # We need to mock delete_trace because it tries to delete file based on index path
    with patch.object(file_storage, 'delete_trace', side_effect=file_storage.delete_trace) as mock_del:
        # But wait, the real delete_trace tries to remove the file.
        # Since we didn't create the file for "t_old", os.remove would fail if not guarded.
        # The implementation checks `.exists()`, so it's safe.

        count = await file_storage.cleanup(retention_days=30)
        assert count == 1
        assert "t_old" not in file_storage.trace_index

@pytest.mark.asyncio
async def test_stats(file_storage):
    """Test stats generation."""
    t1 = create_sample_trace("t1", num_spans=5)
    await file_storage.store_trace(t1)

    stats = await file_storage.get_stats()
    assert stats.total_traces == 1
    assert stats.total_spans == 5
    assert stats.storage_size_bytes > 0

# --- TraceStorage Facade Tests ---

@pytest.mark.asyncio
async def test_facade_store_failover(mocked_backend):
    """Test facade tries secondary backend if primary fails."""
    failing_backend = MagicMock(spec=TraceStorageBackend)
    failing_backend.store_trace = AsyncMock(side_effect=Exception("DB Error"))

    # Facade with [Fail, OK]
    storage = TraceStorage(backends=[failing_backend, mocked_backend])

    success = await storage.store_trace(create_sample_trace("t1"))

    assert success
    failing_backend.store_trace.assert_called_once()
    mocked_backend.store_trace.assert_called_once()

@pytest.mark.asyncio
async def test_facade_query_cache(mocked_backend):
    """Test that facade caches query results."""
    from monitoring.core.trace_storage import TraceQueryResult

    # Setup backend to return a result
    mocked_result = TraceQueryResult(total_count=10)
    mocked_backend.query_traces.return_value = mocked_result

    storage = TraceStorage(backends=[mocked_backend])

    q = TraceQuery(service_name="api")

    # 1. First call -> hits backend
    res1 = await storage.query_traces(q)
    assert res1.total_count == 10
    assert mocked_backend.query_traces.call_count == 1

    # 2. Second call -> hits cache
    res2 = await storage.query_traces(q)
    assert res2.total_count == 10
    assert mocked_backend.query_traces.call_count == 1 # Still 1
