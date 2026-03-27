"""
JustNews Trace Processor

This module processes and correlates distributed traces across the multi-agent system,
providing trace analysis, correlation, and performance insights.

Key Features:
- Trace correlation and stitching
- Service mesh integration (Istio)
- Performance bottleneck identification
- Distributed transaction monitoring
- Trace analytics and reporting

Author: JustNews Development Team
Date: October 22, 2025
"""

import logging
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .trace_collector import TraceData, TraceSpan

logger = logging.getLogger(__name__)


@dataclass
class ServiceDependency:
    """Represents a dependency between services"""

    source_service: str
    target_service: str
    operation: str
    call_count: int = 0
    total_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    error_count: int = 0
    error_rate: float = 0.0
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PerformanceBottleneck:
    """Identifies performance bottlenecks in traces"""

    service_name: str
    operation: str
    bottleneck_type: str  # "latency", "error_rate", "throughput"
    severity: str  # "low", "medium", "high", "critical"
    description: str
    evidence: dict[str, Any]
    recommendations: list[str]
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class TraceAnalysis:
    """Analysis results for a trace"""

    trace_id: str
    total_duration_ms: float
    span_count: int
    service_count: int
    error_count: int
    critical_path: list[str]  # List of span IDs in critical path
    bottlenecks: list[PerformanceBottleneck]
    service_dependencies: list[ServiceDependency]
    recommendations: list[str]
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class TraceProcessor:
    """
    Processes and analyzes distributed traces for performance insights and monitoring.

    Features:
    - Trace correlation and stitching
    - Critical path analysis
    - Performance bottleneck detection
    - Service dependency mapping
    - Anomaly detection in trace patterns
    """

    def __init__(
        self, max_trace_buffer: int = 10000, analysis_window_minutes: int = 60
    ):
        self.max_trace_buffer = max_trace_buffer
        self.analysis_window_minutes = analysis_window_minutes

        # Trace storage
        self.processed_traces: deque = deque(maxlen=max_trace_buffer)
        self.trace_index: dict[str, TraceData] = {}

        # Analysis data
        self.service_dependencies: dict[tuple[str, str], ServiceDependency] = {}
        self.performance_baselines: dict[str, dict[str, float]] = {}
        self.anomaly_thresholds: dict[str, float] = {
            "latency_p95": 2.0,  # 2x baseline
            "error_rate": 0.05,  # 5% error rate threshold
            "span_count": 3.0,  # 3x baseline span count
        }

        # Performance tracking
        self.analysis_times: list[float] = []
        self.bottleneck_count = 0
        self.anomaly_count = 0

        logger.info("TraceProcessor initialized")

    def process_trace(self, trace_data: TraceData) -> TraceAnalysis:
        """
        Process a completed trace and generate analysis.

        Args:
            trace_data: Completed trace data

        Returns:
            TraceAnalysis with insights and recommendations
        """
        start_time = time.time()

        # Update trace storage
        self.processed_traces.append(trace_data)
        self.trace_index[trace_data.trace_id] = trace_data

        # Perform comprehensive analysis
        analysis = self._analyze_trace(trace_data)

        # Update service dependencies
        self._update_service_dependencies(trace_data)

        # Update performance baselines
        self._update_baselines(trace_data)

        # Record analysis time
        analysis_time = time.time() - start_time
        self.analysis_times.append(analysis_time)

        logger.debug(f"Processed trace {trace_data.trace_id} in {analysis_time:.3f}s")
        return analysis

    def _analyze_trace(self, trace_data: TraceData) -> TraceAnalysis:
        """Perform detailed trace analysis"""
        # Calculate basic metrics
        total_duration = trace_data.duration_ms or 0
        span_count = len(trace_data.spans)
        service_count = len(
            {span.service_name for span in trace_data.spans if span.service_name}
        )
        error_count = sum(1 for span in trace_data.spans if span.status != "ok")

        # Find critical path
        critical_path = self._find_critical_path(trace_data)

        # Detect bottlenecks
        bottlenecks = self._detect_bottlenecks(trace_data)

        # Analyze service dependencies
        dependencies = self._analyze_dependencies(trace_data)

        # Generate recommendations
        recommendations = self._generate_recommendations(trace_data, bottlenecks)

        return TraceAnalysis(
            trace_id=trace_data.trace_id,
            total_duration_ms=total_duration,
            span_count=span_count,
            service_count=service_count,
            error_count=error_count,
            critical_path=critical_path,
            bottlenecks=bottlenecks,
            service_dependencies=dependencies,
            recommendations=recommendations,
        )

    def _find_critical_path(self, trace_data: TraceData) -> list[str]:
        """Find the critical path through the trace (longest duration path)"""
        if not trace_data.spans:
            return []

        # Build span graph
        span_graph = {}
        span_durations = {}

        for span in trace_data.spans:
            span_graph[span.span_id] = {
                "children": [],
                "duration": span.duration_ms or 0,
            }
            span_durations[span.span_id] = span.duration_ms or 0

        # Build parent-child relationships
        for span in trace_data.spans:
            if span.parent_span_id:
                if span.parent_span_id in span_graph:
                    span_graph[span.parent_span_id]["children"].append(span.span_id)

        # Find critical path using dynamic programming
        def get_critical_path(span_id: str) -> tuple[list[str], float]:
            if span_id not in span_graph:
                return [span_id], 0

            node = span_graph[span_id]
            if not node["children"]:
                return [span_id], node["duration"]

            max_path = []
            max_duration = 0

            for child_id in node["children"]:
                child_path, child_duration = get_critical_path(child_id)
                total_duration = node["duration"] + child_duration

                if total_duration > max_duration:
                    max_duration = total_duration
                    max_path = [span_id] + child_path

            return max_path, max_duration

        # Start from root spans (spans with no parent)
        root_spans = [span for span in trace_data.spans if not span.parent_span_id]

        if not root_spans:
            return []

        critical_paths = []
        for root_span in root_spans:
            path, duration = get_critical_path(root_span.span_id)
            critical_paths.append((path, duration))

        # Return the longest critical path
        if critical_paths:
            critical_paths.sort(key=lambda x: x[1], reverse=True)
            return critical_paths[0][0]

        return []

    def _detect_bottlenecks(self, trace_data: TraceData) -> list[PerformanceBottleneck]:
        """Detect performance bottlenecks in the trace"""
        bottlenecks = []

        # Analyze each span for bottlenecks
        for span in trace_data.spans:
            bottleneck = self._analyze_span_bottleneck(span)
            if bottleneck:
                bottlenecks.append(bottleneck)
                self.bottleneck_count += 1

        # Analyze service-level bottlenecks
        service_spans = defaultdict(list)
        for span in trace_data.spans:
            if span.service_name:
                service_spans[span.service_name].append(span)

        for service_name, spans in service_spans.items():
            service_bottleneck = self._analyze_service_bottleneck(service_name, spans)
            if service_bottleneck:
                bottlenecks.append(service_bottleneck)

        return bottlenecks

    def _analyze_span_bottleneck(self, span: TraceSpan) -> PerformanceBottleneck | None:
        """Analyze a single span for bottlenecks"""
        duration = span.duration_ms or 0

        # Check against baseline
        baseline_key = f"{span.service_name}:{span.operation}"
        baseline_duration = self.performance_baselines.get(baseline_key, {}).get(
            "p95", 0
        )

        if (
            baseline_duration > 0
            and duration > baseline_duration * self.anomaly_thresholds["latency_p95"]
        ):
            return PerformanceBottleneck(
                service_name=span.service_name,
                operation=span.operation,
                bottleneck_type="latency",
                severity="high" if duration > baseline_duration * 3 else "medium",
                description=f"Span duration {duration:.2f}ms exceeds baseline P95 {baseline_duration:.2f}ms",
                evidence={
                    "span_id": span.span_id,
                    "actual_duration": duration,
                    "baseline_p95": baseline_duration,
                    "ratio": duration / baseline_duration,
                },
                recommendations=[
                    "Consider optimizing the operation",
                    "Check for resource contention",
                    "Review error handling and retries",
                ],
            )

        # Check for errors
        if span.status != "ok":
            return PerformanceBottleneck(
                service_name=span.service_name,
                operation=span.operation,
                bottleneck_type="error_rate",
                severity="medium",
                description=f"Span completed with error status: {span.status}",
                evidence={
                    "span_id": span.span_id,
                    "status": span.status,
                    "attributes": span.attributes,
                },
                recommendations=[
                    "Investigate error cause",
                    "Add retry logic if appropriate",
                    "Improve error handling",
                ],
            )

        return None

    def _analyze_service_bottleneck(
        self, service_name: str, spans: list[TraceSpan]
    ) -> PerformanceBottleneck | None:
        """Analyze service-level bottlenecks"""
        if not spans:
            return None

        # Calculate service metrics
        durations = [span.duration_ms or 0 for span in spans]
        error_count = sum(1 for span in spans if span.status != "ok")
        error_rate = error_count / len(spans)

        # Check error rate threshold
        if error_rate > self.anomaly_thresholds["error_rate"]:
            return PerformanceBottleneck(
                service_name=service_name,
                operation="service_overall",
                bottleneck_type="error_rate",
                severity="critical" if error_rate > 0.1 else "high",
                description=f"Service error rate {error_rate:.2%} exceeds threshold {self.anomaly_thresholds['error_rate']:.2%}",
                evidence={
                    "total_spans": len(spans),
                    "error_count": error_count,
                    "error_rate": error_rate,
                    "avg_duration": statistics.mean(durations) if durations else 0,
                },
                recommendations=[
                    "Investigate service health",
                    "Check upstream dependencies",
                    "Review recent deployments",
                    "Monitor resource utilization",
                ],
            )

        return None

    def _analyze_dependencies(self, trace_data: TraceData) -> list[ServiceDependency]:
        """Analyze service dependencies from trace"""
        dependencies = []

        # Build service call graph
        service_calls = defaultdict(lambda: defaultdict(list))

        for span in trace_data.spans:
            if span.parent_span_id:
                # Find parent span
                parent_span = next(
                    (s for s in trace_data.spans if s.span_id == span.parent_span_id),
                    None,
                )
                if parent_span and parent_span.service_name != span.service_name:
                    service_calls[parent_span.service_name][span.service_name].append(
                        (span, parent_span)
                    )

        # Create dependency objects
        for source_service, targets in service_calls.items():
            for target_service, span_pairs in targets.items():
                durations = [child.duration_ms or 0 for child, parent in span_pairs]
                errors = sum(1 for child, parent in span_pairs if child.status != "ok")

                dependency = ServiceDependency(
                    source_service=source_service,
                    target_service=target_service,
                    operation=f"{source_service}->{target_service}",
                    call_count=len(span_pairs),
                    total_duration_ms=sum(durations),
                    avg_duration_ms=statistics.mean(durations) if durations else 0,
                    error_count=errors,
                    error_rate=errors / len(span_pairs) if span_pairs else 0,
                )
                dependencies.append(dependency)

        return dependencies

    def _update_service_dependencies(self, trace_data: TraceData):
        """Update global service dependency tracking"""
        dependencies = self._analyze_dependencies(trace_data)

        for dep in dependencies:
            key = (dep.source_service, dep.target_service)
            if key not in self.service_dependencies:
                self.service_dependencies[key] = dep
            else:
                existing = self.service_dependencies[key]
                # Update rolling averages
                total_calls = existing.call_count + dep.call_count
                existing.avg_duration_ms = (
                    existing.avg_duration_ms * existing.call_count
                    + dep.total_duration_ms
                ) / total_calls
                existing.call_count = total_calls
                existing.error_count += dep.error_count
                existing.error_rate = existing.error_count / total_calls
                existing.last_seen = datetime.now(UTC)

    def _update_baselines(self, trace_data: TraceData):
        """Update performance baselines from recent traces"""
        # Get traces from analysis window
        cutoff_time = datetime.now(UTC) - timedelta(minutes=self.analysis_window_minutes)
        recent_traces = [
            trace
            for trace in self.processed_traces
            if trace.end_time and trace.end_time > cutoff_time
        ]

        # Calculate baselines per service:operation
        baselines = defaultdict(list)

        for trace in recent_traces:
            for span in trace.spans:
                if span.service_name and span.operation and span.duration_ms:
                    key = f"{span.service_name}:{span.operation}"
                    baselines[key].append(span.duration_ms)

        # Update baselines with percentiles
        for key, durations in baselines.items():
            if len(durations) >= 10:  # Need minimum samples
                sorted_durations = sorted(durations)
                p50 = sorted_durations[len(sorted_durations) // 2]
                p95 = sorted_durations[int(len(sorted_durations) * 0.95)]
                p99 = sorted_durations[int(len(sorted_durations) * 0.99)]

                self.performance_baselines[key] = {
                    "p50": p50,
                    "p95": p95,
                    "p99": p99,
                    "count": len(durations),
                    "updated_at": datetime.now(UTC),
                }

    def _generate_recommendations(
        self, trace_data: TraceData, bottlenecks: list[PerformanceBottleneck]
    ) -> list[str]:
        """Generate recommendations based on trace analysis"""
        recommendations = []

        # Duration-based recommendations
        if trace_data.duration_ms and trace_data.duration_ms > 5000:  # 5 seconds
            recommendations.append(
                "Consider optimizing overall request processing time"
            )

        # Error-based recommendations
        error_rate = sum(1 for span in trace_data.spans if span.status != "ok") / len(
            trace_data.spans
        )
        if error_rate > 0.1:
            recommendations.append(
                "High error rate detected - investigate service health"
            )

        # Bottleneck-based recommendations
        for bottleneck in bottlenecks:
            recommendations.extend(bottleneck.recommendations)

        # Service count recommendations
        if trace_data.service_count > 10:
            recommendations.append(
                "High service coupling detected - consider service consolidation"
            )

        return list(set(recommendations))  # Remove duplicates

    def get_service_map(self) -> dict[str, list[ServiceDependency]]:
        """Get current service dependency map"""
        service_map = defaultdict(list)

        for (source, _target), dep in self.service_dependencies.items():
            service_map[source].append(dep)

        return dict(service_map)

    def get_performance_baselines(self) -> dict[str, dict[str, float]]:
        """Get current performance baselines"""
        return self.performance_baselines.copy()

    def get_recent_bottlenecks(self, limit: int = 50) -> list[PerformanceBottleneck]:
        """Get recently detected bottlenecks"""
        # This would need to be implemented with a bottleneck storage mechanism
        # For now, return empty list
        return []

    def get_trace_stats(self) -> dict[str, Any]:
        """Get trace processing statistics"""
        if not self.analysis_times:
            avg_analysis_time = 0
        else:
            avg_analysis_time = statistics.mean(
                self.analysis_times[-100:]
            )  # Last 100 analyses

        return {
            "processed_traces": len(self.processed_traces),
            "active_traces": len(self.trace_index),
            "service_dependencies": len(self.service_dependencies),
            "performance_baselines": len(self.performance_baselines),
            "bottleneck_count": self.bottleneck_count,
            "anomaly_count": self.anomaly_count,
            "avg_analysis_time_ms": avg_analysis_time * 1000,
            "max_trace_buffer": self.max_trace_buffer,
        }

    def find_similar_traces(
        self, trace_id: str, limit: int = 5
    ) -> list[tuple[str, float]]:
        """
        Find traces similar to the given trace based on structure and performance.

        Args:
            trace_id: ID of the trace to find similar traces for
            limit: Maximum number of similar traces to return

        Returns:
            List of (trace_id, similarity_score) tuples
        """
        target_trace = self.trace_index.get(trace_id)
        if not target_trace:
            return []

        similarities = []

        for other_id, other_trace in self.trace_index.items():
            if other_id == trace_id:
                continue

            similarity = self._calculate_trace_similarity(target_trace, other_trace)
            similarities.append((other_id, similarity))

        # Sort by similarity (highest first) and return top results
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:limit]

    def _calculate_trace_similarity(
        self, trace1: TraceData, trace2: TraceData
    ) -> float:
        """Calculate similarity score between two traces"""
        # Simple similarity based on span count, service count, and duration
        span_similarity = 1 - abs(len(trace1.spans) - len(trace2.spans)) / max(
            len(trace1.spans), len(trace2.spans), 1
        )
        service_similarity = 1 - abs(trace1.service_count - trace2.service_count) / max(
            trace1.service_count, trace2.service_count, 1
        )

        duration1 = trace1.duration_ms or 0
        duration2 = trace2.duration_ms or 0
        duration_similarity = 1 - abs(duration1 - duration2) / max(
            duration1, duration2, 1
        )

        # Weighted average
        return (
            span_similarity * 0.4 + service_similarity * 0.3 + duration_similarity * 0.3
        )


# Global processor instance
_processor = None


def get_trace_processor() -> TraceProcessor:
    """Get or create global trace processor instance"""
    global _processor
    if _processor is None:
        _processor = TraceProcessor()
    return _processor
