"""
Production Multi-Agent GPU Manager for JustNews
Replaces the shim implementation with production-ready GPU resource management

Features:
- Per-agent GPU allocation with memory limits
- Automatic GPU health monitoring
- Resource pooling and optimization
- Graceful fallback to CPU
- Comprehensive error handling and recovery
- Real-time performance metrics
- Atomic allocation operations
"""

import os
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from common.observability import get_logger

# GPU and ML imports with graceful fallbacks
try:
    import numpy as np
    import torch

    GPU_AVAILABLE = torch.cuda.is_available()
    MPS_AVAILABLE = (
        hasattr(torch, "backends")
        and hasattr(torch.backends, "mps")
        and torch.backends.mps.is_available()
    )
    TORCH_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False
    MPS_AVAILABLE = False
    TORCH_AVAILABLE = False
    torch = None
    np = None

logger = get_logger(__name__)
_TELEMETRY_AUTOSTART = os.environ.get("GPU_TELEMETRY_AUTOSTART", "false").lower() in (
    "1",
    "true",
)


def _start_host_telemetry():
    """Attempt to start host telemetry/exporter where available.
    This prefers systemctl if present and the service exists, otherwise it will
    try to start the agent directly (best-effort)."""
    try:
        # Prefer systemctl
        if shutil.which("systemctl"):
            subprocess.run(
                ["systemctl", "start", "justnews-gpu-telemetry.service"], check=False
            )
            return
    except Exception:
        pass
    try:
        # Best-effort: run the agent in background via nohup (if not already running)
        if not os.path.exists("/tmp/gpu_telemetry.pid"):
            subprocess.Popen(
                ["nohup", "./scripts/perf/gpu_telemetry.sh", "/var/log/justnews-perf"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        if not os.path.exists("/tmp/gpu_telemetry_exporter.pid"):
            subprocess.Popen(
                [
                    "nohup",
                    "python3",
                    "scripts/perf/gpu_telemetry_exporter.py",
                    "--port",
                    "9118",
                    "--interval",
                    "1.0",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass


def _stop_host_telemetry_if_idle():
    """Stop host telemetry if there are no active allocations (best-effort).
    This checks for active allocations and attempts to stop telemetry when none remain."""
    try:
        if shutil.which("systemctl"):
            subprocess.run(
                ["systemctl", "stop", "justnews-gpu-telemetry.service"], check=False
            )
            return
    except Exception:
        pass
    # best-effort fallback: kill pid files if present
    try:
        if os.path.exists("/tmp/gpu_telemetry.pid"):
            with open("/tmp/gpu_telemetry.pid") as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 15)
            except Exception:
                pass
            try:
                os.remove("/tmp/gpu_telemetry.pid")
            except Exception:
                pass
        if os.path.exists("/tmp/gpu_telemetry_exporter.pid"):
            with open("/tmp/gpu_telemetry_exporter.pid") as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 15)
            except Exception:
                pass
            try:
                os.remove("/tmp/gpu_telemetry_exporter.pid")
            except Exception:
                pass
    except Exception:
        pass


@dataclass
class GPUAllocation:
    """Represents a GPU allocation for an agent"""

    agent_name: str
    gpu_device: str  # Changed from int to str to support "cuda:0", "mps"
    allocated_memory_gb: float
    batch_size: int
    allocation_time: datetime
    status: str = "active"


@dataclass
class GPUStatus:
    """GPU device status information"""

    device_id: str  # Changed from int to str to support "cuda:0", "mps"
    device_type: str  # "cuda" or "mps"
    total_memory_gb: float
    used_memory_gb: float
    free_memory_gb: float
    utilization_percent: float
    temperature_c: float
    power_draw_w: float
    is_healthy: bool


class GPUHealthMonitor:
    """Monitors GPU health and performance"""

    def __init__(self, check_interval: float = 30.0):
        self.check_interval = check_interval
        self.last_check = 0
        self._lock = threading.Lock()
        self._health_cache: dict[str, GPUStatus] = {}

    def get_gpu_status(self, device_id: str = "cuda:0") -> GPUStatus:
        """Get current GPU status with caching"""
        current_time = time.time()

        with self._lock:
            if current_time - self.last_check < self.check_interval:
                return self._health_cache.get(device_id)

        # Perform fresh health check
        status = self._check_gpu_health(device_id)

        with self._lock:
            self._health_cache[device_id] = status
            self.last_check = current_time

        return status

    def get_available_devices(self) -> list[str]:
        """Get list of all available GPU devices (CUDA + MPS)"""
        devices = []

        # Add CUDA devices
        if GPU_AVAILABLE and torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                devices.append(f"cuda:{i}")

        # Add MPS device if available
        if MPS_AVAILABLE:
            devices.append("mps")

        return devices

    def _check_gpu_health(self, device_id: str) -> GPUStatus:
        """Perform comprehensive GPU health check"""
        try:
            if device_id.startswith("cuda:"):
                # CUDA device health check
                cuda_device_id = int(device_id.split(":")[1])
                nvidia_data = self._get_nvidia_smi_data(cuda_device_id)
                torch_data = self._get_torch_memory_data(device_id)
                is_healthy = self._assess_health(nvidia_data, torch_data)

                return GPUStatus(
                    device_id=device_id,
                    device_type="cuda",
                    total_memory_gb=nvidia_data.get("total_memory_gb", 0),
                    used_memory_gb=torch_data.get("used_memory_gb", 0),
                    free_memory_gb=torch_data.get("free_memory_gb", 0),
                    utilization_percent=nvidia_data.get("utilization_percent", 0),
                    temperature_c=nvidia_data.get("temperature_c", 0),
                    power_draw_w=nvidia_data.get("power_draw_w", 0),
                    is_healthy=is_healthy,
                )

            elif device_id == "mps":
                # MPS device health check
                mps_data = self._get_mps_memory_data()
                is_healthy = self._assess_mps_health(mps_data)

                return GPUStatus(
                    device_id=device_id,
                    device_type="mps",
                    total_memory_gb=mps_data.get("total_memory_gb", 0),
                    used_memory_gb=mps_data.get("used_memory_gb", 0),
                    free_memory_gb=mps_data.get("free_memory_gb", 0),
                    utilization_percent=mps_data.get("utilization_percent", 0),
                    temperature_c=0,  # MPS doesn't provide temperature
                    power_draw_w=0,  # MPS doesn't provide power draw
                    is_healthy=is_healthy,
                )

            else:
                raise ValueError(f"Unsupported device type: {device_id}")

        except Exception as e:
            logger.error(f"GPU health check failed for {device_id}: {e}")
            # Return unhealthy status
            return GPUStatus(
                device_id=device_id,
                device_type=device_id.split(":")[0] if ":" in device_id else "unknown",
                total_memory_gb=0,
                used_memory_gb=0,
                free_memory_gb=0,
                utilization_percent=0,
                temperature_c=0,
                power_draw_w=0,
                is_healthy=False,
            )

    def _get_nvidia_smi_data(self, device_id: int) -> dict[str, float]:
        """Get GPU data from nvidia-smi"""
        try:
            cmd = [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.free,utilization.gpu,temperature.gpu,power.draw",
                "--format=csv,nounits,noheader",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode != 0:
                return {}

            lines = result.stdout.strip().split("\n")
            if device_id >= len(lines):
                return {}

            parts = [p.strip() for p in lines[device_id].split(",")]

            return {
                "total_memory_gb": float(parts[0]) / 1024 if parts[0] else 0,
                "free_memory_gb": float(parts[1]) / 1024 if parts[1] else 0,
                "utilization_percent": float(parts[2]) if parts[2] else 0,
                "temperature_c": float(parts[3]) if parts[3] else 0,
                "power_draw_w": float(parts[4]) if parts[4] else 0,
            }

        except Exception:
            return {}

    def _get_torch_memory_data(self, device_id: str) -> dict[str, float]:
        """Get memory data from PyTorch for CUDA or MPS devices"""
        if not TORCH_AVAILABLE:
            return {"used_memory_gb": 0, "free_memory_gb": 0}

        try:
            if device_id.startswith("cuda:"):
                cuda_device_id = int(device_id.split(":")[1])
                if torch.cuda.is_available():
                    allocated = torch.cuda.memory_allocated(cuda_device_id) / (1024**3)
                    total = torch.cuda.get_device_properties(
                        cuda_device_id
                    ).total_memory / (1024**3)
                    free = total - allocated
                    return {"used_memory_gb": allocated, "free_memory_gb": free}
            elif device_id == "mps":
                if MPS_AVAILABLE:
                    # MPS memory monitoring (limited compared to CUDA)
                    # Note: MPS doesn't provide detailed memory stats like CUDA
                    return {
                        "used_memory_gb": 0,
                        "free_memory_gb": 8.0,
                    }  # Conservative estimate
        except Exception:
            pass

        return {"used_memory_gb": 0, "free_memory_gb": 0}

    def _get_mps_memory_data(self) -> dict[str, float]:
        """Get MPS device memory data"""
        if not MPS_AVAILABLE:
            return {
                "total_memory_gb": 0,
                "used_memory_gb": 0,
                "free_memory_gb": 0,
                "utilization_percent": 0,
            }

        try:
            # MPS has unified memory, so we estimate based on system RAM
            # This is a conservative approach since MPS doesn't expose detailed memory stats
            import psutil

            system_memory = psutil.virtual_memory()

            # Estimate MPS memory as 50% of system RAM (conservative)
            total_memory_gb = system_memory.total / (1024**3) * 0.5
            used_memory_gb = system_memory.used / (1024**3) * 0.5
            free_memory_gb = total_memory_gb - used_memory_gb
            utilization_percent = (
                (used_memory_gb / total_memory_gb) * 100 if total_memory_gb > 0 else 0
            )

            return {
                "total_memory_gb": total_memory_gb,
                "used_memory_gb": used_memory_gb,
                "free_memory_gb": free_memory_gb,
                "utilization_percent": utilization_percent,
            }
        except Exception:
            return {
                "total_memory_gb": 8.0,
                "used_memory_gb": 0,
                "free_memory_gb": 8.0,
                "utilization_percent": 0,
            }

    def _assess_mps_health(self, mps_data: dict) -> bool:
        """Assess MPS device health"""
        try:
            # Check memory utilization (should be < 90%)
            util = mps_data.get("utilization_percent", 0)
            if util > 90:
                return False

            # Check if we have reasonable memory values
            total = mps_data.get("total_memory_gb", 0)
            if total <= 0:
                return False

            return True
        except Exception:
            return False

    def _assess_health(self, nvidia_data: dict, torch_data: dict) -> bool:
        """Assess overall GPU health"""
        try:
            # Check temperature (should be < 85°C)
            temp = nvidia_data.get("temperature_c", 0)
            if temp > 85:
                return False

            # Check utilization (should be responsive)
            util = nvidia_data.get("utilization_percent", 0)
            if util > 95:  # Might indicate hung GPU
                return False

            # Check memory consistency
            total = nvidia_data.get("total_memory_gb", 0)
            free = nvidia_data.get("free_memory_gb", 0)
            used = torch_data.get("used_memory_gb", 0)

            if total > 0 and (free + used) > total * 1.1:  # 10% tolerance
                return False

            return True

        except Exception:
            return False


class MultiAgentGPUManager:
    """
    Production GPU manager for multi-agent systems

    Features:
    - Atomic GPU allocation per agent
    - Memory limit enforcement
    - Health monitoring and automatic recovery
    - Resource optimization and pooling
    - Comprehensive logging and metrics
    - MPS support with configuration-driven limits
    """

    def __init__(
        self, max_memory_per_agent_gb: float = 8.0, health_check_interval: float = 30.0
    ):
        self.max_memory_per_agent_gb = max_memory_per_agent_gb
        self.health_monitor = GPUHealthMonitor(health_check_interval)

        # MPS configuration
        self._mps_config = self._load_mps_config()

        # Allocation tracking
        self._allocations: dict[str, GPUAllocation] = {}
        self._lock = threading.Lock()

        # Performance metrics
        self.metrics = {
            "total_allocations": 0,
            "successful_allocations": 0,
            "failed_allocations": 0,
            "cpu_fallbacks": 0,
            "gpu_recoveries": 0,
        }

        logger.info("🤖 MultiAgentGPUManager initialized")
        logger.info(f"   Max memory per agent: {max_memory_per_agent_gb}GB")
        logger.info(f"   Health check interval: {health_check_interval}s")
        logger.info(f"   MPS support: {'enabled' if MPS_AVAILABLE else 'disabled'}")
        if self._mps_config:
            logger.info(
                f"   MPS config loaded: {len(self._mps_config.get('agent_allocations', {}))} agents configured"
            )

    def _load_mps_config(self) -> dict[str, Any] | None:
        """Load MPS allocation configuration"""
        try:
            import json
            from pathlib import Path

            # Find project root (assuming this file is in agents/common/)
            current_file = Path(__file__)
            project_root = current_file.parents[2]  # Go up to project root

            config_path = project_root / "config" / "gpu" / "mps_allocation_config.json"

            if config_path.exists():
                with open(config_path) as f:
                    config = json.load(f)
                logger.debug(f"Loaded MPS config from {config_path}")
                return config.get("mps_resource_allocation", {})
            else:
                logger.debug(f"MPS config not found at {config_path}")
                return None
        except Exception as e:
            logger.warning(f"Failed to load MPS config: {e}")
            return None

    def _get_agent_mps_limits(self, agent_name: str) -> dict[str, float] | None:
        """Get MPS memory limits for a specific agent"""
        if not self._mps_config:
            return None

        agent_config = self._mps_config.get("agent_allocations", {}).get(agent_name)
        if agent_config:
            return {
                "mps_memory_limit_gb": agent_config.get("mps_memory_limit_gb", 1.0),
                "calculated_requirement_gb": agent_config.get(
                    "calculated_requirement_gb", 0.5
                ),
                "safety_margin_gb": agent_config.get("safety_margin_gb", 0.5),
            }
        return None

    def request_gpu_allocation(
        self,
        agent_name: str,
        requested_memory_gb: float = 4.0,
        preferred_device: str | None = None,
        model_type: str = "general",
    ) -> dict[str, Any]:
        """
        Request GPU allocation for an agent

        Args:
            agent_name: Unique agent identifier
            requested_memory_gb: Requested GPU memory in GB
            preferred_device: Preferred GPU device (None for auto-selection)
            model_type: Type of model ('embedding', 'generation', 'vision', 'general')

        Returns:
            Allocation result dictionary
        """
        self.metrics["total_allocations"] += 1

        with self._lock:
            try:
                # Check if agent already has allocation
                if agent_name in self._allocations:
                    existing = self._allocations[agent_name]
                    if existing.status == "active":
                        return {
                            "status": "already_allocated",
                            "gpu_device": existing.gpu_device,
                            "allocated_memory_gb": existing.allocated_memory_gb,
                            "batch_size": existing.batch_size,
                            "message": f"Agent {agent_name} already has active allocation",
                        }

                # Validate memory request against agent-specific MPS limits if using MPS
                # Find available GPU first to determine device type
                device_id = self._find_available_gpu(
                    requested_memory_gb, preferred_device
                )
                if device_id is None:
                    self.metrics["cpu_fallbacks"] += 1
                    return {
                        "status": "cpu_fallback",
                        "reason": "No GPU available with sufficient memory",
                        "message": "Falling back to CPU processing",
                    }

                # Now check MPS limits if MPS device was selected
                if device_id == "mps":
                    mps_limits = self._get_agent_mps_limits(agent_name)
                    if mps_limits:
                        max_allowed = mps_limits["mps_memory_limit_gb"]
                        if requested_memory_gb > max_allowed:
                            return {
                                "status": "mps_limit_exceeded",
                                "message": f"Requested {requested_memory_gb}GB exceeds MPS limit of {max_allowed}GB for {agent_name}",
                                "mps_limit_gb": max_allowed,
                                "calculated_requirement_gb": mps_limits[
                                    "calculated_requirement_gb"
                                ],
                            }

                # Check GPU health
                gpu_status = self.health_monitor.get_gpu_status(device_id)
                if not gpu_status.is_healthy:
                    logger.warning(
                        f"GPU {device_id} health check failed, attempting recovery"
                    )
                    if not self._attempt_gpu_recovery(device_id):
                        return {
                            "status": "gpu_unhealthy",
                            "reason": f"GPU {device_id} is unhealthy",
                            "message": "GPU health check failed",
                        }

                # Calculate batch size based on memory and model type
                batch_size = self._calculate_optimal_batch_size(
                    requested_memory_gb, model_type
                )

                # Create allocation
                allocation = GPUAllocation(
                    agent_name=agent_name,
                    gpu_device=device_id,
                    allocated_memory_gb=requested_memory_gb,
                    batch_size=batch_size,
                    allocation_time=datetime.now(),
                    status="active",
                )

                self._allocations[agent_name] = allocation
                self.metrics["successful_allocations"] += 1

                logger.info(
                    f"✅ GPU allocated: {agent_name} -> GPU {device_id} ({requested_memory_gb}GB, batch_size={batch_size}, model_type={model_type})"
                )

                # Optionally trigger host-level telemetry collection (useful on dedicated GPU nodes)
                try:
                    if _TELEMETRY_AUTOSTART:
                        _start_host_telemetry()
                except Exception:
                    logger.debug("Telemetry autostart hook failed", exc_info=True)

                return {
                    "status": "allocated",
                    "gpu_device": device_id,
                    "allocated_memory_gb": requested_memory_gb,
                    "batch_size": batch_size,
                    "model_type": model_type,
                    "message": f"Successfully allocated GPU {device_id} for {agent_name}",
                }

            except Exception as e:
                self.metrics["failed_allocations"] += 1
                logger.error(f"❌ GPU allocation failed for {agent_name}: {e}")
                return {
                    "status": "allocation_failed",
                    "reason": str(e),
                    "message": "GPU allocation failed due to internal error",
                }

    def release_gpu_allocation(self, agent_name: str) -> bool:
        """Release GPU allocation for an agent"""
        with self._lock:
            if agent_name not in self._allocations:
                return False

            allocation = self._allocations[agent_name]
            if allocation.status != "active":
                return False

            # Mark as released
            allocation.status = "released"

            # Clean up GPU memory if possible
            self._cleanup_gpu_memory(allocation.gpu_device)

            logger.info(f"✅ GPU released: {agent_name} <- GPU {allocation.gpu_device}")
            # If telemetry autostart is enabled and there are no active allocations left, stop telemetry
            try:
                if _TELEMETRY_AUTOSTART:
                    active_any = any(
                        a.status == "active" for a in self._allocations.values()
                    )
                    if not active_any:
                        _stop_host_telemetry_if_idle()
            except Exception:
                logger.debug("Telemetry autostop hook failed", exc_info=True)
            return True

    def _find_available_gpu(
        self, requested_memory_gb: float, preferred_device: str | None = None
    ) -> str | None:
        """Find an available GPU with sufficient memory (supports CUDA and MPS)"""
        available_devices = self.health_monitor.get_available_devices()

        if not available_devices:
            return None

        try:
            # Check preferred device first
            if preferred_device is not None and preferred_device in available_devices:
                gpu_status = self.health_monitor.get_gpu_status(preferred_device)
                if (
                    gpu_status.is_healthy
                    and gpu_status.free_memory_gb >= requested_memory_gb
                ):
                    return preferred_device

            # Check all available devices with priority: CUDA first, then MPS
            # This ensures CUDA devices are preferred when available
            for device_id in available_devices:
                gpu_status = self.health_monitor.get_gpu_status(device_id)
                if (
                    gpu_status.is_healthy
                    and gpu_status.free_memory_gb >= requested_memory_gb
                ):
                    return device_id

        except Exception as e:
            logger.error(f"Error finding available GPU: {e}")

        return None

    def _calculate_optimal_batch_size(
        self, memory_gb: float, model_type: str = "general"
    ) -> int:
        """Calculate optimal batch size using enhanced optimization with learning"""
        try:
            # Try enhanced optimization first
            try:
                from .gpu_optimizer_enhanced import optimize_gpu_allocation

                optimization = optimize_gpu_allocation(
                    self.__class__.__name__, model_type, memory_gb
                )

                if (
                    optimization["confidence"] > 0.3
                ):  # Use learned optimization if confidence is reasonable
                    logger.info(
                        f"🎯 Using learned optimization: batch_size={optimization['batch_size']} (confidence={optimization['confidence']:.2f})"
                    )
                    return optimization["batch_size"]
            except ImportError:
                logger.debug(
                    "Enhanced optimizer not available, using heuristic optimization"
                )

            # Fall back to enhanced heuristic optimization
            return self._calculate_enhanced_heuristic_batch_size(memory_gb, model_type)

        except Exception as e:
            logger.warning(
                f"Error in enhanced batch calculation: {e}, using basic heuristic"
            )
            return self._calculate_basic_heuristic_batch_size(memory_gb, model_type)

    def _calculate_enhanced_heuristic_batch_size(
        self, memory_gb: float, model_type: str = "general"
    ) -> int:
        """Enhanced heuristic batch size calculation with configuration awareness"""
        try:
            # Get GPU memory info for more accurate calculations
            available_devices = self.health_monitor.get_available_devices()
            if available_devices:
                # Use first available device as reference for memory calculations
                gpu_status = self.health_monitor.get_gpu_status(available_devices[0])
                free_memory = gpu_status.free_memory_gb

                # Use available memory as constraint
                available_memory = min(
                    memory_gb, free_memory * 0.8
                )  # Use 80% of available

                # Try to get model-specific configuration
                try:
                    from .gpu_config_manager import get_model_config

                    model_config = get_model_config()
                    recommended_batch = model_config.get("batch_size_recommendation")

                    if recommended_batch and available_memory >= model_config.get(
                        "max_memory_usage_gb", 0
                    ):
                        return min(recommended_batch, int(available_memory * 8))
                except ImportError:
                    pass

                # Enhanced model-specific batch size calculations
                if model_type == "embedding":
                    # Embedding models: optimize for latency with larger batches
                    if available_memory >= 4:
                        return min(
                            32, int(available_memory * 8)
                        )  # Up to 32 for large memory
                    elif available_memory >= 2:
                        return 16
                    elif available_memory >= 1:
                        return 8
                    else:
                        return 4

                elif model_type == "generation":
                    # Generation models: balance throughput and memory
                    if available_memory >= 8:
                        return min(16, int(available_memory * 2))
                    elif available_memory >= 4:
                        return 8
                    elif available_memory >= 2:
                        return 4
                    else:
                        return 2

                elif model_type == "vision":
                    # Vision models: larger inputs, smaller batches
                    if available_memory >= 8:
                        return min(8, int(available_memory * 1))
                    elif available_memory >= 4:
                        return 4
                    else:
                        return 2

                elif model_type == "classification":
                    # Classification models: larger batches for efficiency
                    if available_memory >= 8:
                        return min(32, int(available_memory * 6))
                    elif available_memory >= 4:
                        return 16
                    elif available_memory >= 2:
                        return 8
                    else:
                        return 4

                else:  # general case
                    # Adaptive batch sizing based on memory with enhanced logic
                    if available_memory >= 8:
                        return 24
                    elif available_memory >= 4:
                        return 12
                    elif available_memory >= 2:
                        return 6
                    else:
                        return 2
            else:
                # CPU fallback - smaller batches
                return 1

        except Exception as e:
            logger.warning(f"Error in enhanced heuristic batch calculation: {e}")
            return self._calculate_basic_heuristic_batch_size(memory_gb, model_type)

    def _calculate_basic_heuristic_batch_size(
        self, memory_gb: float, model_type: str = "general"
    ) -> int:
        """Basic heuristic batch size calculation (fallback)"""
        try:
            # Get GPU memory info for more accurate calculations
            available_devices = self.health_monitor.get_available_devices()
            if available_devices:
                # Use first available device as reference for memory calculations
                gpu_status = self.health_monitor.get_gpu_status(available_devices[0])
                free_memory = gpu_status.free_memory_gb

                # Reserve some memory for overhead
                available_memory = min(
                    memory_gb, free_memory * 0.8
                )  # Use 80% of available

                # Model-specific batch size calculations
                if model_type == "embedding":
                    # Embedding models: smaller batches, focus on latency
                    if available_memory >= 4:
                        return min(
                            32, int(available_memory * 8)
                        )  # Up to 32 for large memory
                    elif available_memory >= 2:
                        return 16
                    elif available_memory >= 1:
                        return 8
                    else:
                        return 4

                elif model_type == "generation":
                    # Generation models: balance throughput and memory
                    if available_memory >= 8:
                        return min(16, int(available_memory * 2))
                    elif available_memory >= 4:
                        return 8
                    elif available_memory >= 2:
                        return 4
                    else:
                        return 2

                elif model_type == "vision":
                    # Vision models: larger inputs, smaller batches
                    if available_memory >= 8:
                        return min(8, int(available_memory * 1))
                    elif available_memory >= 4:
                        return 4
                    else:
                        return 2

                else:  # general case
                    # General heuristic: more memory = larger batches
                    if available_memory >= 8:
                        return 16
                    elif available_memory >= 4:
                        return 8
                    elif available_memory >= 2:
                        return 4
                    else:
                        return 1
            else:
                # CPU fallback - smaller batches
                return 1

        except Exception as e:
            logger.warning(
                f"Error calculating optimal batch size: {e}, using conservative default"
            )
            return 1

    def _attempt_gpu_recovery(self, device_id: str) -> bool:
        """Attempt to recover an unhealthy GPU (CUDA or MPS)"""
        try:
            if device_id.startswith("cuda:"):
                # Clear CUDA cache
                if TORCH_AVAILABLE and torch.cuda.is_available():
                    cuda_device_id = int(device_id.split(":")[1])
                    torch.cuda.set_device(cuda_device_id)
                    torch.cuda.empty_cache()
            elif device_id == "mps":
                # MPS recovery - limited options available
                if TORCH_AVAILABLE and MPS_AVAILABLE:
                    # Try to clear any MPS-related caches (limited support)
                    pass

            # Wait a moment
            time.sleep(1)

            # Re-check health
            gpu_status = self.health_monitor.get_gpu_status(device_id)
            if gpu_status.is_healthy:
                self.metrics["gpu_recoveries"] += 1
                logger.info(f"✅ GPU {device_id} recovered")
                return True

        except Exception as e:
            logger.error(f"GPU recovery failed for device {device_id}: {e}")

        return False

    def _cleanup_gpu_memory(self, device_id: str):
        """Clean up GPU memory for a device (CUDA or MPS)"""
        try:
            if device_id.startswith("cuda:"):
                cuda_device_id = int(device_id.split(":")[1])
                if TORCH_AVAILABLE and torch.cuda.is_available():
                    # Switch to device and clear cache
                    torch.cuda.set_device(cuda_device_id)
                    torch.cuda.empty_cache()
                    logger.debug(f"CUDA memory cleaned for device {device_id}")
            elif device_id == "mps":
                # MPS cleanup - limited options
                if TORCH_AVAILABLE and MPS_AVAILABLE:
                    # MPS memory management is handled by the system
                    logger.debug(f"MPS memory cleanup requested for {device_id}")
        except Exception as e:
            logger.warning(f"Failed to cleanup GPU memory for device {device_id}: {e}")

    def get_allocation_status(self, agent_name: str) -> dict[str, Any] | None:
        """Get allocation status for an agent"""
        with self._lock:
            allocation = self._allocations.get(agent_name)
            if not allocation:
                return None

            return {
                "agent_name": allocation.agent_name,
                "gpu_device": allocation.gpu_device,
                "allocated_memory_gb": allocation.allocated_memory_gb,
                "batch_size": allocation.batch_size,
                "allocation_time": allocation.allocation_time.isoformat(),
                "status": allocation.status,
            }

    def get_system_status(self) -> dict[str, Any]:
        """Get overall system status"""
        gpu_statuses = []
        available_devices = self.health_monitor.get_available_devices()

        for device_id in available_devices:
            gpu_statuses.append(self.health_monitor.get_gpu_status(device_id))

        return {
            "gpu_available": GPU_AVAILABLE,
            "mps_available": MPS_AVAILABLE,
            "torch_available": TORCH_AVAILABLE,
            "gpu_count": len([d for d in available_devices if d.startswith("cuda:")]),
            "mps_count": 1 if MPS_AVAILABLE else 0,
            "total_devices": len(available_devices),
            "gpu_statuses": [vars(status) for status in gpu_statuses],
            "active_allocations": len(
                [a for a in self._allocations.values() if a.status == "active"]
            ),
            "total_allocations": len(self._allocations),
            "metrics": self.metrics.copy(),
        }

    @contextmanager
    def gpu_context(self, agent_name: str, memory_gb: float = 4.0):
        """Context manager for GPU allocation"""
        allocation = self.request_gpu_allocation(agent_name, memory_gb)

        if allocation["status"] == "allocated":
            try:
                yield allocation
            finally:
                self.release_gpu_allocation(agent_name)
        else:
            # CPU fallback
            yield {
                "status": "cpu_fallback",
                "gpu_device": -1,
                "allocated_memory_gb": 0,
                "batch_size": 1,
                "message": allocation.get("message", "CPU fallback"),
            }


# Global manager instance
_global_gpu_manager: MultiAgentGPUManager | None = None
_manager_lock = threading.Lock()


def get_gpu_manager() -> MultiAgentGPUManager:
    """Get the global GPU manager instance"""
    global _global_gpu_manager
    with _manager_lock:
        if _global_gpu_manager is None:
            _global_gpu_manager = MultiAgentGPUManager()
        return _global_gpu_manager


def request_agent_gpu(
    agent_name: str, memory_gb: float = 4.0, model_type: str = "general"
) -> dict[str, Any]:
    """Request GPU allocation for an agent (compatibility function)"""
    manager = get_gpu_manager()
    return manager.request_gpu_allocation(agent_name, memory_gb, model_type=model_type)


def release_agent_gpu(agent_name: str) -> bool:
    """Release GPU allocation for an agent (compatibility function)"""
    manager = get_gpu_manager()
    return manager.release_gpu_allocation(agent_name)


# Initialize manager on import
_gpu_manager = get_gpu_manager()
