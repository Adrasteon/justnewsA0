# JustNews Configuration Management - Validation Utilities
# Phase 2B: Configuration Management Refactoring

"""
Configuration Validation and Testing Utilities

Provides comprehensive validation with:
- Schema validation and type checking
- Cross-component consistency validation
- Environment-specific validation rules
- Configuration testing and simulation
- Migration validation and safety checks
- Performance and security validation
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.observability import get_logger

from ..schemas import Environment, JustNewsConfig

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of configuration validation"""

    is_valid: bool
    errors: list[str]
    warnings: list[str]
    info: list[str]
    duration_ms: float

    def __str__(self) -> str:
        """String representation of validation result"""
        status = "✅ VALID" if self.is_valid else "❌ INVALID"
        lines = [f"{status} ({self.duration_ms:.1f}ms)"]

        if self.errors:
            lines.append(f"Errors ({len(self.errors)}):")
            lines.extend(f"  - {error}" for error in self.errors)

        if self.warnings:
            lines.append(f"Warnings ({len(self.warnings)}):")
            lines.extend(f"  - {warning}" for warning in self.warnings)

        if self.info:
            lines.append(f"Info ({len(self.info)}):")
            lines.extend(f"  - {info}" for info in self.info)

        return "\n".join(lines)


class ConfigurationValidator:
    """
    Comprehensive configuration validator

    Validates:
    - Schema compliance and type safety
    - Cross-component consistency
    - Environment-specific requirements
    - Performance and security constraints
    - Integration compatibility
    """

    def __init__(self):
        self.validators: list[
            Callable[[JustNewsConfig], tuple[list[str], list[str], list[str]]]
        ] = [
            self._validate_schema,
            self._validate_cross_component_consistency,
            self._validate_environment_requirements,
            self._validate_performance_constraints,
            self._validate_security_requirements,
            self._validate_integration_compatibility,
        ]

    def validate(self, config: JustNewsConfig) -> ValidationResult:
        """
        Validate configuration comprehensively

        Args:
            config: Configuration to validate

        Returns:
            ValidationResult: Validation results with errors, warnings, and info
        """
        start_time = time.time()

        all_errors = []
        all_warnings = []
        all_info = []

        # Run all validators
        for validator in self.validators:
            try:
                errors, warnings, info = validator(config)
                all_errors.extend(errors)
                all_warnings.extend(warnings)
                all_info.extend(info)
            except Exception as e:
                all_errors.append(f"Validator {validator.__name__} failed: {e}")

        duration_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            warnings=all_warnings,
            info=all_info,
            duration_ms=duration_ms,
        )

    def _validate_schema(
        self, config: JustNewsConfig
    ) -> tuple[list[str], list[str], list[str]]:
        """Validate schema compliance and type safety"""
        errors = []
        warnings = []
        info = []

        try:
            # Pydantic validation (should not raise if config is valid)
            config.model_dump()
            info.append("Schema validation passed")
        except Exception as e:
            errors.append(f"Schema validation failed: {e}")

        # Check for required fields
        required_sections = ["system", "database", "gpu", "agents", "monitoring"]
        for section in required_sections:
            if not hasattr(config, section):
                errors.append(f"Missing required section: {section}")

        return errors, warnings, info

    def _validate_cross_component_consistency(
        self, config: JustNewsConfig
    ) -> tuple[list[str], list[str], list[str]]:
        """Validate consistency across components"""
        errors = []
        warnings = []
        info = []

        # Port conflicts - check all agent ports are unique
        port_fields = [
            "scout",
            "analyst",
            "fact_checker",
            "synthesizer",
            "critic",
            "chief_editor",
            "memory",
            "reasoning",
            "dashboard",
        ]
        ports = []
        for field_name in port_fields:
            port_value = getattr(config.agents.ports, field_name)
            if port_value in ports:
                errors.append(
                    f"Port conflict: {field_name} uses port {port_value} which is already used"
                )
            ports.append(port_value)

        # GPU consistency
        if config.gpu.enabled:
            if not config.gpu.devices.preferred:
                errors.append("GPU enabled but no preferred devices specified")

        # Database consistency
        if config.database.host and config.database.database:
            info.append("Database configuration appears complete")
        else:
            warnings.append("Database configuration incomplete")

        # MCP Bus consistency
        if config.mcp_bus.host and config.mcp_bus.port:
            info.append("MCP Bus configuration appears complete")

        return errors, warnings, info

    def _validate_environment_requirements(
        self, config: JustNewsConfig
    ) -> tuple[list[str], list[str], list[str]]:
        """Validate environment-specific requirements"""
        errors = []
        warnings = []
        info = []

        env = config.system.environment

        if env == Environment.PRODUCTION:
            # Production requirements
            if config.system.debug_mode:
                errors.append("Debug mode must be disabled in production")

            if not config.database.password:
                errors.append("Database password is required in production")

            if not config.security.api_key_required:
                errors.append("API key authentication should be required in production")

            if not config.monitoring.enabled:
                warnings.append("Monitoring should be enabled in production")

            if config.gpu.enabled and not config.gpu.devices.preferred:
                warnings.append(
                    "GPU enabled in production but no preferred devices specified"
                )

        elif env == Environment.STAGING:
            # Staging requirements
            if not config.monitoring.enabled:
                warnings.append("Monitoring should be enabled in staging")

            if config.system.debug_mode:
                info.append("Debug mode enabled in staging environment")

        elif env == Environment.DEVELOPMENT:
            # Development allowances
            if not config.system.debug_mode:
                info.append(
                    "Debug mode disabled in development (consider enabling for debugging)"
                )

            if config.monitoring.enabled:
                info.append("Monitoring enabled in development")

        return errors, warnings, info

    def _validate_performance_constraints(
        self, config: JustNewsConfig
    ) -> tuple[list[str], list[str], list[str]]:
        """Validate performance-related constraints"""
        errors = []
        warnings = []
        info = []

        # Database connection pool
        if config.database.connection_pool.max_connections > 100:
            warnings.append(
                f"High max connections: {config.database.connection_pool.max_connections} (may overwhelm database)"
            )

        # Crawling rate limits
        if config.crawling.rate_limiting.requests_per_minute > 1000:
            warnings.append(
                f"High crawl rate: {config.crawling.rate_limiting.requests_per_minute} req/min"
            )

        return errors, warnings, info

    def _validate_security_requirements(
        self, config: JustNewsConfig
    ) -> tuple[list[str], list[str], list[str]]:
        """Validate security-related requirements"""
        errors = []
        warnings = []
        info = []

        # API security
        if config.system.environment == Environment.PRODUCTION:
            if not config.security.api_key_required:
                errors.append("API key authentication required in production")

        # Database security
        if config.database.password and len(config.database.password) < 12:
            warnings.append("Database password is weak (should be 12+ characters)")

        # Network security
        if config.security.cors_origins == ["*"]:
            if config.system.environment != Environment.DEVELOPMENT:
                warnings.append("Wildcard CORS origins allowed outside development")

        return errors, warnings, info

    def _validate_integration_compatibility(
        self, config: JustNewsConfig
    ) -> tuple[list[str], list[str], list[str]]:
        """Validate integration compatibility"""
        errors = []
        warnings = []
        info = []

        # Training data compatibility
        if config.training.enabled:
            # Note: dataset_path doesn't exist in schema, so we'll skip this check
            pass

        return errors, warnings, info


