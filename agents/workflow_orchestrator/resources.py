"""
Resource Monitor for Workflow Orchestrator.

This module provides system resource monitoring capabilities (CPU, RAM, GPU)
to help the orchestrator make backpressure decisions.
"""

import shutil
import subprocess
from dataclasses import dataclass

import psutil

from common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class SystemStats:
    cpu_percent: float
    memory_percent: float
    gpu_utilization: float | None = None
    gpu_memory_percent: float | None = None


class ResourceMonitor:
    def __init__(self):
        self.has_nvidia_smi = shutil.which("nvidia-smi") is not None

    def get_stats(self) -> SystemStats:
        """Get current system statistics."""
        cpu = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory().percent

        gpu_util = None
        gpu_mem = None

        if self.has_nvidia_smi:
            try:
                # Query all GPUs, take the max utilization (conservative approach)
                # We assume if *any* GPU is saturated, we should throttle.
                result = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=utilization.gpu,utilization.memory",
                        "--format=csv,nounits,noheader",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().splitlines()
                    if lines:
                        utils = []
                        mems = []
                        for line in lines:
                            parts = line.split(",")
                            if len(parts) >= 2:
                                utils.append(float(parts[0].strip()))
                                mems.append(float(parts[1].strip()))

                        if utils:
                            gpu_util = max(utils)
                        if mems:
                            gpu_mem = max(mems)
            except Exception as e:
                logger.warning(f"Failed to query stats via nvidia-smi: {e}")

        return SystemStats(
            cpu_percent=cpu,
            memory_percent=memory,
            gpu_utilization=gpu_util,
            gpu_memory_percent=gpu_mem,
        )

    def check_health(self, thresholds: dict) -> bool:
        """
        Check if system is healthy enough to accept new tasks.
        Returns True if resources are below thresholds.
        """
        stats = self.get_stats()

        cpu_limit = thresholds.get("max_cpu_percent", 90)
        mem_limit = thresholds.get("max_memory_percent", 90)
        gpu_util_limit = thresholds.get("max_gpu_utilization", 95)
        gpu_mem_limit = thresholds.get("max_gpu_memory_percent", 95)

        if stats.cpu_percent > cpu_limit:
            logger.warning(f"Throttling: CPU at {stats.cpu_percent}% > {cpu_limit}%")
            return False

        if stats.memory_percent > mem_limit:
            logger.warning(f"Throttling: Memory at {stats.memory_percent}% > {mem_limit}%")
            return False

        if stats.gpu_utilization is not None and stats.gpu_utilization > gpu_util_limit:
            logger.warning(f"Throttling: GPU Util at {stats.gpu_utilization}% > {gpu_util_limit}%")
            return False

        if stats.gpu_memory_percent is not None and stats.gpu_memory_percent > gpu_mem_limit:
            logger.warning(f"Throttling: GPU Mem at {stats.gpu_memory_percent}% > {gpu_mem_limit}%")
            return False

        return True
