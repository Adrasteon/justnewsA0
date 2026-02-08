"""
JustNews Trace Analyzer

This module provides advanced trace analysis capabilities including
performance bottleneck detection, anomaly detection, and trend analysis.

Key Features:
- Performance bottleneck identification
- Anomaly detection in trace patterns
- Trend analysis and forecasting
- Service dependency analysis
- Automated alerting and recommendations

Author: JustNews Development Team
Date: October 22, 2025
"""

import logging
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from .trace_collector import TraceData, TraceSpan
from .trace_processor import TraceAnalysis

logger = logging.getLogger(__name__)


class AnomalyType(Enum):
    """Types of anomalies that can be detected"""

    LATENCY_SPIKE = "latency_spike"
    ERROR_RATE_SPIKE = "error_rate_spike"
    UNUSUAL_PATTERN = "unusual_pattern"
    SERVICE_DEGRADATION = "service_degradation"
    DEPENDENCY_FAILURE = "dependency_failure"


@dataclass
class AnomalyAlert:
    """Represents a detected anomaly"""

    anomaly_id: str
    anomaly_type: AnomalyType
    severity: str  # "low", "medium", "high", "critical"
    description: str
    affected_services: list[str]
    evidence: dict[str, Any]
    recommendations: list[str]
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    status: str = "active"  # "active", "resolved", "acknowledged"


@dataclass
class TrendAnalysis:
    """Analysis of performance trends"""

    metric_name: str
    service_name: str
    time_range: str
    trend_direction: str  # "improving", "degrading", "stable"
    trend_slope: float
    confidence: float
    data_points: list[tuple[datetime, float]]
    forecast: list[tuple[datetime, float]] | None = None
    analysis_date: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ServiceHealthScore:
    """Health score for a service"""

    service_name: str
    overall_score: float  # 0-100
    latency_score: float
    error_score: float
    throughput_score: float
    dependency_score: float
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))
    contributing_factors: dict[str, float] = field(default_factory=dict)


