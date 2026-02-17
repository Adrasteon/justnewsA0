from __future__ import annotations

from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Histogram


@dataclass
class StageBMetrics:
    registry: CollectorRegistry | None
    extraction_total: Counter
    extraction_fallback_total: Counter
    ingestion_total: Counter
    embedding_total: Counter
    embedding_latency_seconds: Histogram
    editorial_total: Counter
    editorial_acceptance: Histogram
    publishing_total: Counter
    publishing_latency_seconds: Histogram

    def record_extraction(self, result: str) -> None:
        self.extraction_total.labels(result=result).inc()

    def record_fallback(self, fallback: str, outcome: str) -> None:
        self.extraction_fallback_total.labels(fallback=fallback, outcome=outcome).inc()

    def record_ingestion(self, status: str) -> None:
        self.ingestion_total.labels(status=status).inc()

    def get_extraction_count(self, result: str) -> float:
        return self.extraction_total.labels(result=result)._value.get()

    def get_fallback_count(self, fallback: str, outcome: str) -> float:
        return self.extraction_fallback_total.labels(
            fallback=fallback, outcome=outcome
        )._value.get()

    def get_ingestion_count(self, status: str) -> float:
        return self.ingestion_total.labels(status=status)._value.get()

    def record_embedding(self, status: str) -> None:
        self.embedding_total.labels(status=status).inc()

    def get_embedding_count(self, status: str) -> float:
        return self.embedding_total.labels(status=status)._value.get()

    def observe_embedding_latency(self, cache: str, seconds: float) -> None:
        self.embedding_latency_seconds.labels(cache=cache).observe(seconds)

    def get_embedding_latency_sum(self, cache: str) -> float:
        return self.embedding_latency_seconds.labels(cache=cache)._sum.get()

    def record_editorial_result(self, result: str) -> None:
        self.editorial_total.labels(result=result).inc()

    def get_editorial_count(self, result: str) -> float:
        return self.editorial_total.labels(result=result)._value.get()

    def record_publish_result(self, result: str) -> None:
        """Record a publish outcome (success/failure)."""
        self.publishing_total.labels(result=result).inc()

    def observe_publish_latency(self, seconds: float) -> None:
        """Observe publish latency in seconds."""
        self.publishing_latency_seconds.observe(max(0.0, float(seconds)))

    def observe_editorial_acceptance(self, score: float) -> None:
        self.editorial_acceptance.observe(max(0.0, min(score, 1.0)))

    def get_editorial_acceptance_sum(self) -> float:
        return self.editorial_acceptance._sum.get()


_metric_registry_map: dict[int, StageBMetrics] = {}
_default_metrics = StageBMetrics(
    registry=None,
    extraction_total=Counter(
        "justnews_stage_b_extraction_articles_total",
        "Count of extraction outcomes produced by the Stage B pipeline.",
        ["result"],
    ),
    extraction_fallback_total=Counter(
        "justnews_stage_b_extraction_fallback_total",
        "Count of fallback extractor utilisation (used vs attempted).",
        ["fallback", "outcome"],
    ),
    ingestion_total=Counter(
        "justnews_stage_b_ingestion_articles_total",
        "Count of ingestion outcomes during Stage B article storage.",
        ["status"],
    ),
    embedding_total=Counter(
        "justnews_stage_b_embedding_total",
        "Count of embedding generation outcomes during Stage B ingestion.",
        ["status"],
    ),
    embedding_latency_seconds=Histogram(
        "justnews_stage_b_embedding_latency_seconds",
        "Latency for embedding generation during Stage B ingestion.",
        ["cache"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    ),
    editorial_total=Counter(
        "justnews_stage_b_editorial_harness_total",
        "Count of editorial harness outcomes (accepted, needs_followup, error).",
        ["result"],
    ),
    editorial_acceptance=Histogram(
        "justnews_stage_b_editorial_acceptance",
        "Acceptance score distribution produced by the editorial harness.",
        buckets=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
    ),
    publishing_total=Counter(
        "justnews_stage_b_publishing_total",
        "Count of publishing outcomes (success/failure) during Stage B flow.",
        ["result"],
    ),
    publishing_latency_seconds=Histogram(
        "justnews_stage_b_publishing_latency_seconds",
        "Latency of publishing operations in seconds.",
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    ),
)
_active_metrics: StageBMetrics = _default_metrics


def _build_metrics(registry: CollectorRegistry | None) -> StageBMetrics:
    return StageBMetrics(
        registry=registry,
        extraction_total=Counter(
            "justnews_stage_b_extraction_articles_total",
            "Count of extraction outcomes produced by the Stage B pipeline.",
            ["result"],
            registry=registry,
        ),
        extraction_fallback_total=Counter(
            "justnews_stage_b_extraction_fallback_total",
            "Count of fallback extractor utilisation (used vs attempted).",
            ["fallback", "outcome"],
            registry=registry,
        ),
        ingestion_total=Counter(
            "justnews_stage_b_ingestion_articles_total",
            "Count of ingestion outcomes during Stage B article storage.",
            ["status"],
            registry=registry,
        ),
        embedding_total=Counter(
            "justnews_stage_b_embedding_total",
            "Count of embedding generation outcomes during Stage B ingestion.",
            ["status"],
            registry=registry,
        ),
        embedding_latency_seconds=Histogram(
            "justnews_stage_b_embedding_latency_seconds",
            "Latency for embedding generation during Stage B ingestion.",
            ["cache"],
            registry=registry,
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        ),
        editorial_total=Counter(
            "justnews_stage_b_editorial_harness_total",
            "Count of editorial harness outcomes (accepted, needs_followup, error).",
            ["result"],
            registry=registry,
        ),
        editorial_acceptance=Histogram(
            "justnews_stage_b_editorial_acceptance",
            "Acceptance score distribution produced by the editorial harness.",
            registry=registry,
            buckets=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        ),
        publishing_total=Counter(
            "justnews_stage_b_publishing_total",
            "Count of publishing outcomes (success/failure) during Stage B flow.",
            ["result"],
            registry=registry,
        ),
        publishing_latency_seconds=Histogram(
            "justnews_stage_b_publishing_latency_seconds",
            "Latency of publishing operations in seconds.",
            registry=registry,
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        ),
    )


def configure_stage_b_metrics(registry: CollectorRegistry) -> StageBMetrics:
    global _active_metrics
    key = id(registry)
    metrics = _metric_registry_map.get(key)
    if metrics is None:
        metrics = _build_metrics(registry)
        _metric_registry_map[key] = metrics
    _active_metrics = metrics
    return metrics


def use_default_stage_b_metrics() -> StageBMetrics:
    global _active_metrics
    _active_metrics = _default_metrics
    return _active_metrics


def set_active_stage_b_metrics(metrics: StageBMetrics) -> None:
    global _active_metrics
    _active_metrics = metrics


def get_stage_b_metrics() -> StageBMetrics:
    return _active_metrics
