# JustNews Configuration Management - Core Manager
# Phase 2B: Configuration Management Refactoring

"""
Core Configuration Manager

Provides centralized configuration management with:
- Type-safe configuration loading and validation
- Environment abstraction and overrides
- Runtime configuration updates
- Configuration auditing and rollback
- Comprehensive error handling and logging
"""

import copy
import hashlib
import json
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from common.env_loader import load_global_env
from common.observability import get_logger

from ..schemas import (
    Environment,
    JustNewsConfig,
    create_default_config,
    load_config_from_file,
    save_config_to_file,
)

logger = get_logger(__name__)


class ConfigurationError(Exception):
    """Configuration-related errors"""

    pass


class ConfigurationValidationError(ConfigurationError):
    """Configuration validation errors"""

    pass


class ConfigurationNotFoundError(ConfigurationError):
    """Configuration file not found"""

    pass


class ConfigurationManager:
    """
    Centralized configuration manager for JustNews

    Features:
    - Type-safe configuration with Pydantic validation
    - Environment abstraction (dev/staging/production)
    - Runtime configuration updates
    - Configuration auditing and rollback
    - Comprehensive error handling
    """

    def __init__(
        self,
        config_file: str | Path | None = None,
        environment: Environment | None = None,
        auto_reload: bool = False,
    ):
        """
        Initialize configuration manager

        Args:
            config_file: Path to configuration file (auto-discovered if None)
            environment: Override environment (detected from file if None)
            auto_reload: Enable automatic config reloading on file changes
        """
        self.config_file = (
            Path(config_file) if config_file else self._find_config_file()
        )
        self.environment = environment
        self.auto_reload = auto_reload

        # Configuration state
        self._config: JustNewsConfig | None = None
        self._config_hash: str | None = None
        self._last_load_time: datetime | None = None

        # Audit trail
        self._audit_log: list[dict[str, Any]] = []
        self._change_callbacks: list[Callable[[str, Any, Any], None]] = []

        # Load initial configuration
        self.reload()

        logger.info(
            f"✅ Configuration manager initialized with file: {self.config_file}"
        )

    def _find_config_file(self) -> Path:
        """Find configuration file using standard search paths"""
        search_paths = [
            # Current working directory
            Path.cwd() / "config.json",
            Path.cwd() / "config" / "system_config.json",
            # User home directory
            Path.home() / ".justnews" / "config.json",
            # System-wide locations
            Path("/etc/justnews/config.json"),
            # Development fallback
            Path(__file__).parent.parent.parent / "config" / "system_config.json",
        ]

        for path in search_paths:
            if path.exists() and path.is_file():
                logger.debug(f"Found configuration file: {path}")
                return path

        # No configuration file found, create a default one so callers can continue
        default_path = Path.cwd() / "config" / "system_config.json"
        default_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            default_config = create_default_config()
            save_config_to_file(default_config, default_path)
            logger.info(
                "✅ Created default configuration at %s as no existing configuration was found",
                default_path,
            )
            return default_path
        except Exception as exc:
            raise ConfigurationNotFoundError(
                f"No configuration file found or could be created. Searched: {[str(p) for p in search_paths]}"
            ) from exc

    def reload(self) -> JustNewsConfig:
        """
        Reload configuration from file

        Returns:
            JustNewsConfig: Loaded and validated configuration

        Raises:
            ConfigurationError: If loading or validation fails
        """
        try:
            # Ensure environment variables from global.env are available before loading configuration
            load_global_env(logger=logger)

            # Load configuration
            config = load_config_from_file(self.config_file)

            # Apply environment detection if not specified
            if self.environment is None:
                env_value = config.system.environment
                # Convert string to enum if necessary (due to use_enum_values=True)
                if isinstance(env_value, str):
                    self.environment = Environment(env_value)
                else:
                    self.environment = env_value

            # Apply environment overrides
            config = self._apply_environment_overrides(config)

            # Validate configuration
            self._validate_configuration(config)

            # Update state
            old_config = self._config
            self._config = config
            self._config_hash = self._calculate_hash(config)
            self._last_load_time = datetime.now()

            # Log configuration change
            if old_config is not None:
                self._log_change(
                    "reload", "configuration reloaded from file", old_config, config
                )

            logger.info(
                f"✅ Configuration reloaded successfully (environment: {self.environment.value})"
            )
            return config

        except Exception as e:
            error_msg = f"Failed to reload configuration: {e}"
            logger.error(error_msg)
            raise ConfigurationError(error_msg) from e

    def _apply_environment_overrides(self, config: JustNewsConfig) -> JustNewsConfig:
        """Apply environment-specific overrides"""
        overrides = self._get_environment_overrides()

        if not overrides:
            return config

        # Deep copy to avoid modifying original
        config_dict = config.model_dump()
        self._deep_merge(config_dict, overrides)

        try:
            return JustNewsConfig(**config_dict)
        except Exception as e:
            # Preserve original exception context for debugging
            raise ConfigurationValidationError(
                f"Environment overrides validation failed: {e}"
            ) from e

    def _get_environment_overrides(self) -> dict[str, Any]:
        """Get environment-specific configuration overrides"""
        overrides = {}

        # Environment variables
        env_overrides = self._get_environment_variable_overrides()
        if env_overrides:
            overrides.update(env_overrides)

        # Environment-specific files
        env_file_overrides = self._get_environment_file_overrides()
        if env_file_overrides:
            overrides.update(env_file_overrides)

        return overrides

    def _get_environment_variable_overrides(self) -> dict[str, Any]:
        """Get configuration overrides from environment variables"""
        overrides = {}

        # System overrides
        if os.environ.get("JUSTNEWS_LOG_LEVEL"):
            overrides.setdefault("system", {})["log_level"] = os.environ[
                "JUSTNEWS_LOG_LEVEL"
            ]
        if os.environ.get("JUSTNEWS_DEBUG_MODE"):
            overrides.setdefault("system", {})["debug_mode"] = (
                os.environ["JUSTNEWS_DEBUG_MODE"].lower() == "true"
            )

        # Database overrides - use MariaDB environment variable names
        if os.environ.get("MARIADB_HOST"):
            overrides.setdefault("database", {})["host"] = os.environ["MARIADB_HOST"]

        if os.environ.get("MARIADB_PORT"):
            overrides.setdefault("database", {})["port"] = int(
                os.environ["MARIADB_PORT"]
            )

        if os.environ.get("MARIADB_DB"):
            overrides.setdefault("database", {})["database"] = os.environ["MARIADB_DB"]

        if os.environ.get("MARIADB_USER"):
            overrides.setdefault("database", {})["user"] = os.environ["MARIADB_USER"]

        if os.environ.get("MARIADB_PASSWORD"):
            overrides.setdefault("database", {})["password"] = os.environ[
                "MARIADB_PASSWORD"
            ]

        # GPU overrides
        if os.environ.get("JUSTNEWS_GPU_ENABLED"):
            overrides.setdefault("gpu", {})["enabled"] = (
                os.environ["JUSTNEWS_GPU_ENABLED"].lower() == "true"
            )

        # Crawling overrides
        if os.environ.get("JUSTNEWS_CRAWL_REQUESTS_PER_MINUTE"):
            overrides.setdefault("crawling", {}).setdefault("rate_limiting", {})[
                "requests_per_minute"
            ] = int(os.environ["JUSTNEWS_CRAWL_REQUESTS_PER_MINUTE"])

        return overrides

    def _get_environment_file_overrides(self) -> dict[str, Any]:
        """Get configuration overrides from environment-specific files"""
        if not self.environment:
            return {}

        # Look for environment-specific override files
        override_files = [
            self.config_file.parent / f"config.{self.environment.value}.json",
            self.config_file.parent / f"{self.environment.value}.json",
            Path.home() / ".justnews" / f"config.{self.environment.value}.json",
        ]

        for override_file in override_files:
            if override_file.exists():
                try:
                    with open(override_file) as f:
                        overrides = json.load(f)
                    logger.info(f"Loaded environment overrides from: {override_file}")
                    return overrides
                except Exception as e:
                    logger.warning(
                        f"Failed to load environment overrides from {override_file}: {e}"
                    )

        return {}

    def _validate_configuration(self, config: JustNewsConfig):
        """Validate configuration for consistency and requirements"""
        errors = []

        # Environment-specific validations
        if config.system.environment == Environment.PRODUCTION:
            if not config.database.password:
                errors.append("Database password is required in production")
            if config.system.debug_mode:
                errors.append("Debug mode must be disabled in production")
            if not config.security.api_key_required:
                errors.append("API key authentication should be required in production")

        # Cross-component validations
        if config.gpu.enabled and not config.gpu.devices.preferred:
            errors.append("GPU enabled but no preferred devices specified")

        # Agent port conflicts
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
        ports = [getattr(config.agents.ports, field) for field in port_fields]
        if len(ports) != len(set(ports)):
            errors.append("Agent ports must be unique")

        if errors:
            raise ConfigurationValidationError(
                f"Configuration validation failed: {'; '.join(errors)}"
            )

    def _calculate_hash(self, config: JustNewsConfig) -> str:
        """Calculate configuration hash for change detection"""
        config_str = json.dumps(config.model_dump(), sort_keys=True, default=str)
        return hashlib.sha256(config_str.encode()).hexdigest()

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]):
        """Deep merge override dictionary into base dictionary"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _log_change(
        self,
        operation: str,
        description: str,
        old_value: Any = None,
        new_value: Any = None,
    ):
        """Log configuration change for audit trail"""
        change_entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "description": description,
            "old_value": old_value.model_dump()
            if hasattr(old_value, "model_dump")
            else old_value,
            "new_value": new_value.model_dump()
            if hasattr(new_value, "model_dump")
            else new_value,
        }

        self._audit_log.append(change_entry)

        # Notify change callbacks
        for callback in self._change_callbacks:
            try:
                callback(operation, old_value, new_value)
            except Exception as e:
                logger.warning(f"Configuration change callback failed: {e}")

    # Public API methods

    @property
    def config(self) -> JustNewsConfig:
        """Get current configuration"""
        if self._config is None:
            raise ConfigurationError("Configuration not loaded")
        return self._config

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation path"""
        try:
            return self.config.get_nested_value(key_path)
        except KeyError:
            return default

    def set(self, key_path: str, value: Any, persist: bool = False):
        """
        Set configuration value by dot-notation path

        Args:
            key_path: Dot-notation path (e.g., 'database.host')
            value: New value
            persist: Whether to persist to file
        """
        old_value = self.get(key_path)

        # Update configuration
        new_config = copy.deepcopy(self.config)
        new_config.set_nested_value(key_path, value)

        # Validate new configuration
        self._validate_configuration(new_config)

        # Update state
        self._config = new_config
        self._log_change("set", f"Updated {key_path}", old_value, value)

        # Persist if requested
        if persist:
            self.save()

        logger.info(f"✅ Configuration updated: {key_path} = {value}")

    def save(self, file_path: str | Path | None = None):
        """Save current configuration to file"""
        save_path = Path(file_path) if file_path else self.config_file

        try:
            from ..schemas import save_config_to_file

            save_config_to_file(self.config, save_path)
            self._log_change("save", f"Configuration saved to {save_path}")
            logger.info(f"✅ Configuration saved to {save_path}")
        except Exception as e:
            error_msg = f"Failed to save configuration: {e}"
            logger.error(error_msg)
            # Chain the original exception for clarity
            raise ConfigurationError(error_msg) from e

    def reset_to_defaults(self):
        """Reset configuration to defaults"""
        old_config = self.config
        self._config = create_default_config()
        self._log_change(
            "reset", "Configuration reset to defaults", old_config, self._config
        )
        logger.info("✅ Configuration reset to defaults")

    def add_change_callback(self, callback: Callable[[str, Any, Any], None]):
        """Add callback for configuration changes"""
        self._change_callbacks.append(callback)

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Get configuration change audit log"""
        return self._audit_log.copy()

    def get_config_info(self) -> dict[str, Any]:
        """Get configuration metadata"""
        return {
            "config_file": str(self.config_file),
            "environment": self.environment.value if self.environment else None,
            "last_load_time": self._last_load_time.isoformat()
            if self._last_load_time
            else None,
            "config_hash": self._config_hash,
            "auto_reload": self.auto_reload,
        }

    def __getitem__(self, key: str) -> Any:
        """Allow dictionary-style access"""
        return getattr(self.config, key)

    def __contains__(self, key: str) -> bool:
        """Check if configuration section exists"""
        return hasattr(self.config, key)


# ============================================================================
# GLOBAL CONFIGURATION INSTANCE
# ============================================================================

_config_manager: ConfigurationManager | None = None


def get_config_manager() -> ConfigurationManager:
    """Get global configuration manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigurationManager()
    return _config_manager


def get_config() -> JustNewsConfig:
    """Get current configuration"""
    return get_config_manager().config


# Convenience functions for common access patterns
def get_system_config():
    """Get system configuration section"""
    return get_config().system


def get_database_config():
    """Get database configuration section"""
    return get_config().database


def get_gpu_config():
    """Get GPU configuration section"""
    return get_config().gpu


def get_crawling_config():
    """Get crawling configuration section"""
    return get_config().crawling


def is_production():
    """Check if running in production environment"""
    return get_config().system.environment == Environment.PRODUCTION


def is_debug_mode():
    """Check if debug mode is enabled"""
    return get_config().system.debug_mode


# Export public API
__all__ = [
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
]
