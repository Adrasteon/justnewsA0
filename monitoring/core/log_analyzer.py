"""
JustNews Log Analyzer

Log analysis and anomaly detection system for JustNews
observability platform.
"""

import logging
import os
import re
import statistics
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from .log_collector import LogEntry, LogLevel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from monitoring.core.log_storage import LogQuery, LogStorage


class AnalysisType(Enum):
    """Types of log analysis"""

    ERROR_RATE_ANALYSIS = "error_rate_analysis"
    PERFORMANCE_ANALYSIS = "performance_analysis"
    ANOMALY_DETECTION = "anomaly_detection"
    PATTERN_RECOGNITION = "pattern_recognition"
    TREND_ANALYSIS = "trend_analysis"


class AnomalyType(Enum):
    """Types of detected anomalies"""

    SPIKE_IN_ERRORS = "spike_in_errors"
    UNUSUAL_TRAFFIC_PATTERN = "unusual_traffic_pattern"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    NEW_ERROR_TYPE = "new_error_type"
    FREQUENT_SIMILAR_ERRORS = "frequent_similar_errors"


@dataclass
class AnalysisResult:
    """Result of log analysis"""

    analysis_type: AnalysisType
    timestamp: datetime
    time_range: tuple[datetime, datetime]
    findings: list[dict[str, Any]]
    anomalies: list[dict[str, Any]]
    recommendations: list[str]
    confidence_score: float


@dataclass
class AnomalyAlert:
    """Anomaly detection alert"""

    anomaly_type: AnomalyType
    severity: str  # "low", "medium", "high", "critical"
    title: str
    description: str
    details: dict[str, Any]
    timestamp: datetime
    confidence_score: float
    affected_components: list[str]


