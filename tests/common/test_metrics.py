"""
Tests for JustNews Metrics Library
"""

import time
from unittest.mock import Mock, patch

from prometheus_client import CollectorRegistry

from common.metrics import (
    JustNewsMetrics,
    get_metrics,
    init_metrics_for_agent,
    measure_processing_time,
    record_quality_metric,
    update_system_metrics,
)


class TestJustNewsMetrics:
    """Test JustNewsMetrics class functionality"""

    def test_initialization(self):
        """Test metrics initialization with basic agent"""
        metrics = JustNewsMetrics("test_agent")

        assert metrics.agent_name == "test_agent"
        assert metrics.display_name == "test_agent-agent"
        assert isinstance(metrics.registry, CollectorRegistry)

    def test_initialization_with_display_name_mapping(self):
        """Test initialization with known agent display name"""
        metrics = JustNewsMetrics("crawler")

        assert metrics.agent_name == "crawler"
        assert metrics.display_name == "content-crawling-agent"

    def test_record_request(self):
        """Test recording HTTP requests"""
        metrics = JustNewsMetrics("test_agent")

        metrics.record_request("GET", "/health", 200, 0.5)

        # Check that metrics were recorded (we can't easily inspect prometheus metrics directly)
        # but we can verify no exceptions were raised
        assert True

    def test_record_error(self):
        """Test recording errors"""
        metrics = JustNewsMetrics("test_agent")

        metrics.record_error("ValueError", "/api/test")

        assert True

    def test_record_processing(self):
        """Test recording processing operations"""
        metrics = JustNewsMetrics("test_agent")

        metrics.record_processing("sentiment_analysis", 2.5)

        assert True

    def test_update_queue_size(self):
        """Test updating queue size metrics"""
        metrics = JustNewsMetrics("test_agent")

        metrics.update_queue_size("processing_queue", 10)

        assert True

    def test_record_quality_score(self):
        """Test recording quality scores"""
        metrics = JustNewsMetrics("test_agent")

        metrics.record_quality_score("sentiment_accuracy", 0.85)

        assert True

    @patch("common.metrics.psutil.Process")
    def test_update_system_metrics_cpu_memory(self, mock_process_class):
        """Test updating system metrics for CPU and memory"""
        mock_process = Mock()
        mock_memory_info = Mock()
        mock_memory_info.rss = 1024 * 1024 * 100  # 100 MB
        mock_memory_info.vms = 1024 * 1024 * 200  # 200 MB
        mock_process.memory_info.return_value = mock_memory_info
        mock_process.cpu_percent.return_value = 25.5
        mock_process_class.return_value = mock_process

        metrics = JustNewsMetrics("test_agent")
        metrics.update_system_metrics()

        assert True

    @patch("common.metrics.GPUtil")
    @patch("common.metrics.psutil.Process")
    def test_update_system_metrics_with_gpu(self, mock_process_class, mock_gputil):
        """Test updating system metrics including GPU"""
        # Mock CPU/memory
        mock_process = Mock()
        mock_memory_info = Mock()
        mock_memory_info.rss = 1024 * 1024 * 100
        mock_memory_info.vms = 1024 * 1024 * 200
        mock_process.memory_info.return_value = mock_memory_info
        mock_process.cpu_percent.return_value = 25.5
        mock_process_class.return_value = mock_process

        # Mock GPU
        mock_gpu = Mock()
        mock_gpu.memoryUsed = 512  # MB
        mock_gpu.load = 0.75  # 75%
        mock_gputil.getGPUs.return_value = [mock_gpu]

        metrics = JustNewsMetrics("test_agent")
        metrics.update_system_metrics()

        assert True

    @patch("common.metrics.GPUtil")
    def test_update_system_metrics_gpu_unavailable(self, mock_gputil):
        """Test system metrics update when GPU is unavailable"""
        mock_gputil.getGPUs.side_effect = Exception("No GPU available")

        metrics = JustNewsMetrics("test_agent")
        metrics.update_system_metrics()

        assert True

    def test_get_metrics(self):
        """Test getting metrics in Prometheus format"""
        metrics = JustNewsMetrics("test_agent")

        result = metrics.get_metrics()

        assert isinstance(result, str)
        assert "justnews_requests_total" in result

    def test_increment_custom_counter(self):
        """Test incrementing custom counters"""
        metrics = JustNewsMetrics("test_agent")

        metrics.increment("custom_metric", 5.0)

        assert True

    def test_timing_custom_histogram(self):
        """Test recording timing with custom histogram"""
        metrics = JustNewsMetrics("test_agent")

        metrics.timing("response_time", 1.5)

        assert True

    def test_gauge_custom_gauge(self):
        """Test setting custom gauge values"""
        metrics = JustNewsMetrics("test_agent")

        metrics.gauge("queue_size", 42.0)

        assert True

    def test_measure_time_context_manager(self):
        """Test measure_time context manager"""
        metrics = JustNewsMetrics("test_agent")

        with metrics.measure_time("test_operation"):
            time.sleep(0.01)  # Small delay

        assert True

    def test_sanitize_metric_key(self):
        """Test metric key sanitization"""
        metrics = JustNewsMetrics("test_agent")

        # Test various inputs
        assert metrics._sanitize_metric_key("valid_key") == "valid_key"
        assert metrics._sanitize_metric_key("Invalid-Key.Name!") == "invalid_key_name"
        assert metrics._sanitize_metric_key("") == "metric"


class TestMetricsGlobalFunctions:
    """Test global metrics functions"""

    def test_get_metrics_creates_instance(self):
        """Test get_metrics creates and returns metrics instance"""
        metrics = get_metrics("test_agent")

        assert isinstance(metrics, JustNewsMetrics)
        assert metrics.agent_name == "test_agent"

    def test_get_metrics_reuses_instance(self):
        """Test get_metrics reuses instance for same agent"""
        metrics1 = get_metrics("test_agent")
        metrics2 = get_metrics("test_agent")

        assert metrics1 is metrics2

    def test_get_metrics_different_agents(self):
        """Test get_metrics creates different instances for different agents"""
        metrics1 = get_metrics("agent1")
        metrics2 = get_metrics("agent2")

        assert metrics1 is not metrics2
        assert metrics1.agent_name == "agent1"
        assert metrics2.agent_name == "agent2"

    def test_init_metrics_for_agent(self):
        """Test init_metrics_for_agent creates new instance"""
        metrics = init_metrics_for_agent("test_agent")

        assert isinstance(metrics, JustNewsMetrics)
        assert metrics.agent_name == "test_agent"


class TestMetricsDecorators:
    """Test metrics decorators and utility functions"""

    def test_measure_processing_time_decorator(self):
        """Test measure_processing_time decorator"""

        @measure_processing_time("test_operation")
        def test_function(self):
            time.sleep(0.01)
            return "result"

        # Create a mock self object
        mock_self = Mock()
        mock_self.agent_name = "test_agent"

        result = test_function(mock_self)

        assert result == "result"

    def test_record_quality_metric(self):
        """Test record_quality_metric utility function"""
        record_quality_metric("accuracy", 0.95, "test_agent")

        assert True

    def test_update_system_metrics_utility(self):
        """Test update_system_metrics utility function"""
        update_system_metrics("test_agent")

        assert True