class TraceAnalyzer:
    """
    Advanced trace analyzer for performance insights and anomaly detection.

    Features:
    - Real-time anomaly detection
    - Performance trend analysis
    - Service health scoring
    - Automated bottleneck identification
    - Predictive analytics
    """

    def __init__(
        self, analysis_window_minutes: int = 60, anomaly_sensitivity: float = 0.8
    ):
        self.analysis_window_minutes = analysis_window_minutes
        self.anomaly_sensitivity = anomaly_sensitivity

        # Analysis data
        self.recent_traces: list[TraceData] = []
        self.anomaly_alerts: dict[str, AnomalyAlert] = {}
        self.service_health_scores: dict[str, ServiceHealthScore] = {}
        self.performance_baselines: dict[str, dict[str, float]] = {}

        # Anomaly detection parameters
        self.anomaly_thresholds = {
            "latency_zscore": 3.0,  # Standard deviations
            "error_rate_threshold": 0.05,  # 5% error rate
            "span_count_change": 0.5,  # 50% change in span count
            "dependency_failure_rate": 0.1,  # 10% dependency failure rate
        }

        # Trend analysis
        self.trend_windows = {
            "short": timedelta(minutes=30),
            "medium": timedelta(hours=2),
            "long": timedelta(hours=24),
        }

        logger.info("TraceAnalyzer initialized")

    def analyze_trace(
        self, trace_data: TraceData, trace_analysis: TraceAnalysis
    ) -> list[AnomalyAlert]:
        """
        Analyze a trace for anomalies and performance issues.

        Args:
            trace_data: The trace data to analyze
            trace_analysis: Pre-computed trace analysis

        Returns:
            List of detected anomalies
        """
        anomalies = []

        # Update recent traces buffer
        self._update_recent_traces(trace_data)

        # Detect various types of anomalies
        anomalies.extend(self._detect_latency_anomalies(trace_data))
        anomalies.extend(self._detect_error_anomalies(trace_data))
        anomalies.extend(self._detect_pattern_anomalies(trace_data, trace_analysis))
        anomalies.extend(self._detect_dependency_anomalies(trace_analysis))

        # Update service health scores
        self._update_service_health_scores(trace_data, trace_analysis)

        # Filter and deduplicate anomalies
        unique_anomalies = self._deduplicate_anomalies(anomalies)

        # Store active anomalies
        for anomaly in unique_anomalies:
            self.anomaly_alerts[anomaly.anomaly_id] = anomaly

        return unique_anomalies

    def _update_recent_traces(self, trace_data: TraceData):
        """Update the buffer of recent traces for analysis"""
        self.recent_traces.append(trace_data)

        # Keep only traces within analysis window
        cutoff_time = datetime.now(UTC) - timedelta(minutes=self.analysis_window_minutes)
        self.recent_traces = [
            trace
            for trace in self.recent_traces
            if trace.end_time and trace.end_time > cutoff_time
        ]

        # Limit buffer size
        if len(self.recent_traces) > 1000:
            self.recent_traces = self.recent_traces[-1000:]

    def _detect_latency_anomalies(self, trace_data: TraceData) -> list[AnomalyAlert]:
        """Detect latency-based anomalies"""
        anomalies = []

        for span in trace_data.spans:
            if not span.duration_ms:
                continue

            duration = span.duration_ms
            service_op = f"{span.service_name}:{span.operation}"

            # Get baseline for this service:operation
            baseline = self.performance_baselines.get(service_op, {})
            mean_duration = baseline.get("mean", 0)
            std_duration = baseline.get("std", 1)

            if mean_duration > 0:
                # Calculate z-score
                z_score = abs(duration - mean_duration) / std_duration

                if z_score > self.anomaly_thresholds["latency_zscore"]:
                    severity = "high" if z_score > 4 else "medium"

                    anomaly = AnomalyAlert(
                        anomaly_id=f"latency_{span.span_id}_{int(time.time())}",
                        anomaly_type=AnomalyType.LATENCY_SPIKE,
                        severity=severity,
                        description=f"Latency spike detected for {service_op}: {duration:.2f}ms (z-score: {z_score:.2f})",
                        affected_services=[span.service_name],
                        evidence={
                            "span_id": span.span_id,
                            "service_operation": service_op,
                            "actual_duration": duration,
                            "baseline_mean": mean_duration,
                            "z_score": z_score,
                            "trace_id": trace_data.trace_id,
                        },
                        recommendations=[
                            "Investigate the operation for performance bottlenecks",
                            "Check resource utilization during the time period",
                            "Review recent code changes or deployments",
                        ],
                    )
                    anomalies.append(anomaly)

        return anomalies

    def _detect_error_anomalies(self, trace_data: TraceData) -> list[AnomalyAlert]:
        """Detect error rate anomalies"""
        anomalies = []

        # Group spans by service
        service_spans = defaultdict(list)
        for span in trace_data.spans:
            if span.service_name:
                service_spans[span.service_name].append(span)

        for service_name, spans in service_spans.items():
            error_count = sum(1 for span in spans if span.status != "ok")
            error_rate = error_count / len(spans)

            # Check against baseline
            baseline_key = f"{service_name}:error_rate"
            baseline_error_rate = self.performance_baselines.get(baseline_key, {}).get(
                "mean", 0.01
            )

            if (
                error_rate > self.anomaly_thresholds["error_rate_threshold"]
                and error_rate > baseline_error_rate * 2
            ):
                severity = "critical" if error_rate > 0.2 else "high"

                anomaly = AnomalyAlert(
                    anomaly_id=f"error_rate_{service_name}_{int(time.time())}",
                    anomaly_type=AnomalyType.ERROR_RATE_SPIKE,
                    severity=severity,
                    description=f"Error rate spike for {service_name}: {error_rate:.2%} (baseline: {baseline_error_rate:.2%})",
                    affected_services=[service_name],
                    evidence={
                        "service_name": service_name,
                        "error_rate": error_rate,
                        "baseline_error_rate": baseline_error_rate,
                        "error_count": error_count,
                        "total_spans": len(spans),
                        "trace_id": trace_data.trace_id,
                    },
                    recommendations=[
                        "Check service logs for error details",
                        "Verify upstream service health",
                        "Review recent configuration changes",
                        "Monitor resource constraints",
                    ],
                )
                anomalies.append(anomaly)

        return anomalies

    def _detect_pattern_anomalies(
        self, trace_data: TraceData, trace_analysis: TraceAnalysis
    ) -> list[AnomalyAlert]:
        """Detect unusual patterns in trace structure"""
        anomalies = []

        # Check for unusual span counts
        span_count = len(trace_data.spans)
        baseline_span_count = self.performance_baselines.get(
            "global:span_count", {}
        ).get("mean", 10)

        if baseline_span_count > 0:
            change_ratio = abs(span_count - baseline_span_count) / baseline_span_count

            if change_ratio > self.anomaly_thresholds["span_count_change"]:
                direction = (
                    "increase" if span_count > baseline_span_count else "decrease"
                )

                anomaly = AnomalyAlert(
                    anomaly_id=f"pattern_span_count_{trace_data.trace_id}_{int(time.time())}",
                    anomaly_type=AnomalyType.UNUSUAL_PATTERN,
                    severity="medium",
                    description=f"Unusual span count {direction}: {span_count} spans (baseline: {baseline_span_count})",
                    affected_services=list(
                        {
                            span.service_name
                            for span in trace_data.spans
                            if span.service_name
                        }
                    ),
                    evidence={
                        "trace_id": trace_data.trace_id,
                        "actual_span_count": span_count,
                        "baseline_span_count": baseline_span_count,
                        "change_ratio": change_ratio,
                        "direction": direction,
                    },
                    recommendations=[
                        "Review trace structure for unexpected service calls",
                        "Check for recursive calls or infinite loops",
                        "Validate service integration points",
                    ],
                )
                anomalies.append(anomaly)

        # Check for unusual service involvement
        service_count = trace_data.service_count
        baseline_service_count = self.performance_baselines.get(
            "global:service_count", {}
        ).get("mean", 3)

        if (
            baseline_service_count > 0
            and abs(service_count - baseline_service_count) > 2
        ):
            direction = "more" if service_count > baseline_service_count else "fewer"

            anomaly = AnomalyAlert(
                anomaly_id=f"pattern_service_count_{trace_data.trace_id}_{int(time.time())}",
                anomaly_type=AnomalyType.UNUSUAL_PATTERN,
                severity="low",
                description=f"Unusual service involvement: {service_count} services (baseline: {baseline_service_count})",
                affected_services=list(
                    {
                        span.service_name
                        for span in trace_data.spans
                        if span.service_name
                    }
                ),
                evidence={
                    "trace_id": trace_data.trace_id,
                    "actual_service_count": service_count,
                    "baseline_service_count": baseline_service_count,
                },
                recommendations=[
                    "Verify expected service orchestration",
                    "Check for service discovery issues",
                    "Review request routing logic",
                ],
            )
            anomalies.append(anomaly)

        return anomalies

    def _detect_dependency_anomalies(
        self, trace_analysis: TraceAnalysis
    ) -> list[AnomalyAlert]:
        """Detect anomalies in service dependencies"""
        anomalies = []

        for dependency in trace_analysis.service_dependencies:
            if (
                dependency.error_rate
                > self.anomaly_thresholds["dependency_failure_rate"]
            ):
                anomaly = AnomalyAlert(
                    anomaly_id=f"dependency_{dependency.source_service}_{dependency.target_service}_{int(time.time())}",
                    anomaly_type=AnomalyType.DEPENDENCY_FAILURE,
                    severity="high",
                    description=f"High failure rate in {dependency.source_service} -> {dependency.target_service}: {dependency.error_rate:.2%}",
                    affected_services=[
                        dependency.source_service,
                        dependency.target_service,
                    ],
                    evidence={
                        "source_service": dependency.source_service,
                        "target_service": dependency.target_service,
                        "error_rate": dependency.error_rate,
                        "call_count": dependency.call_count,
                        "error_count": dependency.error_count,
                        "avg_duration_ms": dependency.avg_duration_ms,
                    },
                    recommendations=[
                        f"Investigate {dependency.target_service} health and performance",
                        f"Check network connectivity between {dependency.source_service} and {dependency.target_service}",
                        "Consider implementing circuit breaker pattern",
                        "Review service timeout configurations",
                    ],
                )
                anomalies.append(anomaly)

        return anomalies

    def _update_service_health_scores(
        self, trace_data: TraceData, trace_analysis: TraceAnalysis
    ):
        """Update health scores for services involved in the trace"""
        service_spans = defaultdict(list)
        for span in trace_data.spans:
            if span.service_name:
                service_spans[span.service_name].append(span)

        for service_name, spans in service_spans.items():
            health_score = self._calculate_service_health_score(
                service_name, spans, trace_analysis
            )
            self.service_health_scores[service_name] = health_score

    def _calculate_service_health_score(
        self, service_name: str, spans: list[TraceSpan], trace_analysis: TraceAnalysis
    ) -> ServiceHealthScore:
        """Calculate health score for a service"""
        # Latency score (0-100, higher is better)
        durations = [span.duration_ms for span in spans if span.duration_ms]
        if durations:
            avg_duration = statistics.mean(durations)
            baseline_duration = self.performance_baselines.get(
                f"{service_name}:latency", {}
            ).get("p95", 1000)
            latency_score = max(
                0, min(100, 100 - (avg_duration / baseline_duration) * 100)
            )
        else:
            latency_score = 50  # Neutral score

        # Error score (0-100, higher is better)
        error_count = sum(1 for span in spans if span.status != "ok")
        error_rate = error_count / len(spans) if spans else 0
        error_score = max(0, 100 - (error_rate * 1000))  # Penalize heavily for errors

        # Throughput score (0-100, higher is better)
        throughput_score = min(100, len(spans) * 2)  # Simple throughput indicator

        # Dependency score (0-100, higher is better)
        service_deps = [
            dep
            for dep in trace_analysis.service_dependencies
            if dep.source_service == service_name or dep.target_service == service_name
        ]
        if service_deps:
            avg_dep_error_rate = statistics.mean(dep.error_rate for dep in service_deps)
            dependency_score = max(0, 100 - (avg_dep_error_rate * 1000))
        else:
            dependency_score = 100  # No dependencies = perfect score

        # Overall score (weighted average)
        weights = {"latency": 0.3, "error": 0.4, "throughput": 0.15, "dependency": 0.15}
        overall_score = (
            latency_score * weights["latency"]
            + error_score * weights["error"]
            + throughput_score * weights["throughput"]
            + dependency_score * weights["dependency"]
        )

        return ServiceHealthScore(
            service_name=service_name,
            overall_score=overall_score,
            latency_score=latency_score,
            error_score=error_score,
            throughput_score=throughput_score,
            dependency_score=dependency_score,
            contributing_factors={
                "span_count": len(spans),
                "error_rate": error_rate,
                "avg_duration_ms": statistics.mean(durations) if durations else 0,
            },
        )

    def _deduplicate_anomalies(
        self, anomalies: list[AnomalyAlert]
    ) -> list[AnomalyAlert]:
        """Remove duplicate anomalies based on type and affected services"""
        seen = set()
        unique_anomalies = []

        for anomaly in anomalies:
            # Create a key based on type and services
            key = (anomaly.anomaly_type.value, tuple(sorted(anomaly.affected_services)))

            if key not in seen:
                seen.add(key)
                unique_anomalies.append(anomaly)

        return unique_anomalies

    def update_baselines(self):
        """Update performance baselines from recent traces"""
        if not self.recent_traces:
            return

        # Calculate baselines for different metrics
        new_baselines = {}

        # Global metrics
        all_durations = []
        all_span_counts = []
        all_service_counts = []

        for trace in self.recent_traces:
            if trace.duration_ms:
                all_durations.append(trace.duration_ms)
            all_span_counts.append(len(trace.spans))
            all_service_counts.append(trace.service_count)

        if all_durations:
            new_baselines["global:duration"] = {
                "mean": statistics.mean(all_durations),
                "std": statistics.stdev(all_durations) if len(all_durations) > 1 else 0,
                "p95": sorted(all_durations)[int(len(all_durations) * 0.95)],
            }

        if all_span_counts:
            new_baselines["global:span_count"] = {
                "mean": statistics.mean(all_span_counts),
                "std": statistics.stdev(all_span_counts)
                if len(all_span_counts) > 1
                else 0,
            }

        if all_service_counts:
            new_baselines["global:service_count"] = {
                "mean": statistics.mean(all_service_counts),
                "std": statistics.stdev(all_service_counts)
                if len(all_service_counts) > 1
                else 0,
            }

        # Service-specific metrics
        service_metrics = defaultdict(lambda: defaultdict(list))

        for trace in self.recent_traces:
            for span in trace.spans:
                if span.service_name and span.duration_ms:
                    service_metrics[span.service_name]["durations"].append(
                        span.duration_ms
                    )
                    service_metrics[span.service_name]["operations"].append(
                        span.operation
                    )

        for service_name, metrics in service_metrics.items():
            durations = metrics["durations"]
            if durations:
                new_baselines[f"{service_name}:latency"] = {
                    "mean": statistics.mean(durations),
                    "std": statistics.stdev(durations) if len(durations) > 1 else 0,
                    "p95": sorted(durations)[int(len(durations) * 0.95)],
                }

            # Error rates per service
            service_traces = [
                t
                for t in self.recent_traces
                if any(s.service_name == service_name for s in t.spans)
            ]
            error_rates = []

            for trace in service_traces:
                service_spans = [
                    s for s in trace.spans if s.service_name == service_name
                ]
                if service_spans:
                    error_count = sum(1 for s in service_spans if s.status != "ok")
                    error_rates.append(error_count / len(service_spans))

            if error_rates:
                new_baselines[f"{service_name}:error_rate"] = {
                    "mean": statistics.mean(error_rates),
                    "std": statistics.stdev(error_rates) if len(error_rates) > 1 else 0,
                }

        self.performance_baselines = new_baselines
        logger.info(f"Updated baselines for {len(new_baselines)} metrics")

    def analyze_trends(
        self, service_name: str | None = None, time_window: str = "medium"
    ) -> list[TrendAnalysis]:
        """Analyze performance trends for services"""
        if time_window not in self.trend_windows:
            time_window = "medium"

        window_duration = self.trend_windows[time_window]
        cutoff_time = datetime.now(UTC) - window_duration

        # Collect data points
        trend_data = defaultdict(list)

        for trace in self.recent_traces:
            if not trace.end_time or trace.end_time < cutoff_time:
                continue

            for span in trace.spans:
                if service_name and span.service_name != service_name:
                    continue

                if span.duration_ms:
                    key = f"{span.service_name}:{span.operation}"
                    trend_data[key].append((trace.end_time, span.duration_ms))

        # Analyze trends
        trends = []
        for metric_name, data_points in trend_data.items():
            if len(data_points) < 5:  # Need minimum data points
                continue

            # Sort by time
            data_points.sort(key=lambda x: x[0])

            # Simple linear regression for trend
            x_values = [
                (dt - data_points[0][0]).total_seconds() for dt, _ in data_points
            ]
            y_values = [value for _, value in data_points]

            if len(x_values) > 1:
                slope, intercept = self._linear_regression(x_values, y_values)

                # Determine trend direction
                if slope > 0.1:
                    direction = "degrading"
                elif slope < -0.1:
                    direction = "improving"
                else:
                    direction = "stable"

                # Calculate confidence (R-squared would be better, but this is simpler)
                confidence = min(
                    1.0, len(data_points) / 20.0
                )  # More data points = higher confidence

                trend = TrendAnalysis(
                    metric_name=metric_name,
                    service_name=metric_name.split(":")[0],
                    time_range=time_window,
                    trend_direction=direction,
                    trend_slope=slope,
                    confidence=confidence,
                    data_points=data_points,
                )
                trends.append(trend)

        return trends

    def _linear_regression(
        self, x_values: list[float], y_values: list[float]
    ) -> tuple[float, float]:
        """Simple linear regression implementation"""
        n = len(x_values)
        if n < 2:
            return 0.0, 0.0

        sum_x = sum(x_values)
        sum_y = sum(y_values)
        sum_xy = sum(x * y for x, y in zip(x_values, y_values, strict=True))
        sum_x2 = sum(x * x for x in x_values)

        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return 0.0, sum_y / n

        slope = (n * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / n

        return slope, intercept

    def get_active_anomalies(self) -> list[AnomalyAlert]:
        """Get currently active anomalies"""
        return [
            alert for alert in self.anomaly_alerts.values() if alert.status == "active"
        ]

    def get_service_health_scores(self) -> dict[str, ServiceHealthScore]:
        """Get current service health scores"""
        return self.service_health_scores.copy()

    def resolve_anomaly(self, anomaly_id: str):
        """Mark an anomaly as resolved"""
        if anomaly_id in self.anomaly_alerts:
            self.anomaly_alerts[anomaly_id].resolved_at = datetime.now(UTC)
            self.anomaly_alerts[anomaly_id].status = "resolved"
            logger.info(f"Resolved anomaly: {anomaly_id}")

    def get_stats(self) -> dict[str, Any]:
        """Get analyzer statistics"""
        return {
            "recent_traces_count": len(self.recent_traces),
            "active_anomalies": len(self.get_active_anomalies()),
            "total_anomalies": len(self.anomaly_alerts),
            "service_health_scores": len(self.service_health_scores),
            "performance_baselines": len(self.performance_baselines),
            "analysis_window_minutes": self.analysis_window_minutes,
            "anomaly_sensitivity": self.anomaly_sensitivity,
        }


# Global analyzer instance
_analyzer = None


def get_trace_analyzer() -> TraceAnalyzer:
    """Get or create global trace analyzer instance"""
    global _analyzer
    if _analyzer is None:
        _analyzer = TraceAnalyzer()
    return _analyzer