class LogAnalyzer:
    """
    Log analyzer for anomaly detection and pattern recognition.

    Analyzes log data to detect anomalies, performance issues, and provides
    insights for system optimization and troubleshooting.
    """

    def __init__(self, storage: LogStorage, config: dict[str, Any] | None = None):
        self.storage = storage
        self.config = config or self._get_default_config()

        # Analysis state
        self._baseline_metrics: dict[str, Any] = {}
        self._known_error_patterns: set[str] = set()
        self._performance_baselines: dict[str, float] = {}

        # Anomaly detection thresholds
        self._error_rate_threshold = self.config["error_rate_threshold"]
        self._performance_degradation_threshold = self.config[
            "performance_degradation_threshold"
        ]
        self._anomaly_confidence_threshold = self.config["anomaly_confidence_threshold"]

    def _get_default_config(self) -> dict[str, Any]:
        """Get default analyzer configuration"""
        return {
            "analysis_window_hours": 24,
            "baseline_window_days": 7,
            "error_rate_threshold": 0.05,  # 5% error rate
            "performance_degradation_threshold": 0.20,  # 20% degradation
            "anomaly_confidence_threshold": 0.75,
            "min_samples_for_baseline": 10,
            "max_analysis_entries": 10000,
        }

    async def analyze_logs(
        self,
        analysis_type: AnalysisType,
        time_range: tuple[datetime, datetime] | None = None,
    ) -> AnalysisResult:
        """
        Perform comprehensive log analysis

        Args:
            analysis_type: Type of analysis to perform
            time_range: Time range for analysis (default: last 24 hours)

        Returns:
            AnalysisResult with findings and recommendations
        """
        if time_range is None:
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(
                hours=self.config["analysis_window_hours"]
            )
            time_range = (start_time, end_time)

        start_time, end_time = time_range

        try:
            if analysis_type == AnalysisType.ERROR_RATE_ANALYSIS:
                return await self._analyze_error_rates(start_time, end_time)
            elif analysis_type == AnalysisType.PERFORMANCE_ANALYSIS:
                return await self._analyze_performance(start_time, end_time)
            elif analysis_type == AnalysisType.ANOMALY_DETECTION:
                return await self._detect_anomalies(start_time, end_time)
            elif analysis_type == AnalysisType.PATTERN_RECOGNITION:
                return await self._recognize_patterns(start_time, end_time)
            elif analysis_type == AnalysisType.TREND_ANALYSIS:
                return await self._analyze_trends(start_time, end_time)
            else:
                raise ValueError(f"Unsupported analysis type: {analysis_type}")

        except Exception as e:
            logging.error(f"Error performing {analysis_type.value} analysis: {e}")
            return AnalysisResult(
                analysis_type=analysis_type,
                timestamp=datetime.now(UTC),
                time_range=time_range,
                findings=[],
                anomalies=[],
                recommendations=[f"Analysis failed: {str(e)}"],
                confidence_score=0.0,
            )

    async def _analyze_error_rates(
        self, start_time: datetime, end_time: datetime
    ) -> AnalysisResult:
        """Analyze error rates across components"""
        # Query error logs
        error_query = LogQuery(
            filters={"level": "ERROR"},
            time_range=(start_time, end_time),
            limit=self.config["max_analysis_entries"],
        )

        error_result = await self.storage.query_logs(error_query)

        # Query all logs for rate calculation
        all_query = LogQuery(
            time_range=(start_time, end_time), limit=self.config["max_analysis_entries"]
        )

        all_result = await self.storage.query_logs(all_query)

        # Calculate error rates by component
        error_counts = {}
        total_counts = {}

        for entry in error_result.entries:
            component = entry.agent_name or "unknown"
            error_counts[component] = error_counts.get(component, 0) + 1

        for entry in all_result.entries:
            component = entry.agent_name or "unknown"
            total_counts[component] = total_counts.get(component, 0) + 1

        # Calculate rates and identify issues
        findings = []
        anomalies = []
        recommendations = []

        for component, error_count in error_counts.items():
            total_count = total_counts.get(component, 0)
            if total_count > 0:
                error_rate = error_count / total_count

                findings.append(
                    {
                        "component": component,
                        "error_count": error_count,
                        "total_count": total_count,
                        "error_rate": error_rate,
                    }
                )

                # Check against threshold
                if error_rate > self._error_rate_threshold:
                    anomalies.append(
                        {
                            "type": AnomalyType.SPIKE_IN_ERRORS.value,
                            "component": component,
                            "error_rate": error_rate,
                            "threshold": self._error_rate_threshold,
                            "severity": "high" if error_rate > 0.1 else "medium",
                        }
                    )

                    recommendations.append(
                        f"Investigate high error rate ({error_rate:.2%}) in {component}"
                    )

        return AnalysisResult(
            analysis_type=AnalysisType.ERROR_RATE_ANALYSIS,
            timestamp=datetime.now(UTC),
            time_range=(start_time, end_time),
            findings=findings,
            anomalies=anomalies,
            recommendations=recommendations,
            confidence_score=0.9,
        )

    async def _analyze_performance(
        self, start_time: datetime, end_time: datetime
    ) -> AnalysisResult:
        """Analyze system performance from logs"""
        # Query logs with performance data
        perf_query = LogQuery(
            time_range=(start_time, end_time), limit=self.config["max_analysis_entries"]
        )

        result = await self.storage.query_logs(perf_query)

        # Extract performance metrics
        response_times = []
        request_counts = {}
        error_counts = {}

        for entry in result.entries:
            if entry.duration_ms:
                response_times.append(entry.duration_ms)

            if entry.endpoint:
                request_counts[entry.endpoint] = (
                    request_counts.get(entry.endpoint, 0) + 1
                )

            if entry.level in [LogLevel.ERROR, LogLevel.CRITICAL]:
                error_counts[entry.endpoint or "unknown"] = (
                    error_counts.get(entry.endpoint or "unknown", 0) + 1
                )

        # Calculate performance metrics
        findings = []
        anomalies = []
        recommendations = []

        if response_times:
            avg_response_time = statistics.mean(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[
                18
            ]  # 95th percentile

            findings.append(
                {
                    "metric": "average_response_time",
                    "value": avg_response_time,
                    "unit": "ms",
                }
            )

            findings.append(
                {
                    "metric": "p95_response_time",
                    "value": p95_response_time,
                    "unit": "ms",
                }
            )

            # Check for performance degradation
            baseline_avg = self._performance_baselines.get("avg_response_time")
            if baseline_avg and avg_response_time > baseline_avg * (
                1 + self._performance_degradation_threshold
            ):
                anomalies.append(
                    {
                        "type": AnomalyType.PERFORMANCE_DEGRADATION.value,
                        "metric": "average_response_time",
                        "current_value": avg_response_time,
                        "baseline_value": baseline_avg,
                        "degradation_percent": (
                            (avg_response_time - baseline_avg) / baseline_avg
                        )
                        * 100,
                        "severity": "high",
                    }
                )

                recommendations.append(
                    f"Investigate performance degradation: response time increased by {((avg_response_time - baseline_avg) / baseline_avg) * 100:.1f}%"
                )

            # Update baseline
            self._performance_baselines["avg_response_time"] = avg_response_time

        # Analyze endpoint performance
        for endpoint, count in request_counts.items():
            findings.append({"endpoint": endpoint, "request_count": count})

        return AnalysisResult(
            analysis_type=AnalysisType.PERFORMANCE_ANALYSIS,
            timestamp=datetime.now(UTC),
            time_range=(start_time, end_time),
            findings=findings,
            anomalies=anomalies,
            recommendations=recommendations,
            confidence_score=0.85,
        )

    async def _detect_anomalies(
        self, start_time: datetime, end_time: datetime
    ) -> AnalysisResult:
        """Detect anomalies in log patterns"""
        # Query recent logs
        query = LogQuery(
            time_range=(start_time, end_time), limit=self.config["max_analysis_entries"]
        )

        result = await self.storage.query_logs(query)

        anomalies = []
        recommendations = []

        # Detect unusual error patterns
        error_patterns = self._extract_error_patterns(result.entries)

        for pattern, count in error_patterns.items():
            if pattern not in self._known_error_patterns:
                # New error pattern detected
                anomalies.append(
                    {
                        "type": AnomalyType.NEW_ERROR_TYPE.value,
                        "pattern": pattern,
                        "occurrences": count,
                        "severity": "medium",
                        "first_seen": start_time.isoformat(),
                    }
                )

                recommendations.append(
                    f"Investigate new error pattern: {pattern} (occurred {count} times)"
                )

                # Add to known patterns
                self._known_error_patterns.add(pattern)

        # Detect frequent similar errors
        similar_errors = self._find_similar_errors(result.entries)
        for error_group, count in similar_errors.items():
            if count > 5:  # Threshold for frequent errors
                anomalies.append(
                    {
                        "type": AnomalyType.FREQUENT_SIMILAR_ERRORS.value,
                        "error_group": error_group,
                        "occurrences": count,
                        "severity": "medium",
                    }
                )

                recommendations.append(
                    f"Address frequent error group: {error_group} (occurred {count} times)"
                )

        # Detect unusual traffic patterns
        traffic_patterns = self._analyze_traffic_patterns(result.entries)
        for pattern, deviation in traffic_patterns.items():
            if deviation > 2.0:  # 2 standard deviations
                anomalies.append(
                    {
                        "type": AnomalyType.UNUSUAL_TRAFFIC_PATTERN.value,
                        "pattern": pattern,
                        "deviation": deviation,
                        "severity": "low",
                    }
                )

        findings = [
            {"anomaly_type": a["type"], "count": len(anomalies)} for a in anomalies
        ]

        return AnalysisResult(
            analysis_type=AnalysisType.ANOMALY_DETECTION,
            timestamp=datetime.now(UTC),
            time_range=(start_time, end_time),
            findings=findings,
            anomalies=anomalies,
            recommendations=recommendations,
            confidence_score=0.8,
        )

    async def _recognize_patterns(
        self, start_time: datetime, end_time: datetime
    ) -> AnalysisResult:
        """Recognize patterns in log data"""
        query = LogQuery(
            time_range=(start_time, end_time), limit=self.config["max_analysis_entries"]
        )

        result = await self.storage.query_logs(query)

        # Extract patterns
        patterns = self._extract_log_patterns(result.entries)

        findings = []
        for pattern, info in patterns.items():
            findings.append(
                {
                    "pattern": pattern,
                    "frequency": info["frequency"],
                    "avg_interval": info["avg_interval"],
                    "components": list(info["components"]),
                }
            )

        return AnalysisResult(
            analysis_type=AnalysisType.PATTERN_RECOGNITION,
            timestamp=datetime.now(UTC),
            time_range=(start_time, end_time),
            findings=findings,
            anomalies=[],
            recommendations=["Patterns identified for monitoring and alerting"],
            confidence_score=0.75,
        )

    async def _analyze_trends(
        self, start_time: datetime, end_time: datetime
    ) -> AnalysisResult:
        """Analyze trends in log data over time"""
        # This would implement time-series analysis
        # For now, return basic trend information

        findings = [
            {"trend": "error_rate_trend", "direction": "stable", "confidence": 0.6},
            {"trend": "performance_trend", "direction": "improving", "confidence": 0.7},
        ]

        return AnalysisResult(
            analysis_type=AnalysisType.TREND_ANALYSIS,
            timestamp=datetime.now(UTC),
            time_range=(start_time, end_time),
            findings=findings,
            anomalies=[],
            recommendations=[
                "Continue monitoring trends for optimization opportunities"
            ],
            confidence_score=0.7,
        )

    def _extract_error_patterns(self, entries: list[LogEntry]) -> dict[str, int]:
        """Extract error patterns from log entries"""
        patterns = {}

        for entry in entries:
            if entry.level in [LogLevel.ERROR, LogLevel.CRITICAL]:
                # Create pattern from error message
                message = entry.message or ""
                # Simple pattern extraction - could be more sophisticated
                pattern = re.sub(r"\d+", "<NUMBER>", message)
                pattern = re.sub(r"[a-f0-9]{8,}", "<UUID>", pattern)

                patterns[pattern] = patterns.get(pattern, 0) + 1

        return patterns

    def _find_similar_errors(self, entries: list[LogEntry]) -> dict[str, int]:
        """Find groups of similar errors"""
        error_groups = {}

        for entry in entries:
            if entry.level in [LogLevel.ERROR, LogLevel.CRITICAL]:
                # Group by error type and endpoint
                group_key = (
                    f"{entry.error_type or 'unknown'}:{entry.endpoint or 'unknown'}"
                )
                error_groups[group_key] = error_groups.get(group_key, 0) + 1

        return error_groups

    def _analyze_traffic_patterns(self, entries: list[LogEntry]) -> dict[str, float]:
        """Analyze traffic patterns for anomalies"""
        # Simple traffic analysis - count requests per hour
        hourly_counts = {}

        for entry in entries:
            hour = entry.timestamp.strftime("%Y%m%d%H")
            hourly_counts[hour] = hourly_counts.get(hour, 0) + 1

        if len(hourly_counts) < 2:
            return {}

        # Calculate deviations from mean
        counts = list(hourly_counts.values())
        mean_count = statistics.mean(counts)
        std_dev = statistics.stdev(counts) if len(counts) > 1 else 0

        deviations = {}
        for hour, count in hourly_counts.items():
            if std_dev > 0:
                deviation = abs(count - mean_count) / std_dev
                if deviation > 1.5:  # More than 1.5 standard deviations
                    deviations[hour] = deviation

        return deviations

    def _extract_log_patterns(
        self, entries: list[LogEntry]
    ) -> dict[str, dict[str, Any]]:
        """Extract recurring patterns from logs"""
        patterns = {}

        # Simple pattern extraction based on message similarity
        for entry in entries:
            # Create pattern key from message structure
            message = entry.message or ""
            pattern_key = re.sub(r"\w+", "<WORD>", message)
            pattern_key = re.sub(r"\d+", "<NUMBER>", pattern_key)

            if pattern_key not in patterns:
                patterns[pattern_key] = {
                    "frequency": 0,
                    "timestamps": [],
                    "components": set(),
                }

            patterns[pattern_key]["frequency"] += 1
            patterns[pattern_key]["timestamps"].append(entry.timestamp)
            patterns[pattern_key]["components"].add(entry.agent_name or "unknown")

        # Calculate intervals for frequent patterns
        for pattern_info in patterns.values():
            timestamps = sorted(pattern_info["timestamps"])
            if len(timestamps) > 1:
                intervals = [
                    (timestamps[i + 1] - timestamps[i]).total_seconds()
                    for i in range(len(timestamps) - 1)
                ]
                pattern_info["avg_interval"] = (
                    statistics.mean(intervals) if intervals else 0
                )
            else:
                pattern_info["avg_interval"] = 0

        return patterns

    async def generate_anomaly_alerts(
        self, analysis_result: AnalysisResult
    ) -> list[AnomalyAlert]:
        """Generate anomaly alerts from analysis results"""
        alerts = []

        for anomaly in analysis_result.anomalies:
            alert = AnomalyAlert(
                anomaly_type=AnomalyType(anomaly["type"]),
                severity=anomaly.get("severity", "medium"),
                title=f"Anomaly Detected: {anomaly['type'].replace('_', ' ').title()}",
                description=self._generate_anomaly_description(anomaly),
                details=anomaly,
                timestamp=datetime.now(UTC),
                confidence_score=analysis_result.confidence_score,
                affected_components=[anomaly.get("component", "unknown")],
            )
            alerts.append(alert)

        return alerts

    def _generate_anomaly_description(self, anomaly: dict[str, Any]) -> str:
        """Generate human-readable anomaly description"""
        anomaly_type = anomaly.get("type")

        if anomaly_type == AnomalyType.SPIKE_IN_ERRORS.value:
            return f"Error rate spike detected in {anomaly.get('component', 'unknown')}: {anomaly.get('error_rate', 0):.2%} (threshold: {anomaly.get('threshold', 0):.2%})"

        elif anomaly_type == AnomalyType.PERFORMANCE_DEGRADATION.value:
            degradation = anomaly.get("degradation_percent", 0)
            return f"Performance degradation detected: {degradation:.1f}% increase in {anomaly.get('metric', 'unknown')}"

        elif anomaly_type == AnomalyType.NEW_ERROR_TYPE.value:
            return f"New error pattern detected: {anomaly.get('pattern', 'unknown')} (occurrences: {anomaly.get('occurrences', 0)})"

        elif anomaly_type == AnomalyType.FREQUENT_SIMILAR_ERRORS.value:
            return f"Frequent similar errors: {anomaly.get('error_group', 'unknown')} (occurrences: {anomaly.get('occurrences', 0)})"

        elif anomaly_type == AnomalyType.UNUSUAL_TRAFFIC_PATTERN.value:
            return f"Unusual traffic pattern detected: {anomaly.get('pattern', 'unknown')} (deviation: {anomaly.get('deviation', 0):.1f}σ)"

        else:
            return f"Anomaly detected: {anomaly_type}"

    async def update_baselines(self, time_range_days: int = 7) -> None:
        """Update baseline metrics for anomaly detection"""
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=time_range_days)

        # Update error rate baselines
        error_query = LogQuery(
            filters={"level": "ERROR"}, time_range=(start_time, end_time), limit=1000
        )

        error_result = await self.storage.query_logs(error_query)
        if len(error_result.entries) >= self.config["min_samples_for_baseline"]:
            self._baseline_metrics["avg_daily_errors"] = (
                len(error_result.entries) / time_range_days
            )

        # Update performance baselines
        perf_query = LogQuery(time_range=(start_time, end_time), limit=1000)

        perf_result = await self.storage.query_logs(perf_query)
        response_times = [
            entry.duration_ms
            for entry in perf_result.entries
            if entry.duration_ms is not None
        ]

        if len(response_times) >= self.config["min_samples_for_baseline"]:
            self._performance_baselines["avg_response_time"] = statistics.mean(
                response_times
            )

    async def get_analysis_status(self) -> dict[str, Any]:
        """Get analyzer status and metrics"""
        return {
            "baseline_metrics_count": len(self._baseline_metrics),
            "known_error_patterns_count": len(self._known_error_patterns),
            "performance_baselines_count": len(self._performance_baselines),
            "analysis_config": self.config,
        }


# Global analyzer instance
_global_analyzer: LogAnalyzer | None = None


def get_log_analyzer(
    storage: LogStorage | None = None, config: dict[str, Any] | None = None
) -> LogAnalyzer:
    """Get or create global log analyzer"""
    global _global_analyzer

    if _global_analyzer is None:
        if storage is None:
            from monitoring.core.log_storage import get_log_storage

            storage = get_log_storage()
        _global_analyzer = LogAnalyzer(storage, config)

    return _global_analyzer


def init_log_analysis(
    storage: LogStorage | None = None, config: dict[str, Any] | None = None
) -> LogAnalyzer:
    """Initialize log analysis system"""
    analyzer = LogAnalyzer(storage, config)
    global _global_analyzer
    _global_analyzer = analyzer
    return analyzer
