# GPU Monitoring Guide

This guide provides comprehensive information about the NVIDIA GPU monitoring capabilities integrated into the JustNews
monitoring stack.

## Overview

The JustNews platform includes advanced GPU monitoring that provides real-time insights into NVIDIA GPU performance,
utilization, and health metrics. This enables proactive monitoring of GPU workloads, early detection of performance
issues, and optimization of GPU resource usage.

## Architecture

### Components

1. **GPU Metrics Exporter** (`gpu_metrics_exporter.py`)

- Custom Python-based exporter using NVIDIA Management Library (NVML) via `nvidia-smi`

- HTTP server exposing Prometheus-formatted metrics on port 9400

- Automatic background operation with health checks

1. **Prometheus Integration**

- GPU exporter added to scrape targets

- 15-second scrape interval for real-time monitoring

- Metrics stored with full retention policy

1. **Grafana Visualization**

- 6 dedicated GPU panels in JustNews Operations Dashboard

- Real-time gauges, stats, tables, and time series charts

- Color-coded thresholds for easy issue identification

## GPU Metrics Available

### Core Metrics

| Metric Name | Type | Description | Units | |-------------|------|-------------|-------| | `nvidia_gpu_count` | Gauge |
Number of GPUs detected in the system | count | | `nvidia_gpu_utilization_ratio` | Gauge | GPU utilization as a ratio |
0-1 | | `nvidia_gpu_memory_utilization_ratio` | Gauge | GPU memory utilization as a ratio | 0-1 | |
`nvidia_gpu_temperature_celsius`| Gauge | GPU temperature | Celsius | |`nvidia_gpu_power_draw_watts` | Gauge | Current
power consumption | Watts | | `nvidia_gpu_power_limit_watts` | Gauge | Configured power limit | Watts | |
`nvidia_gpu_fan_speed_ratio`| Gauge | Fan speed as a ratio | 0-1 | |`nvidia_gpu_memory_total_bytes` | Gauge | Total
GPU memory | Bytes | | `nvidia_gpu_memory_used_bytes` | Gauge | Used GPU memory | Bytes | |
`nvidia_gpu_memory_free_bytes` | Gauge | Free GPU memory | Bytes |

### Derived Metrics

Additional metrics can be calculated from the core metrics:

```promql

## GPU utilization percentage

nvidia_gpu_utilization_ratio * 100

## Memory usage percentage

nvidia_gpu_memory_utilization_ratio * 100

## Memory used in GB

nvidia_gpu_memory_used_bytes / (1024*1024*1024)

## Power efficiency (utilization vs power draw)

nvidia_gpu_utilization_ratio / nvidia_gpu_power_draw_watts

```

## Dashboard Panels

The JustNews Operations Dashboard includes 6 GPU monitoring panels:

### 1. GPU Utilization (Gauge)

- **Metric**: `nvidia_gpu_utilization_ratio * 100`

- **Purpose**: Shows current GPU processing utilization

- **Thresholds**: Green (<60%), Yellow (60-80%), Red (>80%)

- **Refresh**: Real-time

### 2. GPU Memory Usage (Gauge)

- **Metric**: `nvidia_gpu_memory_utilization_ratio * 100`

- **Purpose**: Displays GPU memory utilization

- **Thresholds**: Green (<70%), Yellow (70-90%), Red (>90%)

- **Refresh**: Real-time

### 3. GPU Temperature (Stat)

- **Metric**: `nvidia_gpu_temperature_celsius`

- **Purpose**: Current GPU temperature monitoring

- **Units**: Celsius

- **Typical Range**: 30-80°C depending on load

### 4. GPU Power Draw (Stat)

- **Metric**: `nvidia_gpu_power_draw_watts`

- **Purpose**: Real-time power consumption

- **Units**: Watts

- **Typical Range**: 50-350W depending on GPU model

### 5. GPU Memory Details (Table)

- **Metrics**: Total, Used, Free memory in GB

- **Purpose**: Detailed memory breakdown

- **Format**: Human-readable (GB)

- **Update**: Every 15 seconds

### 6. GPU Utilization Over Time (Time Series)

- **Metrics**: GPU utilization % and Memory utilization %

- **Purpose**: Historical trends and patterns

- **Time Range**: Last 1 hour (configurable)

- **Resolution**: 15-second intervals

## Installation and Setup

### Prerequisites

- NVIDIA GPU with drivers installed

- `nvidia-smi` command available

- Python 3.6+ with `subprocess`and`http.server` modules

- Network access for Prometheus scraping

### Automatic Setup

The GPU monitoring is automatically configured when the monitoring stack is installed. The setup includes:

1. **GPU Exporter Deployment**

```bash
cd ${SERVICE_DIR:-$HOME/JustNews}
python3 gpu_metrics_exporter.py &
```

1. **Prometheus Configuration**

```yaml

- job_name: nvidia-gpu-exporter
static_configs:

      - targets: ['127.0.0.1:9400']
metrics_path: /metrics
```

1. **Grafana Dashboard**

- Automatically provisioned from `monitoring/dashboards/generated/`

- 6 GPU panels integrated into JustNews Operations Dashboard

