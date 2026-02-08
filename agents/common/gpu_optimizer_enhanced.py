"""
Enhanced GPU Resource Allocation Optimizer
Advanced performance optimization for GPU resource allocation with learning capabilities

Features:
- Historical performance learning
- Dynamic batch size optimization
- Memory usage prediction
- Agent-specific optimization profiles
- Real-time performance adaptation
"""

import json
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

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

logger = get_logger(__name__)


class PerformanceRecord(NamedTuple):
    """Record of performance metrics for optimization learning"""

    agent_name: str
    model_type: str
    batch_size: int
    memory_used_gb: float
    processing_time_seconds: float
    throughput_items_per_second: float
    gpu_utilization_percent: float
    timestamp: datetime
    success: bool


class ResourceProfile:
    """Performance profile for an agent/model combination"""

    def __init__(self, agent_name: str, model_type: str):
        self.agent_name = agent_name
        self.model_type = model_type
        self.performance_history: deque = deque(maxlen=1000)
        self.optimal_batch_sizes: dict[float, int] = {}
        self.memory_usage_patterns: dict[int, float] = {}
        self.last_updated = datetime.now()

    def add_performance_record(self, record: PerformanceRecord):
        """Add a performance record and update optimization data"""
        self.performance_history.append(record)
        self.last_updated = datetime.now()

        # Update memory usage patterns
        self.memory_usage_patterns[record.batch_size] = record.memory_used_gb

        # Update optimal batch sizes for different memory constraints
        self._update_optimal_batch_sizes()

    def _update_optimal_batch_sizes(self):
        """Update optimal batch size recommendations based on historical data"""
        if len(self.performance_history) < 5:
            return

        # Group by memory allocation
        memory_groups = defaultdict(list)
        for record in self.performance_history:
            if record.success:
                memory_groups[record.memory_used_gb].append(record)

        # Find optimal batch size for each memory level
        for memory_gb, records in memory_groups.items():
            if len(records) >= 3:
                # Calculate throughput-weighted optimal batch size
                best_batch_size = max(
                    records, key=lambda r: r.throughput_items_per_second
                ).batch_size

                # Verify it's consistently good (top 25% of performances)
                throughputs = [r.throughput_items_per_second for r in records]
                threshold = np.percentile(throughputs, 75)

                if best_batch_size >= threshold:
                    self.optimal_batch_sizes[memory_gb] = best_batch_size

    def get_optimal_batch_size(self, memory_gb: float) -> int | None:
        """Get optimal batch size for given memory allocation"""
        if not self.optimal_batch_sizes:
            return None

        # Find closest memory allocation
        closest_memory = min(
            self.optimal_batch_sizes.keys(), key=lambda x: abs(x - memory_gb)
        )

        return self.optimal_batch_sizes.get(closest_memory)

    def predict_memory_usage(self, batch_size: int) -> float | None:
        """Predict memory usage for a given batch size"""
        if batch_size in self.memory_usage_patterns:
            return self.memory_usage_patterns[batch_size]

        # Linear interpolation for unknown batch sizes
        if len(self.memory_usage_patterns) >= 2:
            batch_sizes = sorted(self.memory_usage_patterns.keys())
            memory_usages = [self.memory_usage_patterns[bs] for bs in batch_sizes]

            if batch_size < batch_sizes[0]:
                # Extrapolate downwards
                slope = (memory_usages[1] - memory_usages[0]) / (
                    batch_sizes[1] - batch_sizes[0]
                )
                return memory_usages[0] + slope * (batch_size - batch_sizes[0])
            elif batch_size > batch_sizes[-1]:
                # Extrapolate upwards
                slope = (memory_usages[-1] - memory_usages[-2]) / (
                    batch_sizes[-1] - batch_sizes[-2]
                )
                return memory_usages[-1] + slope * (batch_size - batch_sizes[-1])
            else:
                # Interpolate
                return np.interp(batch_size, batch_sizes, memory_usages)

        return None


