# JustNews Unified Configuration Facade
# Phase 2B: Configuration Management Refactoring

"""
Compatibility facade for the configuration refactor.

This module aggregates the public surface area of the refactored
configuration system so that existing imports (``config.refactor``)
continue to function.  It simply re-exports the canonical objects from
the new module layout:

- ``config.schemas`` for Pydantic models and helpers
- ``config.core`` for the configuration manager
- ``config.environments`` for environment profiles
- ``config.validation`` for validation utilities
- ``config.legacy`` for migration tooling

Importing from here is equivalent to importing directly from the
individual modules, but preserves backwards compatibility with code and
tests that still reference ``config.refactor``.
"""

from ..core import (
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
from ..environments import (
    EnvironmentProfile,
    EnvironmentProfileManager,
    get_profile_manager,
)
from ..legacy import (
    LegacyConfigFile,
    LegacyConfigurationMigrator,
    MigrationPlan,
    create_legacy_compatibility_layer,
    discover_and_migrate_configs,
)
from ..schemas import (
    AgentsConfig,
    CrawlingConfig,
    DatabaseConfig,
    DataMinimizationConfig,
    Environment,
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
from ..validation import (
    ConfigurationMigrationValidator,
    ConfigurationTester,
    ConfigurationValidator,
    ValidationResult,
    benchmark_configuration,
    simulate_system_startup,
    validate_configuration_file,
)

__all__ = [
    # Schema exports
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
    "load_config_from_file",
    "save_config_to_file",
    "create_default_config",
    # Core manager exports
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
    # Environment profile exports
    "EnvironmentProfile",
    "EnvironmentProfileManager",
    "get_profile_manager",
    # Validation exports
    "ValidationResult",
    "ConfigurationValidator",
    "ConfigurationTester",
    "ConfigurationMigrationValidator",
    "validate_configuration_file",
    "simulate_system_startup",
    "benchmark_configuration",
    # Legacy migration exports
    "LegacyConfigFile",
    "MigrationPlan",
    "LegacyConfigurationMigrator",
    "discover_and_migrate_configs",
    "create_legacy_compatibility_layer",
]
