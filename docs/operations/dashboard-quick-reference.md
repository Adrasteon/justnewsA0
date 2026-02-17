# JustNews Operations Dashboard Quick Reference

## Overview

The JustNews Operations Dashboard provides comprehensive monitoring of the entire JustNews platform, including content
processing, system resources, and GPU utilization. This guide helps you quickly understand and navigate the dashboard.

## Dashboard Access

- **URL**: `http://127.0.0.1:3000/d/ef37elu2756o0e/justnews-operations-dashboard`

- **Refresh Rate**: 30 seconds

- **Time Range**: Last 1 hour (configurable)

## Dashboard Layout

### Row 1: Content Processing Metrics (4 panels)

| Panel | Metric | Description | Normal Range | |-------|--------|-------------|--------------| | **Domains Crawled** |
`justnews_crawler_scheduler_domains_crawled_total` | Total domains processed by scheduler | Increases over time | |
**Articles Accepted** | `justnews_crawler_scheduler_articles_accepted_total` | Articles accepted during crawl windows |
Increases over time | | **Adaptive Articles** | `justnews_crawler_scheduler_adaptive_articles_total` | Articles from
adaptive Crawl4AI pipeline | Increases over time | | **Scheduler Lag** | `justnews_crawler_scheduler_lag_seconds` |
Delay between scheduled and actual crawl start | < 300 seconds |

### Row 2: Application Health & Requests (4 panels)

| Panel | Metric | Description | Normal Range | |-------|--------|-------------|--------------| | **Crawler Requests** |
`rate(justnews_requests_total{agent="crawler"}[5m])` | Request rate over time (time series) | 0-50 req/min | | **Active
Connections** | `justnews_active_connections` | Current active connections | 0-10 | | **Total Errors** |
`justnews_errors_total` | Total system errors | Low, increasing slowly | | **Avg Request Duration** |
`avg(justnews_request_duration_seconds_sum / justnews_request_duration_seconds_count)` | Average request processing time
| < 2 seconds |

### Row 3: System Load & Duration (2 panels)

| Panel | Metric | Description | Normal Range | |-------|--------|-------------|--------------| | **System Load (1m)** |
`node_load1` | 1-minute system load average | < CPU cores | | **Avg Request Duration** | (continued) | Average request
processing time | < 2 seconds |

### Row 4: Hardware Resources (4 panels)

| Panel | Metric | Description | Normal Range | |-------|--------|-------------|--------------| | **CPU Usage** | `100 -
(avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)` | CPU utilization percentage | < 80% | | **Memory Usage** |
`(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100` | Memory utilization percentage | < 85% | |
**Disk Usage** | `(1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100`
| Root filesystem usage | < 90% | | **Network I/O** | `rate(node_network_receive_bytes_total[5m])` /
`rate(node_network_transmit_bytes_total[5m])` | Network traffic rates | Variable |

### Row 5: GPU Monitoring (6 panels)

| Panel | Metric | Description | Normal Range | |-------|--------|-------------|--------------| | **GPU Utilization** |
`nvidia_gpu_utilization_ratio * 100` | GPU processing utilization | 0-100% | | **GPU Memory Usage** |
`nvidia_gpu_memory_utilization_ratio * 100` | GPU memory utilization | 0-100% | | **GPU Temperature** |
`nvidia_gpu_temperature_celsius`| GPU temperature | 30-80°C | | **GPU Power Draw** |`nvidia_gpu_power_draw_watts` |
Current power consumption | 50-350W | | **GPU Memory Details** | Memory totals in GB (table) | Total/Used/Free memory |
Model dependent | | **GPU Utilization Over Time** | Utilization trends (time series) | Historical GPU usage | Variable |

## Panel Types

- **Stat**: Single value with optional sparkline

- **Gauge**: Circular gauge with thresholds (green/yellow/red)

- **Table**: Tabular data display

- **Time Series**: Line graphs over time with legends

## Color Coding

- **Green**: Normal operation

- **Yellow**: Warning threshold (typically 70-80%)

- **Red**: Critical threshold (typically >80-90%)

## Common Issues & Solutions

### No Data Showing

- Check Prometheus: `http://localhost:9090/targets`

- Verify services: `systemctl status justnews-prometheus justnews-grafana`

- Check GPU exporter: `curl <http://localhost:9400/health`>

### GPU Metrics Missing

- Verify GPU exporter running: `ps aux | grep gpu_metrics_exporter`

- Check NVIDIA drivers: `nvidia-smi`

- Restart exporter: `cd ${SERVICE_DIR:-$HOME/JustNews} && python3 gpu_metrics_exporter.py &`

### High Resource Usage

- **CPU > 80%**: Check system load, consider scaling

- **Memory > 85%**: Monitor for memory leaks, check swap usage

- **GPU > 90%**: May indicate processing bottleneck or overload

- **Disk > 90%**: Clean up logs/data, consider expansion

## Alert Thresholds

| Metric | Warning | Critical | Action | |--------|---------|----------|--------| | CPU Usage | > 70% | > 85% | Check
processes, consider scaling | | Memory Usage | > 75% | > 90% | Monitor applications, check for leaks | | GPU Utilization
| > 80% | > 95% | Check workload distribution | | GPU Temperature | > 75°C | > 85°C | Check cooling, reduce load | |
Disk Usage | > 80% | > 95% | Clean up space, plan expansion | | Scheduler Lag | > 300s | > 600s | Check crawler
performance |

## Customization

### Time Range

- Click time picker in top-right

- Common ranges: Last 1 hour, 6 hours, 24 hours, 7 days

### Panel Refresh

- Auto-refresh every 30 seconds

- Manual refresh with 🔄 button

- Pause auto-refresh for detailed analysis

### Panel Zoom

- Click panel title to view full screen

- Use time brush to zoom into specific time ranges

## Export & Sharing

- **Export Dashboard**: Dashboard settings → Export

- **Share Panel**: Panel menu → Share → Link

- **Snapshot**: Dashboard settings → Snapshot (static view)

## Related Documentation

- [Systemd Monitoring Setup](systemd-monitoring.md)

- [GPU Monitoring Guide](gpu-monitoring.md)

- [Monitoring Architecture](../../monitoring/README.md)

---

*Dashboard Version: 2.0 | Last Updated: November 5, 2025*
