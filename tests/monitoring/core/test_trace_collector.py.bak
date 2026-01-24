import pytest
from unittest.mock import MagicMock, patch, ANY
import sys
from datetime import datetime, UTC, timedelta

# Mock config and metrics before importing trace_collector to avoid side effects
# configuration is imported inside the module
with patch("config.get_config", return_value={}), \
     patch("common.metrics.JustNewsMetrics"):
     
    from monitoring.core.trace_collector import (
        TraceCollector, 
        TraceContext,
        _OTEL_AVAILABLE
    )

@pytest.fixture
def mock_otel():
    """Mock open telemetry dependencies."""
    with patch("monitoring.core.trace_collector.trace") as mock_trace, \
         patch("monitoring.core.trace_collector.TracerProvider") as mock_provider, \
         patch("monitoring.core.trace_collector.Resource") as mock_resource, \
         patch("monitoring.core.trace_collector._OTEL_AVAILABLE", True):
         
        # Setup tracer mock
        tracer = MagicMock()
        mock_trace.get_tracer.return_value = tracer
        
        # Setup span mock
        span = MagicMock()
        tracer.start_span.return_value = span
        
        # Setup span context
        span_ctx = MagicMock()
        span_ctx.trace_id = 12345678901234567890123456789012
        span_ctx.span_id = 1234567890123456
        span.get_span_context.return_value = span_ctx
        
        # Setup SpanContext constructor mock to return object with accessible span_id
        def SpanContext_mock(trace_id, span_id, is_remote=False):
            m = MagicMock()
            m.trace_id = trace_id
            m.span_id = span_id
            return m
        
        mock_trace.SpanContext.side_effect = SpanContext_mock
        
        yield mock_trace, tracer, span

@pytest.fixture
def collector(mock_otel):
    # Ensure config patch is active during init
    with patch("monitoring.core.trace_collector.get_config", return_value={"tracing": {"jaeger_enabled": False}}), \
         patch("monitoring.core.trace_collector.JustNewsMetrics"):
        return TraceCollector(service_name="test_service")

def test_initialization(collector):
    assert collector.service_name == "test_service"
    assert collector.active_traces == {}
    assert collector.completed_traces == {}

def test_start_trace(collector, mock_otel):
    mock_trace, tracer, span = mock_otel
    
    # Execute
    ctx = collector.start_trace("root_op", attributes={"user": "adra"})
    
    # Verify OTel calls
    tracer.start_span.assert_called_with("root_op", kind=ANY)
    span.set_attribute.assert_any_call("user", "adra")
    span.set_attribute.assert_any_call("trace.root", True)
    
    # Verify Internal State
    assert len(collector.active_traces) == 1
    # Trace ID from mock is hardcoded hex
    tid_hex = hex(12345678901234567890123456789012)[2:]
    assert tid_hex in collector.active_traces
    
    # Verify Return
    assert isinstance(ctx, TraceContext)
    assert ctx.trace_id == tid_hex

def test_start_span_with_parent(collector, mock_otel):
    mock_trace, tracer, span = mock_otel
    
    parent_ctx = TraceContext(trace_id="00000000000000000000000000000001", span_id="0000000000000001")
    
    collector.start_span("child_op", parent_context=parent_ctx)
    
    # Verify start_span called with context
    call_args = tracer.start_span.call_args
    assert call_args[0][0] == "child_op"
    kwargs = call_args[1]
    assert "context" in kwargs
    # We can check specific span context attributes if needed, but existence implies using parent

def test_start_span_no_parent(collector, mock_otel):
    mock_trace, tracer, span = mock_otel
    
    collector.start_span("orphan_op")
    
    tracer.start_span.assert_called_with("orphan_op", kind=ANY)

def test_end_span(collector, mock_otel):
    mock_trace, tracer, span = mock_otel
    
    # trace.get_current_span must return our mock span for end_span logic to trigger
    mock_trace.get_current_span.return_value = span
    
    ctx = TraceContext(trace_id="abc", span_id=hex(1234567890123456)[2:])
    
    collector.end_span(ctx, status="error", attributes={"err.msg": "fail"})
    
    span.set_attribute.assert_called_with("err.msg", "fail")
    span.set_status.assert_called()
    span.end.assert_called()

def test_cleanup_old_traces(collector):
    from monitoring.core.trace_collector import TraceData
    
    # Inject old completed trace
    old_data = TraceData(trace_id="old", root_span_id="1")
    old_data.end_time = datetime.now(UTC) - timedelta(hours=25) # > 24h retention
    
    new_data = TraceData(trace_id="new", root_span_id="2")
    new_data.end_time = datetime.now(UTC) - timedelta(hours=1)
    
    collector.completed_traces["old"] = old_data
    collector.completed_traces["new"] = new_data
    
    # Run cleanup (async method in source?)
    # Looking at source: async def cleanup_old_traces(self):
    import asyncio
    asyncio.run(collector.cleanup_old_traces())
    
    assert "old" not in collector.completed_traces
    assert "new" in collector.completed_traces

def test_otel_unavailable_fallback():
    """Test collector behavior when OTel is not available."""
    
    # Force _OTEL_AVAILABLE = False during init
    with patch("monitoring.core.trace_collector._OTEL_AVAILABLE", False), \
         patch("monitoring.core.trace_collector.get_config", return_value={}), \
         patch("monitoring.core.trace_collector.JustNewsMetrics"):
         
        col = TraceCollector("fallback_service")
        
        # Safe no-ops
        ctx = col.start_trace("test")
        assert ctx.trace_id == "0"
        
        ctx2 = col.start_span("test2")
        assert ctx2.span_id == "0"
        
        # Should not throw
        col.end_span(ctx)