### Manual Verification

```bash

## Check GPU exporter health

curl <http://localhost:9400/health>

## View raw GPU metrics

curl <http://localhost:9400/metrics> | head -20

## Verify Prometheus scraping

curl <http://localhost:9090/api/v1/query?query=nvidia_gpu_count>

## Access dashboard

open <http://localhost:3000/d/ef37elu2756o0e/justnews-operations-dashboard>

```

## Performance Characteristics

### Resource Usage

- **Memory Footprint**: <50MB for exporter process

- **CPU Utilization**: <1% additional system load

- **Network Traffic**: Minimal (<1KB per scrape)

- **Update Frequency**: 5-second internal polling, 15-second Prometheus scraping

### Latency

- **Metrics Collection**: <5ms per GPU query

- **HTTP Response**: <10ms for /metrics endpoint

- **Prometheus Ingestion**: <50ms end-to-end

- **Dashboard Update**: <3 seconds for visualization

## Troubleshooting

### Common Issues

#### GPU Exporter Not Starting

```bash

## Check NVIDIA drivers

nvidia-smi --query-gpu=name --format=csv,noheader

## Verify Python environment

python3 --version

## Check for port conflicts

netstat -tlnp | grep 9400

```bash

#### Metrics Showing "No Data"

```bash

## Check exporter health

curl <http://localhost:9400/health>

## Verify metrics endpoint

curl <http://localhost:9400/metrics> | grep nvidia_gpu

## Check Prometheus targets

curl <http://localhost:9090/api/v1/targets> | jq '.data.activeTargets[] | select(.labels.job == "nvidia-gpu-exporter")'

```

#### GPU Temperature Not Available

Some GPU models don't report temperature via nvidia-smi:

```bash

## Check what metrics are available

nvidia-smi --query-gpu=temperature.gpu --format=csv

## Alternative: Use NVML if available (install the maintained nvidia-ml-py package)

pip install nvidia-ml-py

```bash

#### High Memory Usage

The exporter is lightweight, but monitor system resources:

```bash

## Check exporter process

ps aux | grep gpu_metrics_exporter

## Monitor memory usage

free -h

```

### Log Analysis

```bash

## Check exporter logs (if running in foreground)

python3 gpu_metrics_exporter.py

## System logs for GPU issues

dmesg | grep -i nvidia
journalctl -u nvidia-persistenced

```bash

## Advanced Configuration

### Custom Metrics Collection

Modify `gpu_metrics_exporter.py` to add custom metrics:

```python

## Add custom metric

output.append(f'custom_gpu_metric{{{labels}}} {custom_value}')

```

### Alerting Rules

Example Prometheus alerting rules for GPU monitoring:

```yaml
groups:

  - name: gpu_alerts
    rules:

      - alert: GPUUtilizationHigh
        expr: nvidia_gpu_utilization_ratio > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "GPU utilization is high"
          description: "GPU utilization is {{ $value | humanizePercentage }}"

      - alert: GPUTemperatureCritical
        expr: nvidia_gpu_temperature_celsius > 85
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "GPU temperature is critical"
          description: "GPU temperature is {{ $value }}°C"

```bash

### Multi-GPU Support

The exporter automatically detects and monitors all GPUs:

```bash

## Check number of GPUs

curl <http://localhost:9090/api/v1/query?query=nvidia_gpu_count>

## Query specific GPU (if multiple)

curl <http://localhost:9090/api/v1/query?query=nvidia_gpu_utilization_ratio{gpu="1"}>

```

## Integration with JustNews Agents

GPU metrics are particularly valuable for monitoring:

- **GPU Orchestrator**: Track GPU lease allocation and utilization

- **Model Training**: Monitor GPU usage during training jobs

- **Inference Services**: Track GPU utilization for content processing

- **Resource Optimization**: Identify underutilized GPUs for better allocation

## Future Enhancements

### Planned Features

- **NVML Integration**: Direct NVML library usage for enhanced metrics

- **GPU Process Tracking**: Per-process GPU utilization

- **Historical Analysis**: Long-term GPU performance trends

- **Predictive Alerts**: ML-based anomaly detection for GPU metrics

- **Multi-GPU Optimization**: Advanced multi-GPU workload balancing

### Custom Dashboards

Create specialized GPU dashboards for different use cases:

- **Training Dashboard**: Focus on model training GPU usage

- **Inference Dashboard**: Monitor real-time inference performance

- **Resource Planning**: Capacity planning and optimization insights

## Support and Resources

### Documentation Links

- [NVIDIA System Management Interface](https://developer.nvidia.com/nvidia-system-management-interface)

- [Prometheus Monitoring](https://prometheus.io/docs/)

- [Grafana Dashboards](https://grafana.com/docs/grafana/latest/dashboards/)

### Community Resources

- [NVIDIA GPU Monitoring Best Practices](https://docs.nvidia.com/deploy/driver-persistence/index.html)

- [Prometheus Exporter Guidelines](https://prometheus.io/docs/instrumenting/writing_exporters/)

---

*Last updated: November 5, 2025* *GPU Monitoring Version: 1.0*
