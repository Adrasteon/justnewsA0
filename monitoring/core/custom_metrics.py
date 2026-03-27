"""
Custom Business Metrics for JustNews

Domain-specific metrics for content processing, quality assessment,
fact-checking, and business intelligence.
"""

import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from monitoring.core.metrics_collector import (
    EnhancedMetricsCollector,
    get_enhanced_metrics_collector,
)

logger = logging.getLogger(__name__)


class ContentType(Enum):
    """Types of content processed"""

    ARTICLE = "article"
    NEWS_STORY = "news_story"
    SOCIAL_MEDIA = "social_media"
    BLOG_POST = "blog_post"
    PRESS_RELEASE = "press_release"
    VIDEO_TRANSCRIPT = "video_transcript"
    PODCAST_TRANSCRIPT = "podcast_transcript"


class ProcessingStage(Enum):
    """Content processing stages"""

    INGESTION = "ingestion"
    PREPROCESSING = "preprocessing"
    ANALYSIS = "analysis"
    FACT_CHECKING = "fact_checking"
    SYNTHESIS = "synthesis"
    PUBLISHING = "publishing"


class QualityMetric(Enum):
    """Quality assessment metrics"""

    ACCURACY = "accuracy"
    COMPLETENESS = "completeness"
    TIMELINESS = "timeliness"
    RELEVANCE = "relevance"
    OBJECTIVITY = "objectivity"
    CREDIBILITY = "credibility"


class SentimentType(Enum):
    """Sentiment analysis types"""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


@dataclass
class ContentMetrics:
    """Metrics for content processing"""

    content_id: str
    content_type: ContentType
    source: str
    processing_time: float
    quality_scores: dict[QualityMetric, float]
    word_count: int
    entities_extracted: int
    sentiment: SentimentType
    bias_score: float
    fact_check_result: str
    timestamp: datetime