class EnhancedGPUOptimizer:
    """
    Advanced GPU resource allocation optimizer with learning capabilities

    Features:
    - Historical performance learning
    - Dynamic batch size optimization
    - Memory usage prediction
    - Agent-specific optimization profiles
    - Real-time performance adaptation
    """

    def __init__(self, history_file: str = "./config/gpu/optimization_history.json"):
        self.history_file = Path(history_file)
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

        # Performance profiles
        self.profiles: dict[str, ResourceProfile] = {}
        self.performance_history: deque = deque(maxlen=5000)

        # Optimization state
        self.learning_enabled = True
        self.adaptation_enabled = True

        # Load historical data
        self._load_history()

        # Start background optimization
        self._start_background_tasks()

        logger.info("🚀 Enhanced GPU Optimizer initialized")

    def _start_background_tasks(self):
        """Start background optimization tasks"""

        # Save history periodically
        def save_history_task():
            while True:
                time.sleep(300)  # Save every 5 minutes
                self._save_history()

        save_thread = threading.Thread(target=save_history_task, daemon=True)
        save_thread.start()

    def get_optimized_allocation(
        self, agent_name: str, model_type: str, requested_memory_gb: float
    ) -> dict[str, Any]:
        """
        Get optimized GPU allocation parameters

        Args:
            agent_name: Name of the agent
            model_type: Type of model (embedding, generation, vision, general)
            requested_memory_gb: Requested memory allocation

        Returns:
            Optimized allocation parameters
        """
        profile = self._get_or_create_profile(agent_name, model_type)

        # Get optimal batch size from learning
        optimal_batch_size = profile.get_optimal_batch_size(requested_memory_gb)

        if optimal_batch_size is None:
            # Fall back to heuristic-based calculation
            optimal_batch_size = self._calculate_heuristic_batch_size(
                requested_memory_gb, model_type
            )

        # Predict memory usage
        predicted_memory = profile.predict_memory_usage(optimal_batch_size)
        if predicted_memory is None:
            predicted_memory = requested_memory_gb

        # Adjust memory allocation based on prediction
        adjusted_memory = max(
            requested_memory_gb, predicted_memory * 1.1
        )  # 10% safety margin

        return {
            "batch_size": optimal_batch_size,
            "predicted_memory_gb": predicted_memory,
            "adjusted_memory_gb": adjusted_memory,
            "optimization_source": "learned"
            if profile.get_optimal_batch_size(requested_memory_gb)
            else "heuristic",
            "confidence": self._calculate_confidence(profile, optimal_batch_size),
        }

    def record_performance(
        self,
        agent_name: str,
        model_type: str,
        batch_size: int,
        memory_used_gb: float,
        processing_time_seconds: float,
        items_processed: int,
        gpu_utilization_percent: float,
        success: bool = True,
    ):
        """
        Record performance metrics for learning

        Args:
            agent_name: Name of the agent
            model_type: Type of model
            batch_size: Batch size used
            memory_used_gb: Actual memory usage
            processing_time_seconds: Processing time
            items_processed: Number of items processed
            gpu_utilization_percent: GPU utilization percentage
            success: Whether the operation was successful
        """
        if not self.learning_enabled:
            return

        throughput = (
            items_processed / processing_time_seconds
            if processing_time_seconds > 0
            else 0
        )

        record = PerformanceRecord(
            agent_name=agent_name,
            model_type=model_type,
            batch_size=batch_size,
            memory_used_gb=memory_used_gb,
            processing_time_seconds=processing_time_seconds,
            throughput_items_per_second=throughput,
            gpu_utilization_percent=gpu_utilization_percent,
            timestamp=datetime.now(),
            success=success,
        )

        # Add to global history
        self.performance_history.append(record)

        # Add to profile
        profile = self._get_or_create_profile(agent_name, model_type)
        profile.add_performance_record(record)

        logger.debug(
            f"📊 Performance recorded: {agent_name} {model_type} batch_size={batch_size} throughput={throughput:.2f}"
        )

    def _get_or_create_profile(
        self, agent_name: str, model_type: str
    ) -> ResourceProfile:
        """Get or create a performance profile"""
        profile_key = f"{agent_name}_{model_type}"

        if profile_key not in self.profiles:
            self.profiles[profile_key] = ResourceProfile(agent_name, model_type)

        return self.profiles[profile_key]

    def _calculate_heuristic_batch_size(self, memory_gb: float, model_type: str) -> int:
        """Calculate batch size using enhanced heuristics"""
        try:
            # Get GPU memory info for more accurate calculations
            if GPU_AVAILABLE and torch.cuda.is_available():
                gpu_status = self._get_gpu_status()
                free_memory = gpu_status.get("free_memory_gb", 16.0)

                # Use available memory as constraint
                available_memory = min(memory_gb, free_memory * 0.8)

                # Model-specific optimizations with learning from common patterns
                if model_type == "embedding":
                    # Embedding models: optimize for latency with larger batches
                    base_batch = int(
                        available_memory * 12
                    )  # More aggressive than before
                    return self._constrain_batch_size(base_batch, 4, 64)

                elif model_type == "generation":
                    # Generation models: balance memory and throughput
                    base_batch = int(available_memory * 3)
                    return self._constrain_batch_size(base_batch, 1, 32)

                elif model_type == "vision":
                    # Vision models: smaller batches due to larger inputs
                    base_batch = int(available_memory * 1.5)
                    return self._constrain_batch_size(base_batch, 1, 16)

                elif model_type == "classification":
                    # Classification models: larger batches for efficiency
                    base_batch = int(available_memory * 8)
                    return self._constrain_batch_size(base_batch, 8, 128)

                else:  # general case
                    # Adaptive batch sizing based on memory
                    if available_memory >= 8:
                        return 24
                    elif available_memory >= 4:
                        return 12
                    elif available_memory >= 2:
                        return 6
                    else:
                        return 2
            else:
                # CPU fallback
                return 1

        except Exception as e:
            logger.warning(f"Error in heuristic batch calculation: {e}")
            return 4  # Conservative default

    def _constrain_batch_size(
        self, batch_size: int, min_size: int, max_size: int
    ) -> int:
        """Constrain batch size within reasonable bounds"""
        return max(min_size, min(max_size, batch_size))

    def _get_gpu_status(self) -> dict[str, float]:
        """Get current GPU status"""
        try:
            if GPU_AVAILABLE and torch.cuda.is_available():
                device_id = 0  # Use first GPU
                total_memory = torch.cuda.get_device_properties(
                    device_id
                ).total_memory / (1024**3)
                allocated = torch.cuda.memory_allocated(device_id) / (1024**3)
                free_memory = total_memory - allocated

                return {
                    "total_memory_gb": total_memory,
                    "free_memory_gb": free_memory,
                    "allocated_memory_gb": allocated,
                }
        except Exception:
            pass

        return {
            "total_memory_gb": 24.0,
            "free_memory_gb": 16.0,
            "allocated_memory_gb": 8.0,
        }

    def _calculate_confidence(self, profile: ResourceProfile, batch_size: int) -> float:
        """Calculate confidence score for batch size recommendation"""
        if not profile.performance_history:
            return 0.0

        # Count successful records with this batch size
        matching_records = [
            r
            for r in profile.performance_history
            if r.batch_size == batch_size and r.success
        ]

        if not matching_records:
            return 0.0

        # Calculate confidence based on sample size and consistency
        sample_size = len(matching_records)

        # Base confidence on sample size (more samples = higher confidence)
        size_confidence = min(1.0, sample_size / 10.0)  # Max confidence at 10 samples

        # Calculate throughput consistency
        throughputs = [r.throughput_items_per_second for r in matching_records]
        if len(throughputs) > 1:
            mean_throughput = np.mean(throughputs)
            std_throughput = np.std(throughputs)
            cv = std_throughput / mean_throughput if mean_throughput > 0 else 1.0
            consistency_confidence = max(0.0, 1.0 - cv)  # Lower CV = higher confidence
        else:
            consistency_confidence = 0.5

        return (size_confidence + consistency_confidence) / 2.0

    def get_optimization_stats(self) -> dict[str, Any]:
        """Get optimization statistics"""
        total_records = len(self.performance_history)
        successful_records = len([r for r in self.performance_history if r.success])

        if total_records == 0:
            return {"status": "no_data"}

        # Calculate average throughput by model type
        throughput_by_type = defaultdict(list)
        for record in self.performance_history:
            if record.success:
                throughput_by_type[record.model_type].append(
                    record.throughput_items_per_second
                )

        avg_throughput_by_type = {}
        for model_type, throughputs in throughput_by_type.items():
            avg_throughput_by_type[model_type] = np.mean(throughputs)

        return {
            "total_performance_records": total_records,
            "successful_records": successful_records,
            "success_rate": successful_records / total_records,
            "active_profiles": len(self.profiles),
            "average_throughput_by_type": dict(avg_throughput_by_type),
            "learning_enabled": self.learning_enabled,
            "adaptation_enabled": self.adaptation_enabled,
        }

    def _load_history(self):
        """Load historical performance data"""
        try:
            if self.history_file.exists():
                with open(self.history_file) as f:
                    data = json.load(f)

                # Restore performance records
                for record_data in data.get("performance_history", []):
                    record = PerformanceRecord(**record_data)
                    self.performance_history.append(record)

                    # Restore profile data
                    profile = self._get_or_create_profile(
                        record.agent_name, record.model_type
                    )
                    profile.add_performance_record(record)

                logger.info(
                    f"✅ Loaded {len(self.performance_history)} historical performance records"
                )

        except Exception as e:
            logger.warning(f"Failed to load optimization history: {e}")

    def _save_history(self):
        """Save historical performance data"""
        try:
            data = {
                "performance_history": [
                    record._asdict() for record in self.performance_history
                ],
                "profiles": {
                    key: {
                        "agent_name": profile.agent_name,
                        "model_type": profile.model_type,
                        "optimal_batch_sizes": profile.optimal_batch_sizes,
                        "memory_usage_patterns": profile.memory_usage_patterns,
                        "last_updated": profile.last_updated.isoformat(),
                    }
                    for key, profile in self.profiles.items()
                },
                "saved_at": datetime.now().isoformat(),
            }

            with open(self.history_file, "w") as f:
                json.dump(data, f, indent=2, default=str)

            logger.debug(
                f"💾 Saved {len(self.performance_history)} performance records"
            )

        except Exception as e:
            logger.error(f"Failed to save optimization history: {e}")