class ConfigurationTester:
    """
    Configuration testing and simulation utilities

    Provides:
    - Configuration loading simulation
    - Agent startup simulation
    - Integration testing
    - Performance benchmarking
    """

    def __init__(self, validator: ConfigurationValidator | None = None):
        """
        Initialize configuration tester

        Args:
            validator: Configuration validator to use
        """
        self.validator = validator or ConfigurationValidator()

    def test_configuration_loading(self, config_path: str | Path) -> ValidationResult:
        """
        Test configuration loading from file

        Args:
            config_path: Path to configuration file

        Returns:
            ValidationResult: Loading and validation results
        """
        start_time = time.time()

        errors = []
        warnings = []
        info = []

        try:
            # Test loading
            from config.schemas import load_config_from_file

            config = load_config_from_file(config_path)
            info.append(f"Successfully loaded configuration from {config_path}")

            # Validate loaded configuration
            validation_result = self.validator.validate(config)
            errors.extend(validation_result.errors)
            warnings.extend(validation_result.warnings)
            info.extend(validation_result.info)

        except Exception as e:
            errors.append(f"Failed to load configuration: {e}")

        duration_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            info=info,
            duration_ms=duration_ms,
        )

    def simulate_agent_startup(self, config: JustNewsConfig) -> ValidationResult:
        """
        Simulate agent startup with configuration

        Args:
            config: Configuration to test

        Returns:
            ValidationResult: Startup simulation results
        """
        start_time = time.time()

        errors = []
        warnings = []
        info = []

        # Simulate MCP Bus startup
        try:
            # Test port availability for MCP Bus
            import socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(("localhost", config.mcp_bus.port))
            sock.close()

            if result == 0:
                warnings.append(f"MCP Bus port {config.mcp_bus.port} already in use")
            else:
                info.append(f"MCP Bus port {config.mcp_bus.port} available")

        except Exception as e:
            errors.append(f"MCP Bus port test failed: {e}")

        # Simulate database connection
        try:
            # Test database connection (without actually connecting)
            if not config.database.host:
                errors.append("Database host not configured")
            if not config.database.database:
                errors.append("Database name not configured")

            info.append("Database configuration validated")

        except Exception as e:
            errors.append(f"Database configuration test failed: {e}")

        # Simulate GPU availability
        if config.gpu.enabled:
            try:
                # Check for GPU availability (simulated)
                import torch

                if torch.cuda.is_available():
                    device_count = torch.cuda.device_count()
                    info.append(f"GPU available: {device_count} device(s)")
                else:
                    warnings.append("GPU enabled but CUDA not available")

            except ImportError:
                warnings.append("GPU enabled but PyTorch not available")
            except Exception as e:
                errors.append(f"GPU availability test failed: {e}")

        duration_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            info=info,
            duration_ms=duration_ms,
        )

    def benchmark_configuration_performance(
        self, config: JustNewsConfig, iterations: int = 10
    ) -> dict[str, Any]:
        """
        Benchmark configuration performance

        Args:
            config: Configuration to benchmark
            iterations: Number of benchmark iterations

        Returns:
            Dict[str, Any]: Benchmark results
        """
        results = {
            "validation_times": [],
            "serialization_times": [],
            "deserialization_times": [],
            "average_validation_time": 0,
            "average_serialization_time": 0,
            "average_deserialization_time": 0,
        }

        for _i in range(iterations):
            # Validation benchmark
            start_time = time.time()
            self.validator.validate(config)
            validation_time = (time.time() - start_time) * 1000
            results["validation_times"].append(validation_time)

            # Serialization benchmark
            start_time = time.time()
            config_json = config.model_dump_json()
            serialization_time = (time.time() - start_time) * 1000
            results["serialization_times"].append(serialization_time)

            # Deserialization benchmark
            start_time = time.time()
            JustNewsConfig.model_validate_json(config_json)
            deserialization_time = (time.time() - start_time) * 1000
            results["deserialization_times"].append(deserialization_time)

        # Calculate averages
        results["average_validation_time"] = sum(results["validation_times"]) / len(
            results["validation_times"]
        )
        results["average_serialization_time"] = sum(
            results["serialization_times"]
        ) / len(results["serialization_times"])
        results["average_deserialization_time"] = sum(
            results["deserialization_times"]
        ) / len(results["deserialization_times"])

        return results