class CustomMetrics:
    """
    Custom business metrics for JustNews operations.

    Provides domain-specific metrics for content processing, quality assessment,
    and business intelligence.
    """

    def __init__(self, agent_name: str, collector: EnhancedMetricsCollector):
        self.agent_name = agent_name
        self.collector = collector
        self.registry = collector.registry

        # Content processing metrics
        self.content_ingested_total = Counter(
            "justnews_content_ingested_total",
            "Total content items ingested",
            ["agent", "content_type", "source_type", "source_name"],
            registry=self.registry,
        )

        self.content_processing_duration = Histogram(
            "justnews_content_processing_duration_seconds",
            "Content processing duration",
            ["agent", "content_type", "processing_stage"],
            buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0],
            registry=self.registry,
        )

        # Quality assessment metrics
        self.quality_assessment_score = Histogram(
            "justnews_quality_assessment_score",
            "Quality assessment score distribution",
            ["agent", "quality_metric", "content_type"],
            buckets=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            registry=self.registry,
        )

        self.bias_detection_events = Counter(
            "justnews_bias_detection_events_total",
            "Total bias detection events",
            ["agent", "bias_type", "severity", "content_type"],
            registry=self.registry,
        )

        # Fact-checking metrics
        self.fact_checks_performed = Counter(
            "justnews_fact_checks_performed_total",
            "Total fact checks performed",
            ["agent", "check_type", "result", "confidence_level"],
            registry=self.registry,
        )

        self.fact_check_accuracy = Histogram(
            "justnews_fact_check_accuracy",
            "Fact check accuracy distribution",
            ["agent", "verification_method"],
            buckets=[0.0, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0],
            registry=self.registry,
        )

        # Business intelligence metrics
        self.content_engagement_score = Gauge(
            "justnews_content_engagement_score",
            "Content engagement score",
            ["agent", "content_type", "topic_category"],
            registry=self.registry,
        )

        self.news_trend_velocity = Gauge(
            "justnews_news_trend_velocity",
            "News trend velocity (mentions per hour)",
            ["agent", "topic", "trend_direction"],
            registry=self.registry,
        )

        # Performance metrics
        self.processing_throughput = Gauge(
            "justnews_processing_throughput_items_per_minute",
            "Content processing throughput",
            ["agent", "content_type", "processing_stage"],
            registry=self.registry,
        )

        self.queue_backlog = Gauge(
            "justnews_queue_backlog_items",
            "Processing queue backlog",
            ["agent", "queue_type", "priority_level"],
            registry=self.registry,
        )

        # Error and failure metrics
        self.content_processing_failures = Counter(
            "justnews_content_processing_failures_total",
            "Total content processing failures",
            ["agent", "failure_type", "content_type", "processing_stage"],
            registry=self.registry,
        )

        self.quality_assessment_failures = Counter(
            "justnews_quality_assessment_failures_total",
            "Total quality assessment failures",
            ["agent", "failure_reason", "content_type"],
            registry=self.registry,
        )

        # Compliance metrics
        self.gdpr_compliance_checks = Counter(
            "justnews_gdpr_compliance_checks_total",
            "Total GDPR compliance checks",
            ["agent", "check_type", "result"],
            registry=self.registry,
        )

        self.data_retention_actions = Counter(
            "justnews_data_retention_actions_total",
            "Total data retention actions",
            ["agent", "action_type", "data_type"],
            registry=self.registry,
        )

        # Initialize tracking variables
        self._processing_start_times: dict[str, float] = {}
        self._content_metrics_history: list[ContentMetrics] = []
        self._throughput_counters: dict[str, list[tuple[datetime, int]]] = {}

    def record_content_ingestion(
        self,
        content_type: ContentType,
        source_type: str,
        source_name: str,
        content_id: str = None,
    ):
        """Record content ingestion event"""
        self.content_ingested_total.labels(
            agent=self.agent_name,
            content_type=content_type.value,
            source_type=source_type,
            source_name=source_name,
        ).inc()

        # Start processing timer if content_id provided
        if content_id:
            self._processing_start_times[content_id] = time.time()

        # Record in enhanced collector
        self.collector.record_business_metric(
            "content_ingested",
            1.0,
            {
                "content_type": content_type.value,
                "source_type": source_type,
                "source_name": source_name,
            },
        )

    def record_processing_stage(
        self, content_id: str, stage: ProcessingStage, duration: float = None
    ):
        """Record processing stage completion"""
        if duration is None and content_id in self._processing_start_times:
            duration = time.time() - self._processing_start_times[content_id]

        if duration:
            self.content_processing_duration.labels(
                agent=self.agent_name,
                content_type="unknown",  # Would need to be passed or looked up
                processing_stage=stage.value,
            ).observe(duration)

            # Record performance metric
            self.collector.record_performance_metric(
                f"processing_{stage.value}", duration, "content_processing"
            )

    def record_quality_assessment(
        self, content_type: ContentType, quality_scores: dict[QualityMetric, float]
    ):
        """Record quality assessment results"""
        for metric, score in quality_scores.items():
            self.quality_assessment_score.labels(
                agent=self.agent_name,
                quality_metric=metric.value,
                content_type=content_type.value,
            ).observe(score)

            # Record in enhanced collector
            self.collector.record_business_metric(
                "quality_assessment",
                score,
                {"metric": metric.value, "content_type": content_type.value},
            )

    def record_bias_detection(
        self,
        bias_type: str,
        severity: str,
        content_type: ContentType,
        confidence: float,
    ):
        """Record bias detection event"""
        self.bias_detection_events.labels(
            agent=self.agent_name,
            bias_type=bias_type,
            severity=severity,
            content_type=content_type.value,
        ).inc()

        # Record bias score in enhanced collector
        self.collector.record_business_metric(
            "bias_detected",
            confidence,
            {
                "bias_type": bias_type,
                "severity": severity,
                "content_type": content_type.value,
            },
        )

    def record_fact_check(
        self,
        check_type: str,
        result: str,
        confidence: float,
        verification_method: str = "unknown",
    ):
        """Record fact-checking result"""
        self.fact_checks_performed.labels(
            agent=self.agent_name,
            check_type=check_type,
            result=result,
            confidence_level=self._confidence_level(confidence),
        ).inc()

        self.fact_check_accuracy.labels(
            agent=self.agent_name, verification_method=verification_method
        ).observe(confidence)

        # Record in enhanced collector
        self.collector.record_business_metric(
            "fact_check_performed",
            confidence,
            {
                "check_type": check_type,
                "result": result,
                "verification_method": verification_method,
            },
        )

    def record_sentiment_analysis(
        self, sentiment: SentimentType, confidence: float, content_type: ContentType
    ):
        """Record sentiment analysis result"""
        # This would use the existing sentiment_analysis_count metric
        # from the enhanced collector
        self.collector.record_business_metric(
            "sentiment_analysis",
            confidence,
            {"sentiment": sentiment.value, "content_type": content_type.value},
        )

    def update_engagement_score(
        self, content_type: ContentType, topic_category: str, score: float
    ):
        """Update content engagement score"""
        self.content_engagement_score.labels(
            agent=self.agent_name,
            content_type=content_type.value,
            topic_category=topic_category,
        ).set(score)

    def update_news_trend(self, topic: str, velocity: float, direction: str):
        """Update news trend velocity"""
        self.news_trend_velocity.labels(
            agent=self.agent_name, topic=topic, trend_direction=direction
        ).set(velocity)

    def update_processing_throughput(
        self, content_type: ContentType, stage: ProcessingStage, throughput: float
    ):
        """Update processing throughput"""
        self.processing_throughput.labels(
            agent=self.agent_name,
            content_type=content_type.value,
            processing_stage=stage.value,
        ).set(throughput)

        # Track throughput history for trend analysis
        key = f"{content_type.value}_{stage.value}"
        if key not in self._throughput_counters:
            self._throughput_counters[key] = []

        self._throughput_counters[key].append((datetime.now(UTC), throughput))

        # Keep only recent history (last 24 hours)
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        self._throughput_counters[key] = [
            (ts, val) for ts, val in self._throughput_counters[key] if ts > cutoff
        ]

    def update_queue_backlog(self, queue_type: str, priority_level: str, backlog: int):
        """Update queue backlog"""
        self.queue_backlog.labels(
            agent=self.agent_name, queue_type=queue_type, priority_level=priority_level
        ).set(backlog)

    def record_processing_failure(
        self,
        failure_type: str,
        content_type: ContentType,
        stage: ProcessingStage,
        error_details: str = None,
    ):
        """Record processing failure"""
        self.content_processing_failures.labels(
            agent=self.agent_name,
            failure_type=failure_type,
            content_type=content_type.value,
            processing_stage=stage.value,
        ).inc()

        # Log error details if provided
        if error_details:
            logger.error(f"Processing failure: {failure_type} - {error_details}")

    def record_quality_failure(self, failure_reason: str, content_type: ContentType):
        """Record quality assessment failure"""
        self.quality_assessment_failures.labels(
            agent=self.agent_name,
            failure_reason=failure_reason,
            content_type=content_type.value,
        ).inc()

    def record_gdpr_check(self, check_type: str, result: str):
        """Record GDPR compliance check"""
        self.gdpr_compliance_checks.labels(
            agent=self.agent_name, check_type=check_type, result=result
        ).inc()

    def record_data_retention_action(self, action_type: str, data_type: str):
        """Record data retention action"""
        self.data_retention_actions.labels(
            agent=self.agent_name, action_type=action_type, data_type=data_type
        ).inc()

    def record_complete_content_metrics(self, metrics: ContentMetrics):
        """Record complete content processing metrics"""
        # Store in history for analysis
        self._content_metrics_history.append(metrics)

        # Keep only recent history (last 7 days)
        cutoff = datetime.now(UTC) - timedelta(days=7)
        self._content_metrics_history = [
            m for m in self._content_metrics_history if m.timestamp > cutoff
        ]

        # Record individual metrics
        self.record_content_ingestion(
            metrics.content_type, "unknown", metrics.source, metrics.content_id
        )

        quality_scores = dict(metrics.quality_scores)
        self.record_quality_assessment(metrics.content_type, quality_scores)

        self.record_sentiment_analysis(
            metrics.sentiment,
            0.8,
            metrics.content_type,  # Default confidence
        )

        # Record processing time
        self.collector.record_performance_metric(
            "content_processing_complete", metrics.processing_time, "content_processing"
        )

    def get_processing_stats(self, hours: int = 24) -> dict[str, Any]:
        """Get processing statistics for the last N hours"""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        recent_metrics = [
            m for m in self._content_metrics_history if m.timestamp > cutoff
        ]

        if not recent_metrics:
            return {
                "total_processed": 0,
                "avg_processing_time": 0,
                "avg_quality_score": 0,
            }

        total_processed = len(recent_metrics)
        avg_processing_time = (
            sum(m.processing_time for m in recent_metrics) / total_processed
        )

        # Calculate average quality scores
        quality_metrics = {}
        for metric in QualityMetric:
            scores = [
                m.quality_scores.get(metric, 0)
                for m in recent_metrics
                if metric in m.quality_scores
            ]
            if scores:
                quality_metrics[metric.value] = sum(scores) / len(scores)

        avg_quality_score = (
            sum(quality_metrics.values()) / len(quality_metrics)
            if quality_metrics
            else 0
        )

        return {
            "total_processed": total_processed,
            "avg_processing_time": avg_processing_time,
            "avg_quality_score": avg_quality_score,
            "quality_breakdown": quality_metrics,
            "time_range_hours": hours,
        }

    def get_throughput_trends(
        self, content_type: str = None, stage: str = None, hours: int = 24
    ) -> dict[str, Any]:
        """Get throughput trends for the last N hours"""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        trends = {}

        for key, data_points in self._throughput_counters.items():
            if content_type and not key.startswith(content_type):
                continue
            if stage and not key.endswith(stage):
                continue

            recent_points = [(ts, val) for ts, val in data_points if ts > cutoff]
            if len(recent_points) >= 2:
                # Calculate trend (simple linear regression slope)
                times = [
                    (ts - cutoff).total_seconds() / 3600 for ts, _ in recent_points
                ]  # Hours from start
                values = [val for _, val in recent_points]

                if len(times) > 1:
                    slope = self._calculate_trend_slope(times, values)
                    trends[key] = {
                        "current_throughput": values[-1],
                        "trend_slope": slope,
                        "trend_direction": "increasing" if slope > 0 else "decreasing",
                        "data_points": len(recent_points),
                    }

        return trends

    def _confidence_level(self, confidence: float) -> str:
        """Convert confidence score to level"""
        if confidence >= 0.9:
            return "high"
        elif confidence >= 0.7:
            return "medium"
        else:
            return "low"

    def _calculate_trend_slope(
        self, x_values: list[float], y_values: list[float]
    ) -> float:
        """Calculate linear regression slope"""
        if len(x_values) != len(y_values) or len(x_values) < 2:
            return 0.0

        n = len(x_values)
        sum_x = sum(x_values)
        sum_y = sum(y_values)
        sum_xy = sum(x * y for x, y in zip(x_values, y_values, strict=True))
        sum_x2 = sum(x * x for x in x_values)

        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return 0.0

        return (n * sum_xy - sum_x * sum_y) / denominator


# Global custom metrics instances
_custom_metrics_instances: dict[str, CustomMetrics] = {}


def get_custom_metrics(agent_name: str) -> CustomMetrics:
    """Get or create custom metrics for an agent"""
    if agent_name not in _custom_metrics_instances:
        collector = get_enhanced_metrics_collector(agent_name)
        _custom_metrics_instances[agent_name] = CustomMetrics(agent_name, collector)

    return _custom_metrics_instances[agent_name]


def init_custom_metrics_for_agent(agent_name: str) -> CustomMetrics:
    """Initialize custom metrics for a specific agent"""
    collector = get_enhanced_metrics_collector(agent_name)
    metrics = CustomMetrics(agent_name, collector)
    _custom_metrics_instances[agent_name] = metrics
    return metrics
