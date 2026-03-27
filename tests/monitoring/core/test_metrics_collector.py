from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from prometheus_client import CollectorRegistry

from monitoring.core.metrics_collector import (
    Alert,
    AlertRule,
    AlertSeverity,
    EnhancedMetricsCollector,
    MetricThreshold,
)


# Test Fixture for collector
@pytest.fixture
def registry():
    return CollectorRegistry()

@pytest.fixture
def collector(registry):
    # Mock JustNewsMetrics inside implementation or patch it if strictly needed
    # The class under test imports it.
    with patch("monitoring.core.metrics_collector.JustNewsMetrics") as MockBase:
        # We need the registry passed to JustNewsMetrics to be available
        MockBase.return_value.registry = registry
        col = EnhancedMetricsCollector("test_agent", registry=registry)
        yield col

@pytest.mark.asyncio
async def test_initialization(collector, registry):
    """Test that metrics are initialized and registered correctly."""
    assert collector.agent_name == "test_agent"

    # Check if a metric exists in registry
    assert registry.get_sample_value(
        "justnews_throughput_rate_per_second",
        labels={"agent": "test_agent", "operation_type": "unknown"}
    ) is None # Shouldn't have value yet, but checking existence via internal dicts is better

    # Check internal references
    assert collector.throughput_rate is not None
    assert collector.operation_latency is not None
    assert collector.health_score is not None

@pytest.mark.asyncio
async def test_update_system_metrics(collector):
    """Test system metric updates with mocked psutil."""
    with patch("psutil.Process") as mock_process, \
         patch("psutil.virtual_memory") as mock_vm, \
         patch("psutil.cpu_percent") as mock_cpu, \
         patch("psutil.disk_io_counters") as mock_disk, \
         patch("psutil.net_io_counters") as mock_net:

        # Setup mocks
        mock_process.return_value.memory_info.return_value.rss = 1024 * 1024 * 100 # 100MB
        mock_vm.return_value.total = 1024 * 1024 * 1000 # 1000MB (10% pressure)
        mock_cpu.return_value = [10.0, 20.0] # 2 cores
        mock_disk.return_value.read_bytes = 500
        mock_disk.return_value.write_bytes = 600
        mock_net.return_value.bytes_sent = 1000
        mock_net.return_value.bytes_recv = 2000

        # Execute
        await collector._update_system_metrics()

        # Verify Metrics
        # Memory pressure
        val = collector.memory_pressure.labels(agent="test_agent", memory_pool="process").collect()[0].samples[0].value
        assert val == 10.0

        # CPU
        # Note: cpu_percent returns a list, the implementation iterates it
        val = collector.resource_utilization.labels(agent="test_agent", resource_type="cpu", resource_name="core_0").collect()[0].samples[0].value
        assert val == 10.0

@pytest.mark.asyncio
async def test_record_performance_metric(collector):
    """Test recording performance metrics updates histogram and baseline."""
    collector.record_performance_metric("db_query", 0.5, "database")

    # Check Histogram
    samples = collector.operation_latency.collect()[0].samples
    # Filter for sum
    sum_sample = next(s for s in samples if s.name.endswith("_sum"))
    assert sum_sample.value == 0.5

    # Check baseline (simple moving average logic)
    assert collector._performance_baselines["db_query"] == 0.5

    # Second update
    collector.record_performance_metric("db_query", 0.1, "database")
    # New baseline = 0.1 * 0.1 + 0.9 * 0.5 = 0.01 + 0.45 = 0.46
    assert abs(collector._performance_baselines["db_query"] - 0.46) < 0.001

@pytest.mark.asyncio
async def test_record_business_metric(collector):
    """Test recording business metrics updates history and counters."""
    collector.record_business_metric("content_processed", 1.0, {"content_type": "article", "stage": "ingest"})

    # Check history
    assert "content_processed" in collector._metric_history
    assert len(collector._metric_history["content_processed"]) == 1
    assert collector._metric_history["content_processed"][0][1] == 1.0

    # Check Counter
    val = collector.content_processed_total.labels(agent="test_agent", content_type="article", processing_stage="ingest").collect()[0].samples[0].value
    assert val == 1.0

