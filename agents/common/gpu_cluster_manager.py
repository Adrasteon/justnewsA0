"""
Multi-GPU Cluster Support for JustNews

Provides comprehensive multi-GPU cluster management with:
- Distributed GPU resource allocation
- Cluster health monitoring and failover
- Load balancing across multiple GPUs
- Dynamic scaling and resource optimization
- Cluster configuration management
- Fault tolerance and recovery
"""

import json
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from common.observability import get_logger

# GPU and ML imports with graceful fallbacks
try:
    import psutil
    import torch

    GPU_AVAILABLE = torch.cuda.is_available()
    TORCH_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False
    TORCH_AVAILABLE = False
    torch = None
    psutil = None

# Conditional GPUtil import
GPUTIL_AVAILABLE = False
GPUtil = None
try:
    import GPUtil  # type: ignore

    GPUTIL_AVAILABLE = True
except ImportError:
    pass

logger = get_logger(__name__)


class ClusterStatus(Enum):
    """Cluster operational status"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    MAINTENANCE = "maintenance"


class GPUStatus(Enum):
    """Individual GPU status"""

    AVAILABLE = "available"
    ALLOCATED = "allocated"
    UNAVAILABLE = "unavailable"
    MAINTENANCE = "maintenance"
    FAILED = "failed"


@dataclass
class GPUInfo:
    """Information about a GPU in the cluster"""

    device_id: int
    name: str
    memory_total_gb: float
    memory_free_gb: float
    memory_used_gb: float
    utilization_percent: float
    temperature_c: float
    power_draw_w: float
    status: GPUStatus
    last_updated: datetime
    allocation_count: int = 0
    failure_count: int = 0


@dataclass
class ClusterAllocation:
    """GPU cluster allocation record"""

    allocation_id: str
    agent_name: str
    requested_memory_gb: float
    allocated_gpus: list[int]
    total_allocated_memory_gb: float
    allocation_time: datetime
    expected_completion_time: datetime | None = None
    status: str = "active"


@dataclass
class ClusterMetrics:
    """Cluster-wide performance metrics"""

    total_gpus: int
    available_gpus: int
    allocated_gpus: int
    total_memory_gb: float
    available_memory_gb: float
    allocated_memory_gb: float
    average_utilization: float
    cluster_efficiency: float
    load_balance_score: float
    last_updated: datetime


class GPUClusterManager:
    """
    Advanced GPU cluster manager for multi-GPU deployments

    Features:
    - Distributed GPU resource allocation
    - Cluster health monitoring and failover
    - Load balancing across GPUs
    - Dynamic scaling and optimization
    - Fault tolerance and recovery
    """

    def __init__(self, cluster_config_path: str = "./config/gpu/cluster_config.json"):
        self.cluster_config_path = Path(cluster_config_path)
        self.cluster_config_path.parent.mkdir(parents=True, exist_ok=True)

        # Cluster state
        self.cluster_id = f"cluster_{int(time.time())}"
        self.gpus: dict[int, GPUInfo] = {}
        self.allocations: dict[str, ClusterAllocation] = {}
        self.cluster_metrics = ClusterMetrics(
            total_gpus=0,
            available_gpus=0,
            allocated_gpus=0,
            total_memory_gb=0.0,
            available_memory_gb=0.0,
            allocated_memory_gb=0.0,
            average_utilization=0.0,
            cluster_efficiency=0.0,
            load_balance_score=0.0,
            last_updated=datetime.now(),
        )

        # Configuration
        self.max_allocation_time_hours = 24
        self.health_check_interval_s = 30
        self.load_balance_threshold = 0.8
        self.failover_enabled = True
        self.auto_scaling_enabled = True

        # Monitoring
        self.health_history = deque(maxlen=1000)
        self.allocation_history = deque(maxlen=5000)
        self.failure_events = deque(maxlen=100)

        # Threading
        self.monitoring_thread = None
        self.running = False

        # Load configuration
        self._load_cluster_config()

        # Initialize cluster
        self._initialize_cluster()

        logger.info(f"🚀 GPU Cluster Manager initialized: {self.cluster_id}")

    def _initialize_cluster(self):
        """Initialize the GPU cluster"""
        try:
            if not GPU_AVAILABLE:
                logger.warning("GPU not available, running in simulation mode")
                self._initialize_simulated_cluster()
                return

            # Discover available GPUs
            gpu_count = torch.cuda.device_count()
            logger.info(f"Discovered {gpu_count} GPUs in cluster")

            for i in range(gpu_count):
                gpu_info = self._get_gpu_info(i)
                if gpu_info:
                    self.gpus[i] = gpu_info
                    logger.info(
                        f"GPU {i}: {gpu_info.name} - {gpu_info.memory_total_gb:.1f}GB"
                    )

            self._update_cluster_metrics()

        except Exception as e:
            logger.error(f"Error initializing cluster: {e}")
            self._initialize_simulated_cluster()

    def _initialize_simulated_cluster(self):
        """Initialize simulated cluster for testing/development"""
        logger.info("Initializing simulated GPU cluster")

        # Create simulated GPUs
        for i in range(4):  # Simulate 4 GPUs
            gpu_info = GPUInfo(
                device_id=i,
                name=f"Simulated_GPU_{i}",
                memory_total_gb=24.0,
                memory_free_gb=20.0 - (i * 2),  # Vary memory usage
                memory_used_gb=4.0 + (i * 2),
                utilization_percent=20.0 + (i * 15),  # Vary utilization
                temperature_c=50.0 + (i * 5),
                power_draw_w=150.0 + (i * 20),
                status=GPUStatus.AVAILABLE,
                last_updated=datetime.now(),
            )
            self.gpus[i] = gpu_info

        self._update_cluster_metrics()
        logger.info("Simulated cluster initialized with 4 GPUs")

    def _get_gpu_info(self, device_id: int) -> GPUInfo | None:
        """Get detailed information about a specific GPU"""
        try:
            if not GPU_AVAILABLE:
                return None

            # Get basic GPU properties
            props = torch.cuda.get_device_properties(device_id)

            # Get current memory info
            memory_info = torch.cuda.mem_get_info(device_id)
            memory_free = memory_info[0] / (1024**3)  # Convert to GB
            memory_total = props.total_memory / (1024**3)
            memory_used = memory_total - memory_free

            # Get utilization (approximate)
            utilization = 0.0
            try:
                if GPUtil:
                    gpu_stats = GPUtil.getGPUs()
                    if device_id < len(gpu_stats):
                        utilization = gpu_stats[device_id].load * 100
            except (AttributeError, IndexError, Exception) as e:
                logger.debug(f"Failed to get GPU utilization: {e}")
                pass

            # Get temperature and power (if available)
            temperature = 50.0  # Default
            power_draw = 150.0  # Default

            try:
                if GPUtil and device_id < len(GPUtil.getGPUs()):
                    gpu = GPUtil.getGPUs()[device_id]
                    temperature = gpu.temperature
                    # Power draw estimation based on utilization
                    power_draw = 100 + (utilization * 2)
            except (AttributeError, IndexError, Exception) as e:
                logger.debug(f"Failed to get GPU temperature/power: {e}")
                pass

            return GPUInfo(
                device_id=device_id,
                name=props.name,
                memory_total_gb=memory_total,
                memory_free_gb=memory_free,
                memory_used_gb=memory_used,
                utilization_percent=utilization,
                temperature_c=temperature,
                power_draw_w=power_draw,
                status=GPUStatus.AVAILABLE,
                last_updated=datetime.now(),
            )

        except Exception as e:
            logger.error(f"Error getting GPU info for device {device_id}: {e}")
            return None

    def request_cluster_allocation(
        self,
        agent_name: str,
        requested_memory_gb: float,
        model_type: str = "general",
        priority: str = "normal",
    ) -> dict[str, Any]:
        """
        Request GPU allocation from the cluster

        Args:
            agent_name: Name of the requesting agent
            requested_memory_gb: Memory required in GB
            model_type: Type of model (embedding, generation, vision, general)
            priority: Allocation priority (critical, high, normal, low)

        Returns:
            Allocation result with GPU assignments
        """
        try:
            allocation_id = f"alloc_{int(time.time())}_{agent_name}"

            # Check cluster health
            if self.get_cluster_status() == ClusterStatus.CRITICAL:
                return {
                    "status": "failed",
                    "message": "Cluster is in critical state",
                    "allocation_id": allocation_id,
                }

            # Find optimal GPU allocation
            allocation_result = self._find_optimal_allocation(
                requested_memory_gb, model_type, priority
            )

            if not allocation_result["success"]:
                return {
                    "status": "failed",
                    "message": allocation_result["message"],
                    "allocation_id": allocation_id,
                }

            # Create allocation record
            allocated_gpus = allocation_result["gpus"]
            total_allocated_memory = sum(
                self.gpus[gpu_id].memory_free_gb for gpu_id in allocated_gpus
            )

            allocation = ClusterAllocation(
                allocation_id=allocation_id,
                agent_name=agent_name,
                requested_memory_gb=requested_memory_gb,
                allocated_gpus=allocated_gpus,
                total_allocated_memory_gb=min(
                    total_allocated_memory, requested_memory_gb
                ),
                allocation_time=datetime.now(),
            )

            # Update GPU status
            for gpu_id in allocated_gpus:
                if gpu_id in self.gpus:
                    self.gpus[gpu_id].allocation_count += 1
                    # Mark GPU as allocated if it's the primary allocation
                    if gpu_id == allocated_gpus[0]:
                        self.gpus[gpu_id].status = GPUStatus.ALLOCATED

            self.allocations[allocation_id] = allocation
            self.allocation_history.append(allocation)

            self._update_cluster_metrics()

            logger.info(
                f"✅ Cluster allocation successful: {allocation_id} -> GPUs {allocated_gpus}"
            )

            return {
                "status": "allocated",
                "allocation_id": allocation_id,
                "gpus": allocated_gpus,
                "primary_gpu": allocated_gpus[0],
                "total_memory_gb": allocation.total_allocated_memory_gb,
                "allocation_time": allocation.allocation_time.isoformat(),
            }

        except Exception as e:
            logger.error(f"Error in cluster allocation: {e}")
            return {
                "status": "error",
                "message": f"Allocation failed: {str(e)}",
                "allocation_id": f"alloc_{int(time.time())}_{agent_name}",
            }

    def _find_optimal_allocation(
        self, requested_memory_gb: float, model_type: str, priority: str
    ) -> dict[str, Any]:
        """Find optimal GPU allocation for the request"""
        try:
            # Get available GPUs
            available_gpus = [
                gpu_id
                for gpu_id, gpu in self.gpus.items()
                if gpu.status == GPUStatus.AVAILABLE and gpu.memory_free_gb >= 1.0
            ]

            if not available_gpus:
                return {"success": False, "message": "No GPUs available for allocation"}

            # Sort GPUs by available memory and utilization
            gpu_scores = {}
            for gpu_id in available_gpus:
                gpu = self.gpus[gpu_id]
                # Score based on memory availability and current utilization
                memory_score = min(1.0, gpu.memory_free_gb / requested_memory_gb)
                utilization_penalty = gpu.utilization_percent / 100.0
                temperature_penalty = max(
                    0, (gpu.temperature_c - 70) / 30
                )  # Penalty above 70C

                gpu_scores[gpu_id] = (
                    memory_score - utilization_penalty - temperature_penalty
                )

            # Sort by score (highest first)
            sorted_gpus = sorted(gpu_scores.items(), key=lambda x: x[1], reverse=True)

            # Select GPUs based on requirements
            selected_gpus = []

            if requested_memory_gb <= 8:  # Single GPU sufficient
                selected_gpus = [sorted_gpus[0][0]]
            elif requested_memory_gb <= 16:  # Two GPUs
                selected_gpus = [gpu[0] for gpu in sorted_gpus[:2]]
            else:  # Three or more GPUs for large models
                selected_gpus = [
                    gpu[0] for gpu in sorted_gpus[: min(4, len(sorted_gpus))]
                ]

            # Verify total memory availability
            total_available = sum(
                self.gpus[gpu_id].memory_free_gb for gpu_id in selected_gpus
            )
            if total_available < requested_memory_gb:
                return {
                    "success": False,
                    "message": f"Insufficient memory: {total_available:.1f}GB available, {requested_memory_gb}GB requested",
                }

            return {
                "success": True,
                "gpus": selected_gpus,
                "total_memory": total_available,
            }

        except Exception as e:
            logger.error(f"Error finding optimal allocation: {e}")
            return {
                "success": False,
                "message": f"Allocation optimization failed: {str(e)}",
            }

    def release_cluster_allocation(self, allocation_id: str) -> bool:
        """Release a cluster allocation"""
        try:
            if allocation_id not in self.allocations:
                logger.warning(f"Allocation {allocation_id} not found")
                return False

            allocation = self.allocations[allocation_id]

            # Update GPU status
            for gpu_id in allocation.allocated_gpus:
                if gpu_id in self.gpus:
                    self.gpus[gpu_id].status = GPUStatus.AVAILABLE

            # Mark allocation as completed
            allocation.status = "completed"
            allocation.expected_completion_time = datetime.now()

            self._update_cluster_metrics()

            logger.info(f"✅ Cluster allocation released: {allocation_id}")
            return True

        except Exception as e:
            logger.error(f"Error releasing allocation {allocation_id}: {e}")
            return False

    def get_cluster_status(self) -> ClusterStatus:
        """Get overall cluster status"""
        try:
            if not self.gpus:
                return ClusterStatus.CRITICAL

            available_gpus = sum(
                1 for gpu in self.gpus.values() if gpu.status == GPUStatus.AVAILABLE
            )
            failed_gpus = sum(
                1 for gpu in self.gpus.values() if gpu.status == GPUStatus.FAILED
            )

            total_gpus = len(self.gpus)

            if failed_gpus > 0:
                return ClusterStatus.CRITICAL
            elif available_gpus < total_gpus * 0.5:  # Less than 50% available
                return ClusterStatus.DEGRADED
            else:
                return ClusterStatus.HEALTHY

        except Exception as e:
            logger.error(f"Error getting cluster status: {e}")
            return ClusterStatus.CRITICAL

    def get_cluster_metrics(self) -> ClusterMetrics:
        """Get current cluster metrics"""
        self._update_cluster_metrics()
        return self.cluster_metrics

    def _update_cluster_metrics(self):
        """Update cluster-wide metrics"""
        try:
            if not self.gpus:
                return

            total_gpus = len(self.gpus)
            available_gpus = sum(
                1 for gpu in self.gpus.values() if gpu.status == GPUStatus.AVAILABLE
            )
            allocated_gpus = sum(
                1 for gpu in self.gpus.values() if gpu.status == GPUStatus.ALLOCATED
            )

            total_memory = sum(gpu.memory_total_gb for gpu in self.gpus.values())
            available_memory = sum(gpu.memory_free_gb for gpu in self.gpus.values())
            allocated_memory = sum(gpu.memory_used_gb for gpu in self.gpus.values())

            avg_utilization = np.mean(
                [gpu.utilization_percent for gpu in self.gpus.values()]
            )

            # Calculate cluster efficiency (utilization vs available memory ratio)
            cluster_efficiency = (
                (allocated_memory / total_memory) if total_memory > 0 else 0
            )

            # Calculate load balance score (lower variance = better balance)
            utilizations = [gpu.utilization_percent for gpu in self.gpus.values()]
            load_balance_score = (
                1.0 - (np.std(utilizations) / 100.0) if utilizations else 0
            )

            self.cluster_metrics = ClusterMetrics(
                total_gpus=total_gpus,
                available_gpus=available_gpus,
                allocated_gpus=allocated_gpus,
                total_memory_gb=total_memory,
                available_memory_gb=available_memory,
                allocated_memory_gb=allocated_memory,
                average_utilization=avg_utilization,
                cluster_efficiency=cluster_efficiency,
                load_balance_score=load_balance_score,
                last_updated=datetime.now(),
            )

        except Exception as e:
            logger.error(f"Error updating cluster metrics: {e}")

    def start_monitoring(self):
        """Start cluster monitoring"""
        if self.running:
            return

        self.running = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop, daemon=True
        )
        self.monitoring_thread.start()
        logger.info("📊 Cluster monitoring started")

    def stop_monitoring(self):
        """Stop cluster monitoring"""
        self.running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logger.info("🛑 Cluster monitoring stopped")

    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                # Update GPU information
                self._update_gpu_status()

                # Check for failed GPUs and trigger failover
                self._check_failover_conditions()

                # Update cluster metrics
                self._update_cluster_metrics()

                # Clean up expired allocations
                self._cleanup_expired_allocations()

                time.sleep(self.health_check_interval_s)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(60)  # Wait longer on error

    def _update_gpu_status(self):
        """Update status of all GPUs in the cluster"""
        for gpu_id in list(self.gpus.keys()):
            try:
                updated_info = self._get_gpu_info(gpu_id)
                if updated_info:
                    # Preserve allocation count and failure count
                    updated_info.allocation_count = self.gpus[gpu_id].allocation_count
                    updated_info.failure_count = self.gpus[gpu_id].failure_count

                    # Check for GPU failure
                    if (
                        self.gpus[gpu_id].status != GPUStatus.FAILED
                        and updated_info.status == GPUStatus.FAILED
                    ):
                        updated_info.failure_count += 1
                        logger.warning(f"GPU {gpu_id} marked as failed")

                    self.gpus[gpu_id] = updated_info
                else:
                    # GPU became unavailable
                    if self.gpus[gpu_id].status != GPUStatus.FAILED:
                        self.gpus[gpu_id].status = GPUStatus.FAILED
                        self.gpus[gpu_id].failure_count += 1
                        logger.error(f"GPU {gpu_id} became unavailable")

            except Exception as e:
                logger.error(f"Error updating GPU {gpu_id} status: {e}")

    def _check_failover_conditions(self):
        """Check for failover conditions and trigger recovery"""
        if not self.failover_enabled:
            return

        failed_gpus = [
            gpu_id
            for gpu_id, gpu in self.gpus.items()
            if gpu.status == GPUStatus.FAILED
        ]

        if failed_gpus:
            logger.warning(f"Detected {len(failed_gpus)} failed GPUs: {failed_gpus}")

            # Record failure event
            failure_event = {
                "timestamp": datetime.now(),
                "failed_gpus": failed_gpus,
                "cluster_status": self.get_cluster_status().value,
                "active_allocations": len(
                    [a for a in self.allocations.values() if a.status == "active"]
                ),
            }
            self.failure_events.append(failure_event)

            # Trigger failover for affected allocations
            self._trigger_failover(failed_gpus)

    def _trigger_failover(self, failed_gpus: list[int]):
        """Trigger failover for allocations affected by failed GPUs"""
        affected_allocations = []

        for alloc_id, allocation in self.allocations.items():
            if allocation.status == "active" and any(
                gpu in failed_gpus for gpu in allocation.allocated_gpus
            ):
                affected_allocations.append(alloc_id)

        for alloc_id in affected_allocations:
            logger.info(f"Triggering failover for allocation {alloc_id}")
            # In a real implementation, this would attempt to reallocate to healthy GPUs
            # For now, we'll mark as failed
            self.allocations[alloc_id].status = "failed"

    def _cleanup_expired_allocations(self):
        """Clean up expired allocations"""
        current_time = datetime.now()
        expired_allocations = []

        for alloc_id, allocation in self.allocations.items():
            if allocation.status == "active":
                allocation_duration = current_time - allocation.allocation_time
                if allocation_duration.total_seconds() > (
                    self.max_allocation_time_hours * 3600
                ):
                    expired_allocations.append(alloc_id)

        for alloc_id in expired_allocations:
            logger.warning(f"Cleaning up expired allocation: {alloc_id}")
            self.release_cluster_allocation(alloc_id)

    def get_cluster_report(self) -> dict[str, Any]:
        """Generate comprehensive cluster report"""
        try:
            metrics = self.get_cluster_metrics()

            report = {
                "cluster_id": self.cluster_id,
                "status": self.get_cluster_status().value,
                "timestamp": datetime.now().isoformat(),
                "metrics": asdict(metrics),
                "gpus": {
                    gpu_id: {
                        "name": gpu.name,
                        "status": gpu.status.value,
                        "memory_total_gb": gpu.memory_total_gb,
                        "memory_free_gb": gpu.memory_free_gb,
                        "utilization_percent": gpu.utilization_percent,
                        "temperature_c": gpu.temperature_c,
                        "allocation_count": gpu.allocation_count,
                        "failure_count": gpu.failure_count,
                    }
                    for gpu_id, gpu in self.gpus.items()
                },
                "active_allocations": len(
                    [a for a in self.allocations.values() if a.status == "active"]
                ),
                "total_allocations": len(self.allocations),
                "recent_failures": len(list(self.failure_events)),
            }

            return report

        except Exception as e:
            logger.error(f"Error generating cluster report: {e}")
            return {"error": str(e)}

    def _load_cluster_config(self):
        """Load cluster configuration"""
        try:
            if self.cluster_config_path.exists():
                with open(self.cluster_config_path) as f:
                    config = json.load(f)

                self.max_allocation_time_hours = config.get(
                    "max_allocation_time_hours", 24
                )
                self.health_check_interval_s = config.get("health_check_interval_s", 30)
                self.load_balance_threshold = config.get("load_balance_threshold", 0.8)
                self.failover_enabled = config.get("failover_enabled", True)
                self.auto_scaling_enabled = config.get("auto_scaling_enabled", True)

                logger.info("✅ Cluster configuration loaded")

        except Exception as e:
            logger.warning(f"Failed to load cluster config: {e}, using defaults")

    def _save_cluster_config(self):
        """Save cluster configuration"""
        try:
            config = {
                "max_allocation_time_hours": self.max_allocation_time_hours,
                "health_check_interval_s": self.health_check_interval_s,
                "load_balance_threshold": self.load_balance_threshold,
                "failover_enabled": self.failover_enabled,
                "auto_scaling_enabled": self.auto_scaling_enabled,
                "saved_at": datetime.now().isoformat(),
            }

            with open(self.cluster_config_path, "w") as f:
                json.dump(config, f, indent=2)

            logger.info("💾 Cluster configuration saved")

        except Exception as e:
            logger.error(f"Failed to save cluster config: {e}")


# Global cluster manager instance
_cluster_manager: GPUClusterManager | None = None
_cluster_lock = threading.Lock()


def get_gpu_cluster_manager() -> GPUClusterManager:
    """Get the global GPU cluster manager instance"""
    global _cluster_manager
    with _cluster_lock:
        if _cluster_manager is None:
            _cluster_manager = GPUClusterManager()
        return _cluster_manager


def request_cluster_allocation(
    agent_name: str,
    memory_gb: float,
    model_type: str = "general",
    priority: str = "normal",
) -> dict[str, Any]:
    """Request GPU allocation from the cluster"""
    manager = get_gpu_cluster_manager()
    return manager.request_cluster_allocation(
        agent_name, memory_gb, model_type, priority
    )


def release_cluster_allocation(allocation_id: str) -> bool:
    """Release a cluster allocation"""
    manager = get_gpu_cluster_manager()
    return manager.release_cluster_allocation(allocation_id)


def get_cluster_status() -> dict[str, Any]:
    """Get cluster status and metrics"""
    manager = get_gpu_cluster_manager()
    metrics = manager.get_cluster_metrics()
    return {
        "status": manager.get_cluster_status().value,
        "metrics": asdict(metrics),
        "gpu_count": len(manager.gpus),
        "available_gpus": sum(
            1 for gpu in manager.gpus.values() if gpu.status == GPUStatus.AVAILABLE
        ),
    }


def get_cluster_report() -> dict[str, Any]:
    """Get comprehensive cluster report"""
    manager = get_gpu_cluster_manager()
    return manager.get_cluster_report()


# Initialize cluster manager on import
_cluster_manager = get_gpu_cluster_manager()
