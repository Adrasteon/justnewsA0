from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from prometheus_client import CollectorRegistry

from monitoring.core.metrics_collector import AlertSeverity, EnhancedMetricsCollector
from monitoring.core.performance_monitor import (
    BottleneckType,
    PerformanceMetric,
    PerformanceMonitor,
    PerformanceSnapshot,
    PerformanceThreshold,
)


# Test Fixture
@pytest.fixture
def collector():
    registry = CollectorRegistry()
    with patch("monitoring.core.metrics_collector.JustNewsMetrics") as MockBase:
        MockBase.return_value.registry = registry
        col = EnhancedMetricsCollector("test_agent", registry=registry)
        # Mock handle_alert to verify alerts being propagated
        col._handle_alert = AsyncMock()
        yield col

@pytest.fixture
def monitor(collector):
    mon = PerformanceMonitor("test_agent", collector)
    yield mon

@pytest.mark.asyncio
async def test_initialization(monitor):
    """Test monitor initialization."""
    assert monitor.agent_name == "test_agent"
    assert monitor._thresholds is not None
    assert PerformanceMetric.CPU_USAGE in monitor._thresholds

    # Check default threshold
    cpu_thresh = monitor._thresholds[PerformanceMetric.CPU_USAGE]
    assert cpu_thresh.warning_threshold == 70.0
    assert cpu_thresh.critical_threshold == 90.0

@pytest.mark.asyncio
async def test_take_performance_snapshot(monitor):
    """Test snapshot creation with mocked psutil."""
    with patch("psutil.cpu_percent") as mock_cpu, \
         patch("psutil.virtual_memory") as mock_mem, \
         patch("psutil.disk_io_counters") as mock_disk, \
         patch("psutil.net_io_counters") as mock_net, \
         patch("psutil.Process") as mock_process:

        # Setup mocks
        mock_cpu.return_value = 50.0
        mock_mem.return_value.percent = 60.0
        mock_disk.return_value.read_bytes = 100
        mock_disk.return_value.write_bytes = 200
        mock_net.return_value.bytes_sent = 300
        mock_net.return_value.bytes_recv = 400

        mock_proc_instance = mock_process.return_value
        mock_proc_instance.num_threads.return_value = 10
        mock_proc_instance.open_files.return_value = ["file1", "file2"]

        await monitor._take_performance_snapshot()

        assert len(monitor._snapshots) == 1
        snap = monitor._snapshots[0]
        assert snap.cpu_percent == 50.0
        assert snap.memory_percent == 60.0
        assert snap.active_threads == 10
        assert snap.open_files == 2

@pytest.mark.asyncio
async def test_detect_bottleneck(monitor):
    """Test bottleneck detection logic."""
    # Case 1: CPU Bottleneck
    snapshots = []
    for _ in range(5):
        s = PerformanceSnapshot(
            timestamp=datetime.now(UTC),
            cpu_percent=90.0, # High CPU
            memory_percent=50.0,
            disk_read_bytes=0, disk_write_bytes=0,
            network_sent_bytes=0, network_recv_bytes=0
        )
        snapshots.append(s)

    analysis = await monitor._detect_bottleneck(snapshots)

    assert analysis is not None
    assert analysis.primary_bottleneck == BottleneckType.CPU_BOUND
    assert analysis.severity == "high"
    assert "algorithms" in analysis.recommendations[1] # Check content of recommendation

    # Case 2: Memory Bottleneck
    snapshots_mem = []
    for _ in range(5):
        s = PerformanceSnapshot(
            timestamp=datetime.now(UTC),
            cpu_percent=10.0,
            memory_percent=95.0, # High Mem
            disk_read_bytes=0, disk_write_bytes=0,
            network_sent_bytes=0, network_recv_bytes=0
        )
        snapshots_mem.append(s)

    analysis_mem = await monitor._detect_bottleneck(snapshots_mem)
    assert analysis_mem.primary_bottleneck == BottleneckType.MEMORY_BOUND

@pytest.mark.asyncio
async def test_update_performance_metrics(monitor, collector):
    """Test updating prometheus metrics."""
    snap = PerformanceSnapshot(
        timestamp=datetime.now(UTC),
        cpu_percent=55.5,
        memory_percent=44.4,
        disk_read_bytes=0, disk_write_bytes=0,
        network_sent_bytes=0, network_recv_bytes=0
    )
    monitor._snapshots.append(snap)

    await monitor._update_performance_metrics()

    # Check collector metrics
    # Resource utilization (CPU)
    val = collector.resource_utilization.labels(agent="test_agent", resource_type="cpu", resource_name="system").collect()[0].samples[0].value
    assert val == 55.5

    # Performance score calculation verification
    # Input stats are all safe/low impact, so score should remain 100
    score_val = monitor.performance_score.labels(agent="test_agent", component="system").collect()[0].samples[0].value
    assert score_val == 100.0

