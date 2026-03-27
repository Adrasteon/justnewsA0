from datetime import UTC, datetime, timedelta

import pytest

from monitoring.core.trace_collector import TraceData, TraceSpan
from monitoring.core.trace_processor import (
    TraceAnalysis,
    TraceProcessor,
)


@pytest.fixture
def processor():
    return TraceProcessor(max_trace_buffer=100, analysis_window_minutes=60)

@pytest.fixture
def sample_trace_span():
    def _create_span(
        span_id="span-1",
        parent_span_id=None,
        service_name="test-service",
        operation="test-op",
        duration_ms=100.0,
        status="ok",
        start_time=None
    ):
        if start_time is None:
            start_time = datetime.now(UTC)

        return TraceSpan(
            trace_id="trace-1",
            span_id=span_id,
            parent_span_id=parent_span_id,
            name=operation,
            kind="INTERNAL",
            service_name=service_name,
            operation=operation,
            start_time=start_time,
            end_time=start_time + timedelta(milliseconds=duration_ms),
            duration_ms=duration_ms,
            status=status,
            attributes={},
            events=[]
        )
    return _create_span

@pytest.fixture
def sample_trace_data(sample_trace_span):
    def _create_trace(
        trace_id="trace-1",
        spans=None,
        duration_ms=200.0
    ):
        if spans is None:
            spans = [sample_trace_span()]

        start_time = datetime.now(UTC)
        return TraceData(
            trace_id=trace_id,
            root_span_id=spans[0].span_id if spans else "root",
            spans=spans,
            start_time=start_time,
            end_time=start_time + timedelta(milliseconds=duration_ms),
            duration_ms=duration_ms,
            service_count=len({s.service_name for s in spans}),
            total_spans=len(spans),
            error_count=sum(1 for s in spans if s.status != "ok"),
            status="active"
        )
    return _create_trace

class TestTraceProcessor:

    def test_initialization(self, processor):
        assert processor.max_trace_buffer == 100
        assert len(processor.processed_traces) == 0

    def test_process_trace_basic(self, processor, sample_trace_data):
        trace = sample_trace_data()
        analysis = processor.process_trace(trace)

        assert isinstance(analysis, TraceAnalysis)
        assert analysis.trace_id == trace.trace_id
        assert processor.trace_index.get(trace.trace_id) == trace
        assert len(processor.processed_traces) == 1

    def test_critical_path(self, processor, sample_trace_data, sample_trace_span):
        # A -> B
        start = datetime.now(UTC)
        span_a = sample_trace_span(
            span_id="A",
            duration_ms=100.0,
            start_time=start
        )
        span_b = sample_trace_span(
            span_id="B",
            parent_span_id="A",
            duration_ms=50.0,
            start_time=start + timedelta(milliseconds=20)
        )

        trace = sample_trace_data(spans=[span_a, span_b])

        # In this simple case, A wraps B. Does critical path imply strict parent-child accumulation?
        # The logic in trace_processor uses specific graph traversal.
        # path(A) = A + max(path(children))
        # path(B) = B
        # duration = duration(A) + duration(B) = 100 + 50 = 150
        # If A completely encloses B, typically we sum unique time or just longest path in dag.
        # The code implementation sums durations along the path: total_duration = node["duration"] + child_duration

        # Verify
        path = processor._find_critical_path(trace)
        # Expected: A, B
        assert path == ["A", "B"]

    def test_detect_bottlenecks_latency(self, processor, sample_trace_data, sample_trace_span):
        # Setup baseline
        processor.performance_baselines["test-service:test-op"] = {
            "p95": 100.0,
            "count": 10
        }

        # Trace with high latency (350ms > 2*100ms threshold)
        span = sample_trace_span(duration_ms=350.0)
        trace = sample_trace_data(spans=[span])

        bottlenecks = processor._detect_bottlenecks(trace)
        assert len(bottlenecks) > 0
        assert bottlenecks[0].bottleneck_type == "latency"
        assert bottlenecks[0].severity == "high" # 350 > 3*100

    def test_analyze_dependencies(self, processor, sample_trace_data, sample_trace_span):
        # Service A -> Service B
        span_a = sample_trace_span(span_id="A", service_name="ServiceA")
        span_b = sample_trace_span(span_id="B", parent_span_id="A", service_name="ServiceB")

        trace = sample_trace_data(spans=[span_a, span_b])

        dependencies = processor._analyze_dependencies(trace)
        assert len(dependencies) == 1
        assert dependencies[0].source_service == "ServiceA"
        assert dependencies[0].target_service == "ServiceB"
        assert dependencies[0].call_count == 1

    def test_update_baselines(self, processor, sample_trace_data, sample_trace_span):
        # Add a bunch of traces to calc P95
        durations = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200]
        for d in durations:
            trace = sample_trace_data(spans=[sample_trace_span(duration_ms=float(d))], duration_ms=float(d))
            processor.processed_traces.append(trace)

        # Calling process_trace triggers update, but we added manually.
        # Let's call _update_baselines directly or via process_trace with a dummy one.
        dummy_trace = sample_trace_data()
        processor._update_baselines(dummy_trace)

        baseline = processor.performance_baselines.get("test-service:test-op")
        assert baseline is not None
        assert baseline["count"] >= 10
        # P95 of [10...100, 200] (11 items). 0.95 * 11 = 10.45 -> index 10 -> 200.
        assert baseline["p95"] == 200.0

    def test_find_similar_traces(self, processor, sample_trace_data, sample_trace_span):
        trace1 = sample_trace_data(trace_id="t1", duration_ms=100.0, spans=[sample_trace_span()])
        trace2 = sample_trace_data(trace_id="t2", duration_ms=100.0, spans=[sample_trace_span()])

        processor.trace_index["t1"] = trace1
        processor.trace_index["t2"] = trace2

        similar = processor.find_similar_traces("t1")
        assert len(similar) == 1
        assert similar[0][0] == "t2"
        assert similar[0][1] > 0.9 # Should be very similar

    def test_stats(self, processor):
        stats = processor.get_trace_stats()
        assert "processed_traces" in stats
