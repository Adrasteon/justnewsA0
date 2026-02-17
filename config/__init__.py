# JustNews Unified Configuration System
# Phase 2B: Configuration Management Refactoring

"""
Unified Configuration System for JustNews

Provides a complete configuration management solution with:
- Type-safe configuration models with Pydantic validation
- Environment abstraction and inheritance
- Centralized configuration management
- Comprehensive validation and testing
- Legacy migration support
- Runtime configuration updates
"""

from typing import Any

from .core import (
    ConfigurationError,
    ConfigurationManager,
    ConfigurationNotFoundError,
    ConfigurationValidationError,
    get_config,
    get_config_manager,
    get_crawling_config,
    get_database_config,
    get_gpu_config,
    get_system_config,
    is_debug_mode,
    is_production,
)
from .environments import (
    Environment,
    EnvironmentProfile,
    EnvironmentProfileManager,
    get_profile_manager,
)
from .legacy import (
    LegacyConfigFile,
    LegacyConfigurationMigrator,
    MigrationPlan,
    create_legacy_compatibility_layer,
    discover_and_migrate_configs,
)
from .schemas import (
    AgentsConfig,
    CrawlingConfig,
    DatabaseConfig,
    DataMinimizationConfig,
    ExternalServicesConfig,
    GPUConfig,
    JustNewsConfig,
    MCPBusConfig,
    MonitoringConfig,
    PerformanceConfig,
    SecurityConfig,
    SystemConfig,
    TrainingConfig,
    create_default_config,
    load_config_from_file,
    save_config_to_file,
)

# validation imports are declared explicitly below
# Explicit imports used in this module (avoid star-import ambiguity for linting)
from .validation import (
    ConfigurationMigrationValidator,
    ConfigurationTester,
    ConfigurationValidator,
    ValidationResult,
    benchmark_configuration,
    simulate_system_startup,
    validate_configuration_file,
)

# Re-export key classes and functions for convenience
__all__ = [
    # Schema / config exports
    "JustNewsConfig",
    "Environment",
    "SystemConfig",
    "MCPBusConfig",
    "DatabaseConfig",
    "CrawlingConfig",
    "GPUConfig",
    "AgentsConfig",
    "TrainingConfig",
    "SecurityConfig",
    "MonitoringConfig",
    "DataMinimizationConfig",
    "PerformanceConfig",
    "ExternalServicesConfig",
    "create_default_config",
    # loader helpers
    "load_config_from_file",
    "save_config_to_file",
    # core manager / helpers
    "ConfigurationManager",
    "ConfigurationError",
    "ConfigurationValidationError",
    "ConfigurationNotFoundError",
    "get_config_manager",
    "get_config",
    "get_system_config",
    "get_database_config",
    "get_gpu_config",
    "get_crawling_config",
    "is_production",
    "is_debug_mode",
    # environments
    "EnvironmentProfile",
    "EnvironmentProfileManager",
    "get_profile_manager",
    # validation
    "ValidationResult",
    "ConfigurationValidator",
    "ConfigurationTester",
    "ConfigurationMigrationValidator",
    "validate_configuration_file",
    "simulate_system_startup",
    "benchmark_configuration",
    # legacy migration
    "LegacyConfigFile",
    "MigrationPlan",
    "LegacyConfigurationMigrator",
    "discover_and_migrate_configs",
    "create_legacy_compatibility_layer",
]

# ============================================================================
# QUICK START HELPERS
# ============================================================================


def quick_start_development() -> ConfigurationManager:
    """
    Quick start for development environment

    Returns:
        ConfigurationManager: Initialized configuration manager
    """
    manager = ConfigurationManager(environment=Environment.DEVELOPMENT)
    return manager


def quick_start_production() -> ConfigurationManager:
    """
    Quick start for production environment

    Returns:
        ConfigurationManager: Initialized configuration manager
    """
    manager = ConfigurationManager(environment=Environment.PRODUCTION)
    return manager


def validate_current_setup() -> ValidationResult:
    """
    Validate current configuration setup

    Returns:
        ValidationResult: Validation results
    """
    try:
        config = get_config()
        validator = ConfigurationValidator()
        return validator.validate(config)
    except Exception as e:
        return ValidationResult(
            is_valid=False,
            errors=[f"Setup validation failed: {e}"],
            warnings=[],
            info=[],
            duration_ms=0,
        )


# ============================================================================
# MIGRATION HELPERS
# ============================================================================


def migrate_from_legacy(
    dry_run: bool = True,
) -> tuple[MigrationPlan, ValidationResult | None]:
    """
    Migrate from legacy configuration files

    Args:
        dry_run: If True, only create migration plan without executing

    Returns:
        Tuple[MigrationPlan, Optional[ValidationResult]]: Migration plan and execution result
    """
    plan, result = discover_and_migrate_configs(
        target_environment=Environment.DEVELOPMENT, execute=not dry_run, backup=True
    )
    return plan, result


# ============================================================================
# VERSION INFORMATION
# ============================================================================

__version__ = "1.0.0"
__description__ = "Unified Configuration System for JustNews"
__author__ = "JustNews Team"


def get_system_info() -> dict[str, Any]:
    """Get system configuration information"""
    try:
        manager = get_config_manager()
        return {
            "version": __version__,
            "config_file": str(manager.config_file),
            "environment": manager.environment.value if manager.environment else None,
            "last_load_time": manager._last_load_time.isoformat()
            if manager._last_load_time
            else None,
            "config_hash": manager._config_hash,
        }
    except Exception as e:
        return {"error": f"Failed to get system info: {e}", "version": __version__}
