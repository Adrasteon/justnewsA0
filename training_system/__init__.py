"""
JustNews V2 Online Training System
================================

Comprehensive "Training On The Fly" system enabling continuous model improvement
through real-time news data processing.

Core Components:
- training_coordinator: Active learning and incremental model updates
- system_manager: Multi-agent coordination and monitoring
- dashboard: Web interface for training status and management
- utils: Helper functions and utilities

Features:
- Active Learning Selection (uncertainty-based + importance weighting)
- Incremental Model Updates with catastrophic forgetting prevention (EWC)
- Performance Monitoring with automatic rollback protection
- User Correction Integration with priority handling
- Multi-Agent Support with individual configurations

Performance:
- 28,800+ articles/hour data processing capacity
- Model updates every ~45 minutes per agent
- 82+ model updates/hour across all agents
- Real-time continuous learning from news pipeline
"""

__version__ = "2.0.0"
__author__ = "JustNews V2 Development Team"

# Core imports for easy access
try:
    from .core.system_manager import (
        SystemWideTrainingManager,
        collect_prediction,
        force_update,
        get_system_training_manager,
        get_training_dashboard,
        submit_correction,
    )
    from .core.training_coordinator import (
        ModelPerformance,
        OnTheFlyTrainingCoordinator,
        TrainingExample,
        add_training_feedback,
        add_user_correction,
        get_online_training_status,
        get_training_coordinator,
        initialize_online_training,
    )

    _imports_available = True

except ImportError as e:
    # Fallback for environments where dependencies aren't available
    _imports_available = False
    _import_error_message = str(e)

    def _not_available(*args, **kwargs):
        # Use a captured string to avoid referencing the exception object
        # which may not be available at call-time in some import scenarios.
        raise ImportError(f"Training system not available: {_import_error_message}")

    # Create placeholder functions
    OnTheFlyTrainingCoordinator = _not_available
    TrainingExample = _not_available
    ModelPerformance = _not_available
    initialize_online_training = _not_available
    get_training_coordinator = _not_available
    add_training_feedback = _not_available
    add_user_correction = _not_available
    get_online_training_status = _not_available
    SystemWideTrainingManager = _not_available
    get_system_training_manager = _not_available
    collect_prediction = _not_available
    submit_correction = _not_available
    get_training_dashboard = _not_available
    force_update = _not_available

# Convenience functions
__all__ = [
    # Core coordinator
    "OnTheFlyTrainingCoordinator",
    "TrainingExample",
    "ModelPerformance",
    "initialize_online_training",
    "get_training_coordinator",
    "add_training_feedback",
    "add_user_correction",
    "get_online_training_status",
    # System manager
    "SystemWideTrainingManager",
    "get_system_training_manager",
    "collect_prediction",
    "submit_correction",
    "get_training_dashboard",
    "force_update",
]
