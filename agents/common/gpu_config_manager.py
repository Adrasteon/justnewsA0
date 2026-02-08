"""
Centralized GPU Configuration Management for JustNews
Provides unified configuration management for all GPU-related settings

Features:
- Centralized configuration files
- Environment-specific settings
- Dynamic configuration updates
- Configuration validation
- Backup and restore capabilities
"""

import json
import os
import socket
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from common.observability import get_logger

logger = get_logger(__name__)


class GPUConfigManager:
    """
    Centralized configuration manager for GPU settings

    Manages:
    - GPU allocation settings
    - Model configurations
    - Performance tuning parameters
    - Environment-specific overrides
    - Configuration validation and backup
    """

    def __init__(self, config_dir: str = "./config/gpu"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Configuration files
        self.main_config_file = self.config_dir / "gpu_config.json"
        self.env_config_file = self.config_dir / "environment_config.json"
        self.model_config_file = self.config_dir / "model_config.json"
        self.backup_dir = self.config_dir / "backups"

        # Configuration profiles
        self.profiles_config_file = self.config_dir / "config_profiles.json"
        self.active_profile = os.environ.get("GPU_CONFIG_PROFILE", "default")

        # Default configurations
        self._load_default_configs()

        # Load existing configurations
        self._load_configs()

    def _load_default_configs(self):
        """Load default configuration templates"""
        self.default_main_config = {
            "gpu_manager": {
                "max_memory_per_agent_gb": 8.0,
                "health_check_interval_seconds": 30.0,
                "allocation_timeout_seconds": 60.0,
                "memory_safety_margin_percent": 10,
                "enable_memory_cleanup": True,
                "enable_health_monitoring": True,
                "enable_performance_tracking": True,
            },
            "gpu_devices": {
                "preferred_devices": [0],
                "excluded_devices": [],
                "device_memory_limits": {},
                "device_temperature_limits": {
                    "warning_celsius": 75,
                    "critical_celsius": 85,
                    "shutdown_celsius": 95,
                },
            },
            "performance": {
                "batch_size_optimization": True,
                "memory_preallocation": False,
                "async_operations": True,
                "profiling_enabled": False,
                "metrics_collection_interval": 10.0,
            },
            "monitoring": {
                "alert_thresholds": {
                    "temperature_warning": 75,
                    "temperature_critical": 85,
                    "memory_usage_warning": 85,
                    "memory_usage_critical": 95,
                    "utilization_stuck_threshold": 95,
                    "power_draw_anomaly_watts": 300,
                },
                "alert_cooldown_minutes": 5,
                "enable_email_alerts": False,
                "email_recipients": [],
                "log_level": "INFO",
            },
        }

        self.default_env_config = {
            "development": {
                "gpu_manager": {
                    "max_memory_per_agent_gb": 4.0,
                    "health_check_interval_seconds": 15.0,
                },
                "performance": {
                    "profiling_enabled": True,
                    "metrics_collection_interval": 5.0,
                },
            },
            "staging": {
                "gpu_manager": {
                    "max_memory_per_agent_gb": 6.0,
                    "health_check_interval_seconds": 20.0,
                },
                "monitoring": {
                    "enable_email_alerts": True,
                    "email_recipients": ["admin@company.com"],
                },
            },
            "production": {
                "gpu_manager": {
                    "max_memory_per_agent_gb": 8.0,
                    "health_check_interval_seconds": 30.0,
                },
                "performance": {
                    "batch_size_optimization": True,
                    "memory_preallocation": True,
                },
                "monitoring": {
                    "enable_email_alerts": True,
                    "email_recipients": ["ops@company.com", "admin@company.com"],
                },
            },
        }

        self.default_model_config = {
            "model_defaults": {
                "dtype": "float16",
                "device_map": "auto",
                "load_in_8bit": False,
                "load_in_4bit": False,
                "trust_remote_code": True,
                "max_memory_usage_gb": 4.0,
            },
            "model_specific": {
                "gpt2-medium": {
                    "max_memory_usage_gb": 2.0,
                    "batch_size_recommendation": 8,
                    "use_flash_attention": False,
                },
                "distilgpt2": {
                    "max_memory_usage_gb": 1.0,
                    "batch_size_recommendation": 16,
                    "use_flash_attention": False,
                },
                "sentence-transformers/all-MiniLM-L6-v2": {
                    "max_memory_usage_gb": 0.5,
                    "batch_size_recommendation": 32,
                    "use_flash_attention": False,
                },
                "facebook/bart-large-mnli": {
                    "max_memory_usage_gb": 3.0,
                    "batch_size_recommendation": 4,
                    "use_flash_attention": False,
                },
            },
            "agent_model_assignments": {
                "synthesizer": ["gpt2-medium", "distilgpt2"],
                "fact_checker": ["gpt2-medium", "facebook/bart-large-mnli"],
                "analyst": ["sentence-transformers/all-MiniLM-L6-v2"],
                "scout": ["sentence-transformers/all-MiniLM-L6-v2"],
                "memory": ["sentence-transformers/all-MiniLM-L6-v2"],
                "newsreader": ["sentence-transformers/all-MiniLM-L6-v2"],
            },
        }

        self.default_profiles_config = {
            "default": {
                "description": "Standard configuration profile",
                "gpu_manager": {
                    "max_memory_per_agent_gb": 8.0,
                    "health_check_interval_seconds": 30.0,
                },
            },
            "high_performance": {
                "description": "Optimized for maximum performance",
                "gpu_manager": {
                    "max_memory_per_agent_gb": 12.0,
                    "health_check_interval_seconds": 15.0,
                },
                "performance": {
                    "batch_size_optimization": True,
                    "memory_preallocation": True,
                    "async_operations": True,
                    "profiling_enabled": True,
                },
            },
            "memory_conservative": {
                "description": "Conservative memory usage for limited GPU resources",
                "gpu_manager": {
                    "max_memory_per_agent_gb": 4.0,
                    "health_check_interval_seconds": 45.0,
                },
                "performance": {
                    "batch_size_optimization": True,
                    "memory_preallocation": False,
                    "async_operations": False,
                },
            },
            "debug": {
                "description": "Debug configuration with extensive logging",
                "gpu_manager": {
                    "max_memory_per_agent_gb": 6.0,
                    "health_check_interval_seconds": 10.0,
                },
                "performance": {
                    "profiling_enabled": True,
                    "metrics_collection_interval": 5.0,
                },
                "monitoring": {"log_level": "DEBUG"},
            },
        }

    def _load_configs(self):
        """Load existing configuration files"""
        self.main_config = self._load_config_file(
            self.main_config_file, self.default_main_config
        )
        self.env_config = self._load_config_file(
            self.env_config_file, self.default_env_config
        )
        self.model_config = self._load_config_file(
            self.model_config_file, self.default_model_config
        )
        self.profiles_config = self._load_config_file(
            self.profiles_config_file, self.default_profiles_config
        )

    def _load_config_file(
        self, file_path: Path, default_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Load a configuration file with fallback to defaults"""
        if file_path.exists():
            try:
                with open(file_path, encoding="utf-8") as f:
                    if file_path.suffix == ".json":
                        loaded_config = json.load(f)
                    elif file_path.suffix in [".yaml", ".yml"]:
                        loaded_config = yaml.safe_load(f)
                    else:
                        logger.warning(f"Unsupported config file format: {file_path}")
                        return default_config

                # Merge with defaults to ensure all keys exist
                return self._merge_configs(default_config, loaded_config)

            except Exception as e:
                logger.error(f"Error loading config file {file_path}: {e}")
                return default_config
        else:
            # Create default config file
            self._save_config_file(file_path, default_config)
            return default_config

    def _merge_configs(
        self, base: dict[str, Any], override: dict[str, Any]
    ) -> dict[str, Any]:
        """Recursively merge configuration dictionaries"""
        result = base.copy()

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value

        return result

    def _save_config_file(self, file_path: Path, config: dict[str, Any]):
        """Save configuration to file"""
        try:
            # Create backup if file exists
            if file_path.exists():
                self._create_backup(file_path)

            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                if file_path.suffix == ".json":
                    json.dump(config, f, indent=2, ensure_ascii=False)
                elif file_path.suffix in [".yaml", ".yml"]:
                    yaml.dump(config, f, default_flow_style=False)

            logger.info(f"Configuration saved to {file_path}")

        except Exception as e:
            logger.error(f"Error saving config file {file_path}: {e}")

    def _create_backup(self, file_path: Path):
        """Create a backup of the configuration file"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
            backup_path = self.backup_dir / backup_name

            import shutil

            shutil.copy2(file_path, backup_path)

            # Keep only last 10 backups
            backups = sorted(
                self.backup_dir.glob(f"{file_path.stem}_*{file_path.suffix}")
            )
            if len(backups) > 10:
                for old_backup in backups[:-10]:
                    old_backup.unlink()

            logger.debug(f"Backup created: {backup_path}")

        except Exception as e:
            logger.warning(f"Failed to create backup for {file_path}: {e}")

    def get_config(
        self, environment: str = None, profile: str = None
    ) -> dict[str, Any]:
        """Get the effective configuration for the current environment and profile"""
        # Start with main config
        config = self.main_config.copy()

        # Apply environment-specific overrides
        if environment:
            env_overrides = self.env_config.get(environment, {})
            config = self._merge_configs(config, env_overrides)

        # Apply current environment if detected
        current_env = self._detect_environment()
        if current_env and current_env != environment:
            env_overrides = self.env_config.get(current_env, {})
            config = self._merge_configs(config, env_overrides)

        # Apply profile overrides
        if profile:
            profile_overrides = self.profiles_config.get(profile, {})
            if (
                isinstance(profile_overrides, dict)
                and "description" in profile_overrides
            ):
                # Remove description from profile config before merging
                profile_config = {
                    k: v for k, v in profile_overrides.items() if k != "description"
                }
                config = self._merge_configs(config, profile_config)

        # Apply active profile if set
        if self.active_profile and self.active_profile != "default":
            active_profile_overrides = self.profiles_config.get(self.active_profile, {})
            if (
                isinstance(active_profile_overrides, dict)
                and "description" in active_profile_overrides
            ):
                profile_config = {
                    k: v
                    for k, v in active_profile_overrides.items()
                    if k != "description"
                }
                config = self._merge_configs(config, profile_config)

        return config

    def _detect_environment(self) -> str | None:
        """Detect the current environment with enhanced detection methods"""
        # Check environment variables (highest priority)
        env_var = os.environ.get("JUSTNEWS_ENV", os.environ.get("ENV", "")).lower()

        if env_var in ["dev", "development", "local"]:
            return "development"
        elif env_var in ["staging", "stage", "test"]:
            return "staging"
        elif env_var in ["prod", "production", "live"]:
            return "production"

        # Check hostname patterns
        import socket

        hostname = socket.gethostname().lower()

        if any(pattern in hostname for pattern in ["dev", "development", "local"]):
            return "development"
        elif any(pattern in hostname for pattern in ["staging", "stage", "test"]):
            return "staging"
        elif any(pattern in hostname for pattern in ["prod", "production", "live"]):
            return "production"

        # Check for environment-specific files
        # Note: Docker Compose and Kubernetes manifests are deprecated; prefer systemd units in `infrastructure/systemd`.
        if os.path.exists(".env.development") or os.path.exists(
            "infrastructure/systemd"
        ):
            return "development"
        elif os.path.exists(".env.staging"):
            return "staging"
        elif os.path.exists(".env.production"):
            return "production"

        # Check current working directory for environment hints
        cwd = os.getcwd().lower()
        if any(pattern in cwd for pattern in ["/dev/", "/development/", "/local/"]):
            return "development"
        elif any(pattern in cwd for pattern in ["/staging/", "/stage/", "/test/"]):
            return "staging"
        elif any(pattern in cwd for pattern in ["/prod/", "/production/", "/live/"]):
            return "production"

        return None

    def get_model_config(self, model_name: str = None) -> dict[str, Any]:
        """Get model-specific configuration"""
        if model_name and model_name in self.model_config["model_specific"]:
            # Merge model-specific config with defaults
            config = self.model_config["model_defaults"].copy()
            config.update(self.model_config["model_specific"][model_name])
            return config
        else:
            return self.model_config["model_defaults"].copy()

    def get_agent_models(self, agent_name: str) -> list[str]:
        """Get recommended models for an agent"""
        return self.model_config["agent_model_assignments"].get(agent_name, [])

    def update_config(self, updates: dict[str, Any], environment: str = None):
        """Update configuration with validation"""
        if not self._validate_config_updates(updates):
            raise ValueError("Invalid configuration updates")

        if environment:
            # Update environment-specific config
            if environment not in self.env_config:
                self.env_config[environment] = {}
            self.env_config[environment] = self._merge_configs(
                self.env_config[environment], updates
            )
            self._save_config_file(self.env_config_file, self.env_config)
        else:
            # Update main config
            self.main_config = self._merge_configs(self.main_config, updates)
            self._save_config_file(self.main_config_file, self.main_config)

        logger.info(f"Configuration updated for environment: {environment or 'main'}")

    def _validate_config_updates(self, updates: dict[str, Any]) -> bool:
        """Validate configuration updates"""
        try:
            # Basic validation rules
            if "gpu_manager" in updates:
                gpu_mgr = updates["gpu_manager"]
                if "max_memory_per_agent_gb" in gpu_mgr:
                    mem_limit = gpu_mgr["max_memory_per_agent_gb"]
                    if not isinstance(mem_limit, (int, float)) or mem_limit <= 0:
                        return False

                if "health_check_interval_seconds" in gpu_mgr:
                    interval = gpu_mgr["health_check_interval_seconds"]
                    if not isinstance(interval, (int, float)) or interval <= 0:
                        return False

            if "monitoring" in updates:
                monitoring = updates["monitoring"]
                if "alert_thresholds" in monitoring:
                    thresholds = monitoring["alert_thresholds"]
                    if "temperature_critical" in thresholds:
                        temp = thresholds["temperature_critical"]
                        if not isinstance(temp, (int, float)) or temp < 0 or temp > 150:
                            return False

            return True

        except Exception:
            return False

    def export_config(self, file_path: str, environment: str = None):
        """Export current configuration to file"""
        config = self.get_config(environment)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            logger.info(f"Configuration exported to {file_path}")

        except Exception as e:
            logger.error(f"Failed to export config: {e}")
            raise

    def import_config(self, file_path: str, environment: str = None):
        """Import configuration from file"""
        try:
            with open(file_path, encoding="utf-8") as f:
                imported_config = json.load(f)

            self.update_config(imported_config, environment)
            logger.info(f"Configuration imported from {file_path}")

        except Exception as e:
            logger.error(f"Failed to import config: {e}")
            raise

    def set_runtime_environment(self, environment: str):
        """Set the runtime environment override"""
        if environment not in ["development", "staging", "production"]:
            raise ValueError(
                f"Invalid environment: {environment}. Must be one of: development, staging, production"
            )

        os.environ["JUSTNEWS_ENV"] = environment
        logger.info(f"Runtime environment set to: {environment}")

        # Reload configurations to apply new environment
        self._load_configs()

    def get_environment_info(self) -> dict[str, Any]:
        """Get detailed information about the current environment"""
        current_env = self._detect_environment()
        runtime_env = os.environ.get("JUSTNEWS_ENV")

        return {
            "detected_environment": current_env,
            "runtime_environment": runtime_env,
            "effective_environment": runtime_env or current_env,
            "hostname": socket.gethostname(),
            "environment_variables": {
                "JUSTNEWS_ENV": os.environ.get("JUSTNEWS_ENV"),
                "ENV": os.environ.get("ENV"),
            },
            "detection_method": self._get_detection_method(),
        }

    def _get_detection_method(self) -> str:
        """Get the method used to detect the current environment"""
        if os.environ.get("JUSTNEWS_ENV"):
            return "environment_variable"
        elif os.environ.get("ENV"):
            return "env_variable"

        import socket

        hostname = socket.gethostname().lower()

        if any(
            pattern in hostname
            for pattern in [
                "dev",
                "development",
                "local",
                "staging",
                "stage",
                "test",
                "prod",
                "production",
                "live",
            ]
        ):
            return "hostname_pattern"

        # Check for environment marker files (docker-compose and Kubernetes deprecated)
        if any(
            os.path.exists(f)
            for f in [
                ".env.development",
                ".env.staging",
                ".env.production",
                "infrastructure/systemd",
            ]
        ):
            return "environment_files"

        cwd = os.getcwd().lower()
        if any(
            pattern in cwd
            for pattern in [
                "/dev/",
                "/development/",
                "/local/",
                "/staging/",
                "/stage/",
                "/test/",
                "/prod/",
                "/production/",
                "/live/",
            ]
        ):
            return "working_directory"

        return "default"

    def set_active_profile(self, profile_name: str):
        """Set the active configuration profile"""
        if profile_name not in self.profiles_config:
            available_profiles = list(self.profiles_config.keys())
            raise ValueError(
                f"Profile '{profile_name}' not found. Available profiles: {available_profiles}"
            )

        self.active_profile = profile_name
        os.environ["GPU_CONFIG_PROFILE"] = profile_name
        logger.info(f"Active configuration profile set to: {profile_name}")

    def get_available_profiles(self) -> list[dict[str, Any]]:
        """Get list of available configuration profiles"""
        profiles = []
        for name, config in self.profiles_config.items():
            profile_info = {
                "name": name,
                "description": config.get("description", "No description"),
                "is_active": name == self.active_profile,
            }
            profiles.append(profile_info)
        return profiles

    def create_profile(self, name: str, config: dict[str, Any], description: str = ""):
        """Create a new configuration profile"""
        if name in self.profiles_config:
            raise ValueError(f"Profile '{name}' already exists")

        profile_config = config.copy()
        profile_config["description"] = description
        self.profiles_config[name] = profile_config

        self._save_config_file(self.profiles_config_file, self.profiles_config)
        logger.info(f"Configuration profile '{name}' created")

    def update_profile(
        self, name: str, config: dict[str, Any], description: str = None
    ):
        """Update an existing configuration profile"""
        if name not in self.profiles_config:
            raise ValueError(f"Profile '{name}' not found")

        if description is not None:
            config["description"] = description

        self.profiles_config[name] = self._merge_configs(
            self.profiles_config[name], config
        )
        self._save_config_file(self.profiles_config_file, self.profiles_config)
        logger.info(f"Configuration profile '{name}' updated")

    def delete_profile(self, name: str):
        """Delete a configuration profile"""
        if name not in self.profiles_config:
            raise ValueError(f"Profile '{name}' not found")

        if name == "default":
            raise ValueError("Cannot delete the default profile")

        if name == self.active_profile:
            self.set_active_profile("default")

        del self.profiles_config[name]
        self._save_config_file(self.profiles_config_file, self.profiles_config)
        logger.info(f"Configuration profile '{name}' deleted")

    def restore_backup(self, backup_filename: str):
        """Restore configuration from backup"""
        backup_path = self.backup_dir / backup_filename

        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_filename}")

        # Determine config type from filename
        if "gpu_config" in backup_filename:
            target_file = self.main_config_file
        elif "environment_config" in backup_filename:
            target_file = self.env_config_file
        elif "model_config" in backup_filename:
            target_file = self.model_config_file
        else:
            raise ValueError(
                f"Cannot determine config type from backup filename: {backup_filename}"
            )

        # Restore the backup
        import shutil

        shutil.copy2(backup_path, target_file)

        # Reload configurations
        self._load_configs()

        logger.info(f"Configuration restored from backup: {backup_filename}")


# Global configuration manager instance
_config_manager: GPUConfigManager | None = None
_manager_lock = threading.Lock()


def get_config_manager() -> GPUConfigManager:
    """Get the global configuration manager instance"""
    global _config_manager
    with _manager_lock:
        if _config_manager is None:
            _config_manager = GPUConfigManager()
        return _config_manager


def get_gpu_config(environment: str = None, profile: str = None) -> dict[str, Any]:
    """Get GPU configuration for the current environment and profile"""
    manager = get_config_manager()
    return manager.get_config(environment, profile)


def get_model_config(model_name: str = None) -> dict[str, Any]:
    """Get model-specific configuration"""
    manager = get_config_manager()
    return manager.get_model_config(model_name)


def get_agent_models(agent_name: str) -> list[str]:
    """Get recommended models for an agent"""
    manager = get_config_manager()
    return manager.get_agent_models(agent_name)


def update_gpu_config(
    updates: dict[str, Any], environment: str = None, profile: str = None
):
    """Update GPU configuration"""
    manager = get_config_manager()
    if profile:
        manager.update_profile(profile, updates)
    else:
        manager.update_config(updates, environment)


# Initialize configuration manager on import
_config_manager = get_config_manager()
