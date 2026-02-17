import importlib
from unittest.mock import MagicMock, patch

import pytest

import monitoring.core.custom_metrics
from monitoring.core.metrics_collector import EnhancedMetricsCollector


@pytest.fixture
def mock_collector():
    collector = MagicMock(spec=EnhancedMetricsCollector)
    collector.registry = MagicMock()
    return collector

@pytest.fixture
def custom_metrics_bundle(mock_collector):
    # Patch prometheus_client
    with patch("prometheus_client.Counter") as MockCounter,          patch("prometheus_client.Gauge") as MockGauge,          patch("prometheus_client.Histogram") as MockHistogram:

        mock_metric = MagicMock()
        mock_metric.labels.return_value = MagicMock()

        MockCounter.return_value = mock_metric
        MockGauge.return_value = mock_metric
        MockHistogram.return_value = mock_metric

        # Reload to ensure it picks up patches
        importlib.reload(monitoring.core.custom_metrics)

        # Get the fresh classes
        CustomMetrics = monitoring.core.custom_metrics.CustomMetrics
        ContentType = monitoring.core.custom_metrics.ContentType
        QualityMetric = monitoring.core.custom_metrics.QualityMetric
        ProcessingStage = monitoring.core.custom_metrics.ProcessingStage

        cm = CustomMetrics(agent_name="test_agent", collector=mock_collector)

        # Return bundle
        return cm, ContentType, QualityMetric, ProcessingStage

class TestCustomMetrics:

    def test_record_content_ingestion(self, custom_metrics_bundle, mock_collector):
        cm, ContentType, _, _ = custom_metrics_bundle

        cm.record_content_ingestion(
            ContentType.ARTICLE, "rss", "cnn", "123"
        )

        mock_collector.record_business_metric.assert_called_with(
            "content_ingested",
            1.0,
            {
                "content_type": "article",
                "source_type": "rss",
                "source_name": "cnn",
            }
        )

        cm.content_ingested_total.labels.assert_called_with(
            agent="test_agent",
            content_type="article",
            source_type="rss",
            source_name="cnn"
        )
        cm.content_ingested_total.labels().inc.assert_called()

    def test_record_processing_stage(self, custom_metrics_bundle, mock_collector):
        cm, _, _, ProcessingStage = custom_metrics_bundle

        cm._processing_start_times["123"] = 1000.0

        with patch("time.time", return_value=1001.0):
            cm.record_processing_stage("123", ProcessingStage.ANALYSIS)

        mock_collector.record_performance_metric.assert_called()
        args = mock_collector.record_performance_metric.call_args
        assert args[0][0] == "processing_analysis"
        # duration 1.0

    def test_record_quality_assessment(self, custom_metrics_bundle, mock_collector):
        cm, ContentType, QualityMetric, _ = custom_metrics_bundle

        scores = {QualityMetric.ACCURACY: 0.95}
        cm.record_quality_assessment(ContentType.ARTICLE, scores)

        mock_collector.record_business_metric.assert_called()
        cm.quality_assessment_score.labels.assert_called()
        cm.quality_assessment_score.labels().observe.assert_called_with(0.95)