# Global optimizer instance
_optimizer: EnhancedGPUOptimizer | None = None
_optimizer_lock = threading.Lock()


def get_gpu_optimizer() -> EnhancedGPUOptimizer:
    """Get the global GPU optimizer instance"""
    global _optimizer
    with _optimizer_lock:
        if _optimizer is None:
            _optimizer = EnhancedGPUOptimizer()
        return _optimizer


def optimize_gpu_allocation(
    agent_name: str, model_type: str, memory_gb: float
) -> dict[str, Any]:
    """Get optimized GPU allocation parameters"""
    optimizer = get_gpu_optimizer()
    return optimizer.get_optimized_allocation(agent_name, model_type, memory_gb)


def record_gpu_performance(
    agent_name: str,
    model_type: str,
    batch_size: int,
    memory_used_gb: float,
    processing_time_seconds: float,
    items_processed: int,
    gpu_utilization_percent: float,
    success: bool = True,
):
    """Record GPU performance for optimization learning"""
    optimizer = get_gpu_optimizer()
    optimizer.record_performance(
        agent_name,
        model_type,
        batch_size,
        memory_used_gb,
        processing_time_seconds,
        items_processed,
        gpu_utilization_percent,
        success,
    )


def get_optimization_stats() -> dict[str, Any]:
    """Get optimization statistics"""
    optimizer = get_gpu_optimizer()
    return optimizer.get_optimization_stats()


# Initialize optimizer on import
_optimizer = get_gpu_optimizer()
