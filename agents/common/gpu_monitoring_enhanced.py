"""
Enhanced GPU Monitoring Dashboard for JustNews
Provides comprehensive real-time GPU health monitoring and performance analytics

Features:
- Real-time GPU health dashboards
- Performance trend analysis
- Resource utilization alerts
- Historical metrics tracking
- Web-based monitoring interface
- Alert system for GPU issues
"""

import os
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any

import psutil

from common.observability import get_logger

# GPU and ML imports with graceful fallbacks
try:
    import numpy as np
    import torch

    GPU_AVAILABLE = torch.cuda.is_available()
    TORCH_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False
    TORCH_AVAILABLE = False
    torch = None
    np = None

logger = get_logger(__name__)


class GPUMetricsCollector:
    """Collects comprehensive GPU metrics over time"""

    def __init__(self, max_history: int = 1000, collection_interval: float = 10.0):
        self.max_history = max_history
        self.collection_interval = collection_interval

        # Historical data storage
        self.metrics_history: dict[str, deque] = {
            "gpu_utilization": deque(maxlen=max_history),
            "gpu_memory_used": deque(maxlen=max_history),
            "gpu_memory_free": deque(maxlen=max_history),
            "gpu_temperature": deque(maxlen=max_history),
            "gpu_power_draw": deque(maxlen=max_history),
            "agent_allocations": deque(maxlen=max_history),
            "timestamps": deque(maxlen=max_history),
        }

        # Current state
        self.current_metrics = {}
        self.collection_thread: threading.Thread | None = None
        self.running = False

        # Alert thresholds
        self.alert_thresholds = {
            "temperature_critical": 85,
            "temperature_warning": 75,
            "memory_usage_critical": 95,  # percentage
            "memory_usage_warning": 85,
            "utilization_stuck": 95,  # if utilization stuck > 95% for too long
            "power_draw_anomaly": 300,  # watts
        }

        # Alert history
        self.alerts = deque(maxlen=100)

    def start_collection(self):
        """Start the metrics collection thread"""
        if self.running:
            return

        self.running = True
        self.collection_thread = threading.Thread(
            target=self._collection_loop, daemon=True
        )
        self.collection_thread.start()
        logger.info("🚀 GPU metrics collection started")

    def stop_collection(self):
        """Stop the metrics collection thread"""
        self.running = False
        if self.collection_thread:
            self.collection_thread.join(timeout=5)
        logger.info("🛑 GPU metrics collection stopped")

    def _collection_loop(self):
        """Main collection loop"""
        while self.running:
            try:
                self._collect_metrics()
                time.sleep(self.collection_interval)
            except Exception as e:
                logger.error(f"Error in metrics collection: {e}")
                time.sleep(self.collection_interval)

    def _collect_metrics(self):
        """Collect current GPU metrics"""
        timestamp = datetime.now()

        try:
            # Collect GPU metrics
            gpu_metrics = self._get_gpu_metrics()

            # Collect system metrics
            system_metrics = self._get_system_metrics()

            # Collect agent allocation info
            allocation_metrics = self._get_allocation_metrics()

            # Combine all metrics
            current = {
                "timestamp": timestamp,
                "gpu": gpu_metrics,
                "system": system_metrics,
                "allocations": allocation_metrics,
            }

            self.current_metrics = current

            # Store in history
            self._store_historical_data(current)

            # Check for alerts
            self._check_alerts(current)

        except Exception as e:
            logger.error(f"Failed to collect metrics: {e}")

    def _get_gpu_metrics(self) -> dict[str, Any]:
        """Get comprehensive GPU metrics"""
        if not GPU_AVAILABLE:
            return {"available": False}

        try:
            device_count = torch.cuda.device_count()
            gpu_devices = []

            for device_id in range(device_count):
                device_metrics = self._get_device_metrics(device_id)
                gpu_devices.append(device_metrics)

            return {
                "available": True,
                "device_count": device_count,
                "devices": gpu_devices,
            }

        except Exception as e:
            logger.error(f"Failed to get GPU metrics: {e}")
            return {"available": False, "error": str(e)}

    def _get_device_metrics(self, device_id: int) -> dict[str, Any]:
        """Get metrics for a specific GPU device"""
        try:
            # Get nvidia-smi data
            nvidia_data = self._get_nvidia_smi_data(device_id)

            # Get PyTorch memory data
            torch_data = self._get_torch_memory_data(device_id)

            # Get process information
            process_data = self._get_gpu_processes(device_id)

            return {
                "device_id": device_id,
                "name": torch.cuda.get_device_name(device_id) if torch else "Unknown",
                "total_memory_gb": nvidia_data.get("total_memory_gb", 0),
                "used_memory_gb": torch_data.get("used_memory_gb", 0),
                "free_memory_gb": nvidia_data.get("free_memory_gb", 0),
                "utilization_percent": nvidia_data.get("utilization_percent", 0),
                "temperature_c": nvidia_data.get("temperature_c", 0),
                "power_draw_w": nvidia_data.get("power_draw_w", 0),
                "memory_percent": (
                    torch_data.get("used_memory_gb", 0)
                    / nvidia_data.get("total_memory_gb", 1)
                )
                * 100,
                "processes": process_data,
            }

        except Exception as e:
            logger.error(f"Failed to get device {device_id} metrics: {e}")
            return {"device_id": device_id, "error": str(e)}

    def _get_nvidia_smi_data(self, device_id: int) -> dict[str, float]:
        """Get GPU data from nvidia-smi"""
        try:
            cmd = [
                "nvidia-smi",
                f"--id={device_id}",
                "--query-gpu=memory.total,memory.free,memory.used,utilization.gpu,temperature.gpu,power.draw",
                "--format=csv,nounits,noheader",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode != 0:
                return {}

            parts = [p.strip() for p in result.stdout.strip().split(",")]

            return {
                "total_memory_gb": float(parts[0]) / 1024 if parts[0] else 0,
                "free_memory_gb": float(parts[1]) / 1024 if parts[1] else 0,
                "used_memory_gb": float(parts[2]) / 1024 if parts[2] else 0,
                "utilization_percent": float(parts[3]) if parts[3] else 0,
                "temperature_c": float(parts[4]) if parts[4] else 0,
                "power_draw_w": float(parts[5]) if parts[5] else 0,
            }

        except Exception:
            return {}

    def _get_torch_memory_data(self, device_id: int) -> dict[str, float]:
        """Get memory data from PyTorch"""
        if not TORCH_AVAILABLE or not torch.cuda.is_available():
            return {"used_memory_gb": 0}

        try:
            torch.cuda.synchronize(device_id)  # Ensure accurate readings
            allocated = torch.cuda.memory_allocated(device_id) / (1024**3)
            reserved = torch.cuda.memory_reserved(device_id) / (1024**3)

            return {"used_memory_gb": allocated, "reserved_memory_gb": reserved}
        except Exception:
            return {"used_memory_gb": 0}

    def _get_gpu_processes(self, device_id: int) -> list[dict[str, Any]]:
        """Get processes using the GPU"""
        try:
            cmd = [
                "nvidia-smi",
                f"--id={device_id}",
                "--query-compute-apps=pid,name,used_memory",
                "--format=csv,nounits,noheader",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode != 0:
                return []

            processes = []
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 3:
                        try:
                            processes.append(
                                {
                                    "pid": int(parts[0]),
                                    "name": parts[1],
                                    "used_memory_mb": float(parts[2]),
                                }
                            )
                        except ValueError:
                            continue

            return processes

        except Exception:
            return []

    def _get_system_metrics(self) -> dict[str, Any]:
        """Get system-wide metrics"""
        try:
            return {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_percent": psutil.virtual_memory().percent,
                "memory_used_gb": psutil.virtual_memory().used / (1024**3),
                "memory_total_gb": psutil.virtual_memory().total / (1024**3),
                "disk_usage_percent": psutil.disk_usage("/").percent,
                "network_connections": len(psutil.net_connections()),
            }
        except Exception:
            return {}

    def _get_allocation_metrics(self) -> dict[str, Any]:
        """Get agent allocation metrics"""
        try:
            # Import here to avoid circular imports
            from .gpu_manager_production import get_gpu_manager

            manager = get_gpu_manager()
            status = manager.get_system_status()

            return {
                "active_allocations": status.get("active_allocations", 0),
                "total_allocations": status.get("total_allocations", 0),
                "gpu_count": status.get("gpu_count", 0),
                "metrics": status.get("metrics", {}),
            }

        except Exception:
            return {"error": "Could not get allocation metrics"}

    def _store_historical_data(self, current: dict[str, Any]):
        """Store metrics in historical data"""
        timestamp = current["timestamp"]

        # Store timestamp
        self.metrics_history["timestamps"].append(timestamp)

        # Store GPU metrics
        if current["gpu"]["available"]:
            for device in current["gpu"]["devices"]:
                device_id = device["device_id"]

                # Initialize device-specific history if needed
                for metric in [
                    "utilization",
                    "memory_used",
                    "memory_free",
                    "temperature",
                    "power_draw",
                ]:
                    key = f"gpu_{device_id}_{metric}"
                    if key not in self.metrics_history:
                        self.metrics_history[key] = deque(maxlen=self.max_history)

                # Store device metrics
                self.metrics_history[f"gpu_{device_id}_utilization"].append(
                    device.get("utilization_percent", 0)
                )
                self.metrics_history[f"gpu_{device_id}_memory_used"].append(
                    device.get("used_memory_gb", 0)
                )
                self.metrics_history[f"gpu_{device_id}_memory_free"].append(
                    device.get("free_memory_gb", 0)
                )
                self.metrics_history[f"gpu_{device_id}_temperature"].append(
                    device.get("temperature_c", 0)
                )
                self.metrics_history[f"gpu_{device_id}_power_draw"].append(
                    device.get("power_draw_w", 0)
                )

        # Store allocation metrics
        self.metrics_history["agent_allocations"].append(
            current["allocations"].get("active_allocations", 0)
        )

    def _check_alerts(self, current: dict[str, Any]):
        """Check for alert conditions"""
        if not current["gpu"]["available"]:
            return

        for device in current["gpu"]["devices"]:
            device_id = device["device_id"]

            # Temperature alerts
            temp = device.get("temperature_c", 0)
            if temp >= self.alert_thresholds["temperature_critical"]:
                self._create_alert(
                    "CRITICAL", f"GPU {device_id} temperature: {temp}°C", device
                )
            elif temp >= self.alert_thresholds["temperature_warning"]:
                self._create_alert(
                    "WARNING", f"GPU {device_id} temperature: {temp}°C", device
                )

            # Memory usage alerts
            mem_percent = device.get("memory_percent", 0)
            if mem_percent >= self.alert_thresholds["memory_usage_critical"]:
                self._create_alert(
                    "CRITICAL",
                    f"GPU {device_id} memory usage: {mem_percent:.1f}%",
                    device,
                )
            elif mem_percent >= self.alert_thresholds["memory_usage_warning"]:
                self._create_alert(
                    "WARNING",
                    f"GPU {device_id} memory usage: {mem_percent:.1f}%",
                    device,
                )

            # Utilization stuck alerts
            util = device.get("utilization_percent", 0)
            if util >= self.alert_thresholds["utilization_stuck"]:
                # Check if it's been stuck for multiple readings
                util_history = list(
                    self.metrics_history.get(f"gpu_{device_id}_utilization", [])
                )
                if len(util_history) >= 3 and all(
                    u >= self.alert_thresholds["utilization_stuck"]
                    for u in util_history[-3:]
                ):
                    self._create_alert(
                        "WARNING",
                        f"GPU {device_id} utilization stuck at {util}%",
                        device,
                    )

            # Power draw alerts
            power = device.get("power_draw_w", 0)
            if power >= self.alert_thresholds["power_draw_anomaly"]:
                self._create_alert(
                    "WARNING", f"GPU {device_id} high power draw: {power}W", device
                )

    def _create_alert(self, level: str, message: str, device_data: dict[str, Any]):
        """Create an alert"""
        alert = {
            "timestamp": datetime.now(),
            "level": level,
            "message": message,
            "device_id": device_data.get("device_id"),
            "device_data": device_data,
        }

        self.alerts.append(alert)
        logger.warning(f"🚨 GPU Alert [{level}]: {message}")

    def get_current_dashboard(self) -> dict[str, Any]:
        """Get current dashboard data"""
        return {
            "current_metrics": self.current_metrics,
            "recent_alerts": list(self.alerts)[-10:],  # Last 10 alerts
            "summary": self._get_dashboard_summary(),
        }

    def get_historical_dashboard(self, hours: int = 1) -> dict[str, Any]:
        """Get historical dashboard data"""
        cutoff_time = datetime.now() - timedelta(hours=hours)

        # Filter historical data
        recent_indices = []
        for i, timestamp in enumerate(self.metrics_history["timestamps"]):
            if timestamp >= cutoff_time:
                recent_indices.append(i)

        historical_data = {}
        for key, data in self.metrics_history.items():
            if key != "timestamps":
                historical_data[key] = [
                    data[i] for i in recent_indices if i < len(data)
                ]

        return {
            "timestamps": [
                self.metrics_history["timestamps"][i]
                for i in recent_indices
                if i < len(self.metrics_history["timestamps"])
            ],
            "metrics": historical_data,
            "period_hours": hours,
        }

    def _get_dashboard_summary(self) -> dict[str, Any]:
        """Get dashboard summary statistics"""
        if not self.current_metrics:
            return {"status": "no_data"}

        gpu_data = self.current_metrics.get("gpu", {})
        if not gpu_data.get("available"):
            return {"status": "gpu_unavailable"}

        devices = gpu_data.get("devices", [])
        if not devices:
            return {"status": "no_devices"}

        # Calculate summary statistics
        total_memory = sum(d.get("total_memory_gb", 0) for d in devices)
        used_memory = sum(d.get("used_memory_gb", 0) for d in devices)
        avg_temp = sum(d.get("temperature_c", 0) for d in devices) / len(devices)
        max_util = max(d.get("utilization_percent", 0) for d in devices)

        return {
            "status": "healthy",
            "total_gpus": len(devices),
            "total_memory_gb": total_memory,
            "used_memory_gb": used_memory,
            "memory_usage_percent": (used_memory / total_memory * 100)
            if total_memory > 0
            else 0,
            "average_temperature_c": avg_temp,
            "max_utilization_percent": max_util,
            "active_alerts": len(
                [
                    a
                    for a in self.alerts
                    if (datetime.now() - a["timestamp"]).seconds < 3600
                ]
            ),  # Last hour
        }

    def get_performance_trends(self, hours: int = 24) -> dict[str, Any]:
        """Get performance trend analysis"""
        historical = self.get_historical_dashboard(hours)

        if not historical["timestamps"]:
            return {"status": "no_data"}

        trends = {}
        for metric_key, values in historical["metrics"].items():
            if values:
                trends[metric_key] = {
                    "current": values[-1] if values else 0,
                    "average": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "trend": self._calculate_trend(values),
                }

        return {
            "period_hours": hours,
            "data_points": len(historical["timestamps"]),
            "trends": trends,
        }

    def _calculate_trend(self, values: list[float]) -> str:
        """Calculate trend direction"""
        if len(values) < 2:
            return "stable"

        # Simple linear trend
        n = len(values)
        if n < 2:
            return "stable"

        # Calculate slope
        x = list(range(n))
        slope = np.polyfit(x, values, 1)[0] if len(x) > 1 else 0

        if abs(slope) < 0.01:
            return "stable"
        elif slope > 0:
            return "increasing"
        else:
            return "decreasing"


# Global metrics collector
_metrics_collector: GPUMetricsCollector | None = None
_collector_lock = threading.Lock()


def get_metrics_collector() -> GPUMetricsCollector:
    """Get the global metrics collector instance"""
    global _metrics_collector
    with _collector_lock:
        if _metrics_collector is None:
            _metrics_collector = GPUMetricsCollector()
        return _metrics_collector


def start_gpu_monitoring():
    """Start GPU monitoring"""
    collector = get_metrics_collector()
    collector.start_collection()


def stop_gpu_monitoring():
    """Stop GPU monitoring"""
    collector = get_metrics_collector()
    collector.stop_collection()


def get_gpu_dashboard() -> dict[str, Any]:
    """Get current GPU dashboard"""
    collector = get_metrics_collector()
    return collector.get_current_dashboard()


def get_gpu_trends(hours: int = 24) -> dict[str, Any]:
    """Get GPU performance trends"""
    collector = get_metrics_collector()
    return collector.get_performance_trends(hours)


# Auto-start monitoring on import (DISABLED when GPU Orchestrator is authoritative)
_monitoring_started = False
_orchestrator_env = os.environ.get("GPU_ORCHESTRATOR_URL") or os.environ.get(
    "GPU_ORCHESTRATOR_PORT"
)
if not _monitoring_started and not _orchestrator_env:
    try:
        start_gpu_monitoring()
        _monitoring_started = True
        logger.info("✅ GPU monitoring auto-started (no orchestrator detected)")
    except Exception as e:
        logger.warning(f"Failed to auto-start GPU monitoring: {e}")
else:
    logger.info("🛑 Suppressing legacy GPU monitoring auto-start (orchestrator active)")