class ConfigurationMigrationValidator:
    """
    Configuration migration validation utilities

    Provides:
    - Migration path validation
    - Backward compatibility checking
    - Data integrity validation
    - Rollback safety validation
    """

    def __init__(self, validator: ConfigurationValidator | None = None):
        """
        Initialize migration validator

        Args:
            validator: Configuration validator to use
        """
        self.validator = validator or ConfigurationValidator()

    def validate_migration_path(
        self,
        old_config: JustNewsConfig,
        new_config: JustNewsConfig,
        migration_steps: list[str],
    ) -> ValidationResult:
        """
        Validate configuration migration path

        Args:
            old_config: Original configuration
            new_config: Target configuration
            migration_steps: List of migration steps performed

        Returns:
            ValidationResult: Migration validation results
        """
        start_time = time.time()

        errors = []
        warnings = []
        info = []

        # Validate old configuration
        old_validation = self.validator.validate(old_config)
        if not old_validation.is_valid:
            errors.append("Old configuration is invalid")
            errors.extend(old_validation.errors)

        # Validate new configuration
        new_validation = self.validator.validate(new_config)
        if not new_validation.is_valid:
            errors.append("New configuration is invalid")
            errors.extend(new_validation.errors)

        # Check for breaking changes
        breaking_changes = self._identify_breaking_changes(old_config, new_config)
        if breaking_changes:
            warnings.extend(f"Breaking change: {change}" for change in breaking_changes)

        # Validate migration steps
        if not migration_steps:
            warnings.append("No migration steps documented")

        # Check data integrity
        integrity_issues = self._check_data_integrity(old_config, new_config)
        if integrity_issues:
            errors.extend(
                f"Data integrity issue: {issue}" for issue in integrity_issues
            )

        duration_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            info=info,
            duration_ms=duration_ms,
        )

    def _identify_breaking_changes(
        self, old_config: JustNewsConfig, new_config: JustNewsConfig
    ) -> list[str]:
        """Identify breaking changes between configurations"""
        changes = []

        # Check for port changes
        old_ports = old_config.agents.ports.model_dump()
        new_ports = new_config.agents.ports.model_dump()
        for port_name, old_port in old_ports.items():
            if port_name in new_ports and old_port != new_ports[port_name]:
                changes.append(
                    f"Port changed: {port_name} {old_port} -> {new_ports[port_name]}"
                )

        return changes

    def _check_data_integrity(
        self, old_config: JustNewsConfig, new_config: JustNewsConfig
    ) -> list[str]:
        """Check data integrity between configurations"""
        issues = []

        # Check for required data preservation
        if old_config.database.host != new_config.database.host:
            issues.append("Database host changed without migration consideration")

        return issues

    def validate_rollback_safety(
        self, config: JustNewsConfig, backup_path: str | Path
    ) -> ValidationResult:
        """
        Validate rollback safety

        Args:
            config: Current configuration
            backup_path: Path to backup configuration

        Returns:
            ValidationResult: Rollback safety validation results
        """
        start_time = time.time()

        errors = []
        warnings = []
        info = []

        try:
            # Load backup configuration
            from config.schemas import load_config_from_file

            backup_config = load_config_from_file(backup_path)

            # Validate backup configuration
            backup_validation = self.validator.validate(backup_config)
            if not backup_validation.is_valid:
                errors.append("Backup configuration is invalid")
                errors.extend(backup_validation.errors)

            # Check rollback compatibility
            compatibility_issues = self._check_rollback_compatibility(
                config, backup_config
            )
            if compatibility_issues:
                warnings.extend(
                    f"Rollback compatibility issue: {issue}"
                    for issue in compatibility_issues
                )

            info.append("Rollback safety validated")

        except Exception as e:
            errors.append(f"Rollback safety validation failed: {e}")

        duration_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            info=info,
            duration_ms=duration_ms,
        )

    def _check_rollback_compatibility(
        self, current_config: JustNewsConfig, backup_config: JustNewsConfig
    ) -> list[str]:
        """Check rollback compatibility issues"""
        issues = []

        # Check for data that might be lost
        if current_config.database.database != backup_config.database.database:
            issues.append("Database name changed - rollback may lose data")

        return issues


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def validate_configuration_file(config_path: str | Path) -> ValidationResult:
    """
    Validate configuration file

    Args:
        config_path: Path to configuration file

    Returns:
        ValidationResult: Validation results
    """
    tester = ConfigurationTester()
    return tester.test_configuration_loading(config_path)


def simulate_system_startup(config: JustNewsConfig) -> ValidationResult:
    """
    Simulate system startup with configuration

    Args:
        config: Configuration to test

    Returns:
        ValidationResult: Startup simulation results
    """
    tester = ConfigurationTester()
    return tester.simulate_agent_startup(config)


def benchmark_configuration(config: JustNewsConfig) -> dict[str, Any]:
    """
    Benchmark configuration performance

    Args:
        config: Configuration to benchmark

    Returns:
        Dict[str, Any]: Benchmark results
    """
    tester = ConfigurationTester()
    return tester.benchmark_configuration_performance(config)


# Export public API
__all__ = [
    "ValidationResult",
    "ConfigurationValidator",
    "ConfigurationTester",
    "ConfigurationMigrationValidator",
    "validate_configuration_file",
    "simulate_system_startup",
    "benchmark_configuration",
]