@pytest.mark.asyncio
async def test_anomaly_detection(collector):
    """Test anomaly detection logic."""
    # Setup history with low variance
    history = []
    for _ in range(25):
        history.append((datetime.now(UTC), 10.0))

    collector._metric_history["test_metric"] = history
    collector._anomaly_thresholds["test_metric"] = 3.0 # 3 sigma

    # Mock trigger
    collector._trigger_anomaly_alert = AsyncMock()

    # Case 1: No anomaly (value 10.0 matches avg 10.0)
    await collector._check_anomalies()
    collector._trigger_anomaly_alert.assert_not_called()

    # Case 2: Anomaly (value 20.0 is way off standard deviation of 0 - effectively triggers if std_dev > 0)
    # The existing implementation requires std_dev > 0.
    # Let's add some noise so std_dev is positive
    history_noisy = []
    for i in range(25):
        val = 10.0 + (0.1 if i % 2 == 0 else -0.1)
        history_noisy.append((datetime.now(UTC), val))

    # Add a massive spike at the end
    history_noisy.append((datetime.now(UTC), 50.0))

    collector._metric_history["test_metric"] = history_noisy

    await collector._check_anomalies()
    collector._trigger_anomaly_alert.assert_called_once()

    # Verify args
    args = collector._trigger_anomaly_alert.call_args
    assert args[0][0] == "test_metric" # metric_name
    assert args[0][1] == 50.0 # current value

@pytest.mark.asyncio
async def test_alert_lifecycle(collector):
    """Test manual triggering and resolving of alerts."""

    # Setup handler
    handler_mock = AsyncMock()
    collector.add_alert_handler(handler_mock)

    rule = AlertRule(
        name="test_rule",
        metric_name="cpu",
        thresholds=MetricThreshold(warning_threshold=80, critical_threshold=90),
        description="CPU High",
        severity=AlertSeverity.WARNING,
        labels={"host": "localhost"}
    )

    # Trigger alert directly via internal method (simulating rule evaluation)
    await collector._trigger_alert(rule, AlertSeverity.WARNING, 85.0, 80.0)

    # Check Active
    active_alerts = collector.get_active_alerts()
    assert len(active_alerts) == 1
    assert active_alerts[0].rule_name == "test_rule"
    assert active_alerts[0].severity == AlertSeverity.WARNING

    # Check Handler called
    handler_mock.assert_called_once()

    # Resolve
    alert_key = f"{rule.name}_{AlertSeverity.WARNING.value}"
    collector.resolve_alert(alert_key)

    # Check Resolved status
    alerts_after = collector.get_active_alerts()
    assert alerts_after[0].resolved is True
    assert alerts_after[0].resolved_at is not None

@pytest.mark.asyncio
async def test_start_stop_monitoring(collector):
    """Test start and stop of background tasks."""

    with patch.object(collector, "_monitoring_loop") as mock_mon, \
         patch.object(collector, "_alerting_loop") as mock_alert, \
         patch.object(collector, "_cleanup_loop") as mock_clean:

        mock_mon.return_value = None # Return coroutine result

        await collector.start_monitoring()

        assert collector._monitoring_task is not None
        assert collector._alerting_task is not None
        assert collector._cleanup_task is not None

        await collector.stop_monitoring()

        assert collector._monitoring_task.cancelled() or collector._monitoring_task.done()

# Cleanup loop test
@pytest.mark.asyncio
async def test_cleanup_loop(collector):
    # Manually populate old data
    collector._custom_metrics = {} # Not used in cleanup

    # Add old valid alert
    old_resolved_alert = Alert(
        rule_name="old", severity=AlertSeverity.INFO, message="old",
        value=1, threshold=1, timestamp=datetime(2020, 1, 1, tzinfo=UTC),
        resolved=True, resolved_at=datetime(2020, 1, 1, tzinfo=UTC)
    )
    collector._active_alerts["old_info"] = old_resolved_alert

    # Add new active alert
    new_alert = Alert(
        rule_name="new", severity=AlertSeverity.INFO, message="new",
        value=1, threshold=1, timestamp=datetime.now(UTC)
    )
    collector._active_alerts["new_info"] = new_alert

    await collector._cleanup_old_data()

    assert "old_info" not in collector._active_alerts
    assert "new_info" in collector._active_alerts