@pytest.mark.asyncio
async def test_calculate_performance_score(monitor):
    """Test score calculation logic."""

    # Perfect scenario
    snap_perfect = PerformanceSnapshot(
        timestamp=datetime.now(UTC),
        cpu_percent=10, memory_percent=10,
        disk_read_bytes=0, disk_write_bytes=0,
        network_sent_bytes=0, network_recv_bytes=0
    )
    assert monitor._calculate_performance_score(snap_perfect) == 100.0

    # Bad CPU
    snap_cpu = PerformanceSnapshot(
        timestamp=datetime.now(UTC),
        cpu_percent=95, # > 90 -> -30
        memory_percent=10,
        disk_read_bytes=0, disk_write_bytes=0,
        network_sent_bytes=0, network_recv_bytes=0
    )
    assert monitor._calculate_performance_score(snap_cpu) == 70.0

    # Bad Memory + Bad CPU
    snap_bad = PerformanceSnapshot(
        timestamp=datetime.now(UTC),
        cpu_percent=95, # -30
        memory_percent=96, # -30
        disk_read_bytes=0, disk_write_bytes=0,
        network_sent_bytes=0, network_recv_bytes=0
    )
    assert monitor._calculate_performance_score(snap_bad) == 40.0

@pytest.mark.asyncio
async def test_check_thresholds_alerts(monitor, collector):
    """Test alert triggering on threshold violation."""

    # Set a sensitive threshold for testing
    monitor.set_threshold(PerformanceMetric.CPU_USAGE, PerformanceThreshold(
        metric=PerformanceMetric.CPU_USAGE,
        warning_threshold=50.0,
        critical_threshold=80.0
    ))

    # Snapshot that triggers WARNING (60 > 50)
    snap = PerformanceSnapshot(
        timestamp=datetime.now(UTC),
        cpu_percent=60.0,
        memory_percent=10.0,
        disk_read_bytes=0, disk_write_bytes=0,
        network_sent_bytes=0, network_recv_bytes=0
    )
    monitor._snapshots.append(snap)

    await monitor._check_thresholds()

    # Verify alert sent to collector
    collector._handle_alert.assert_called_once()
    alert_arg = collector._handle_alert.call_args[0][0]
    assert alert_arg.rule_name == "threshold_cpu_usage"
    assert alert_arg.severity == AlertSeverity.WARNING
    assert alert_arg.value == 60.0

@pytest.mark.asyncio
async def test_analyze_performance_loop(monitor, collector):
    """Test high-level analysis loop triggers."""
    # Populate enough snapshots to trigger analysis
    now = datetime.now(UTC)
    for i in range(5):
        monitor._snapshots.append(PerformanceSnapshot(
            timestamp=now - timedelta(minutes=i),
            cpu_percent=95.0, # High to force bottleneck
            memory_percent=50.0,
            disk_read_bytes=0, disk_write_bytes=0,
            network_sent_bytes=0, network_recv_bytes=0
        ))

    await monitor._analyze_performance()

    # Should trigger bottleneck alert
    collector._handle_alert.assert_called()
    # Looking for a call with "bottleneck_" in rule name
    found = False
    for call in collector._handle_alert.call_args_list:
        if call[0][0].rule_name.startswith("bottleneck_"):
            found = True
            break
    assert found

@pytest.mark.asyncio
async def test_get_performance_report_no_data(monitor):
    """Test report generation with empty data."""
    report = monitor.get_performance_report()
    assert report["status"] == "no_data"

@pytest.mark.asyncio
async def test_get_performance_report_with_data(monitor):
    """Test report generation with data."""
    snap = PerformanceSnapshot(
        timestamp=datetime.now(UTC),
        cpu_percent=50.0, memory_percent=50.0,
        disk_read_bytes=0, disk_write_bytes=0,
        network_sent_bytes=0, network_recv_bytes=0
    )
    monitor._snapshots.append(snap)

    report = monitor.get_performance_report()
    assert report["status"] == "active"
    assert report["sample_count"] == 1
    assert report["cpu_usage"]["avg"] == 50.0
