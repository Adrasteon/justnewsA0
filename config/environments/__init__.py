# JustNews Configuration Management - Environment Profiles
# Phase 2B: Configuration Management Refactoring

"""
Environment Profile Management

Provides environment-specific configuration profiles with:
- Hierarchical inheritance (base -> environment -> overrides)
- Environment detection and validation
- Profile validation and consistency checks
- Runtime environment switching
- Profile auditing and versioning
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from common.observability import get_logger

from ..schemas import Environment, JustNewsConfig, create_default_config

logger = get_logger(__name__)


@dataclass
class EnvironmentProfile:
    """
    Environment-specific configuration profile

    Provides hierarchical configuration with inheritance:
    base_config -> environment_overrides -> runtime_overrides
    """

    name: str
    environment: Environment
    description: str = ""
    base_config: JustNewsConfig = field(default_factory=create_default_config)
    overrides: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Profile metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    version: str = "1.0.0"
    checksum: str | None = None

    def __post_init__(self):
        """Initialize profile with computed fields"""
        if not self.checksum:
            self.checksum = self._calculate_checksum()

    def _calculate_checksum(self) -> str:
        """Calculate profile checksum for integrity verification"""
        profile_data = {
            "name": self.name,
            "environment": self.environment.value,
            "overrides": self.overrides,
            "version": self.version,
        }
        data_str = json.dumps(profile_data, sort_keys=True, default=str)
        return hashlib.sha256(data_str.encode()).hexdigest()

    def apply_overrides(self, config: JustNewsConfig) -> JustNewsConfig:
        """
        Apply profile overrides to configuration

        Args:
            config: Base configuration to modify

        Returns:
            JustNewsConfig: Configuration with overrides applied
        """
        config_dict = config.model_dump()

        # Apply overrides
        self._deep_merge(config_dict, self.overrides)

        # Create new configuration with overrides
        try:
            return JustNewsConfig(**config_dict)
        except Exception as e:
            raise ValueError(
                f"Failed to apply profile overrides for {self.name}: {e}"
            ) from e

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]):
        """Deep merge override dictionary into base dictionary"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def validate(self) -> list[str]:
        """
        Validate profile consistency

        Returns:
            List[str]: List of validation errors (empty if valid)
        """
        errors = []

        # Validate environment consistency
        if self.environment == Environment.PRODUCTION:
            if self.overrides.get("system", {}).get("debug_mode", False):
                errors.append("Production profiles cannot have debug_mode enabled")

        # Validate required overrides for production
        if self.environment == Environment.PRODUCTION:
            required_overrides = [
                ("database", "password"),
                ("security", "api_key_required"),
                ("monitoring", "enabled"),
            ]

            for section, key in required_overrides:
                if not self._has_override(section, key):
                    errors.append(f"Production profile must override {section}.{key}")

        # Validate checksum
        if self.checksum != self._calculate_checksum():
            errors.append("Profile checksum mismatch - profile may be corrupted")

        return errors

    def _has_override(self, section: str, key: str) -> bool:
        """Check if profile has a specific override"""
        return section in self.overrides and key in self.overrides[section]

    def to_dict(self) -> dict[str, Any]:
        """Convert profile to dictionary for serialization"""
        return {
            "name": self.name,
            "environment": self.environment.value,
            "description": self.description,
            "overrides": self.overrides,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnvironmentProfile":
        """Create profile from dictionary"""
        # Convert environment string back to enum
        environment = Environment(data["environment"])

        # Parse timestamps
        created_at = datetime.fromisoformat(data["created_at"])
        updated_at = datetime.fromisoformat(data["updated_at"])

        return cls(
            name=data["name"],
            environment=environment,
            description=data.get("description", ""),
            overrides=data.get("overrides", {}),
            metadata=data.get("metadata", {}),
            created_at=created_at,
            updated_at=updated_at,
            version=data.get("version", "1.0.0"),
            checksum=data.get("checksum"),
        )


class EnvironmentProfileManager:
    """
    Manages environment-specific configuration profiles

    Provides:
    - Profile loading and validation
    - Environment detection
    - Profile inheritance and composition
    - Profile auditing and versioning
    """

    def __init__(self, profiles_dir: str | Path | None = None):
        """
        Initialize profile manager

        Args:
            profiles_dir: Directory containing profile files (auto-discovered if None)
        """
        self.profiles_dir = (
            Path(profiles_dir) if profiles_dir else self._find_profiles_dir()
        )
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        # Profile cache
        self._profiles: dict[str, EnvironmentProfile] = {}
        self._loaded_profiles: set[str] = set()

        # Load built-in profiles
        self._load_builtin_profiles()

        logger.info(
            f"✅ Environment profile manager initialized (profiles dir: {self.profiles_dir})"
        )

    def _find_profiles_dir(self) -> Path:
        """Find profiles directory using standard search paths"""
        search_paths = [
            Path.cwd() / "config" / "refactor" / "environments",
            Path.cwd() / "config" / "environments",
            Path.home() / ".justnews" / "environments",
            Path("/etc/justnews/environments"),
        ]

        for path in search_paths:
            if path.exists() and path.is_dir():
                return path

        # Return default path
        return Path.cwd() / "config" / "refactor" / "environments"

    def _load_builtin_profiles(self):
        """Load built-in environment profiles"""
        # Development profile
        dev_profile = EnvironmentProfile(
            name="development",
            environment=Environment.DEVELOPMENT,
            description="Development environment with debug features enabled",
            overrides={
                "system": {"debug_mode": True, "log_level": "DEBUG"},
                "database": {"host": "localhost", "database": "justnews_dev"},
                "gpu": {
                    "enabled": False  # Disable GPU in dev by default
                },
                "monitoring": {"enabled": False},
            },
        )

        # Staging profile
        staging_profile = EnvironmentProfile(
            name="staging",
            environment=Environment.STAGING,
            description="Staging environment for testing and validation",
            overrides={
                "system": {"debug_mode": False, "log_level": "INFO"},
                "database": {
                    "host": "staging-db.justnews.internal",
                    "database": "justnews_staging",
                },
                "gpu": {"enabled": True},
                "monitoring": {"enabled": True},
                "security": {"api_key_required": True},
            },
        )

        # Production profile
        prod_profile = EnvironmentProfile(
            name="production",
            environment=Environment.PRODUCTION,
            description="Production environment with security and performance optimizations",
            overrides={
                "system": {"debug_mode": False, "log_level": "WARNING"},
                "database": {
                    "host": "prod-db.justnews.internal",
                    "database": "justnews_prod",
                },
                "gpu": {"enabled": True},
                "monitoring": {"enabled": True, "metrics_enabled": True},
                "security": {"api_key_required": True, "rate_limiting_enabled": True},
                "performance": {"caching_enabled": True, "connection_pooling": True},
            },
        )

        # Register built-in profiles
        self._profiles["development"] = dev_profile
        self._profiles["staging"] = staging_profile
        self._profiles["production"] = prod_profile

    def get_profile(self, name: str) -> EnvironmentProfile:
        """
        Get environment profile by name

        Args:
            name: Profile name

        Returns:
            EnvironmentProfile: The requested profile

        Raises:
            ValueError: If profile not found
        """
        if name not in self._profiles:
            # Try to load from file
            self._load_profile_from_file(name)

        if name not in self._profiles:
            available = list(self._profiles.keys())
            raise ValueError(
                f"Profile '{name}' not found. Available profiles: {available}"
            )

        return self._profiles[name]

    def _load_profile_from_file(self, name: str):
        """Load profile from file"""
        profile_file = self.profiles_dir / f"{name}.json"

        if not profile_file.exists():
            return

        try:
            with open(profile_file) as f:
                data = json.load(f)

            profile = EnvironmentProfile.from_dict(data)

            # Validate profile
            errors = profile.validate()
            if errors:
                logger.warning(f"Profile '{name}' has validation errors: {errors}")

            self._profiles[name] = profile
            self._loaded_profiles.add(name)

            logger.debug(f"Loaded profile '{name}' from {profile_file}")

        except Exception as e:
            logger.error(f"Failed to load profile '{name}' from {profile_file}: {e}")

    def save_profile(self, profile: EnvironmentProfile, overwrite: bool = False):
        """
        Save profile to file

        Args:
            profile: Profile to save
            overwrite: Whether to overwrite existing file
        """
        profile_file = self.profiles_dir / f"{profile.name}.json"

        if profile_file.exists() and not overwrite:
            raise FileExistsError(f"Profile file already exists: {profile_file}")

        try:
            # Update metadata
            profile.updated_at = datetime.now()
            profile.checksum = profile._calculate_checksum()

            # Save to file
            with open(profile_file, "w") as f:
                json.dump(profile.to_dict(), f, indent=2, default=str)

            # Update cache
            self._profiles[profile.name] = profile
            self._loaded_profiles.add(profile.name)

            logger.info(f"✅ Saved profile '{profile.name}' to {profile_file}")

        except Exception as e:
            error_msg = f"Failed to save profile '{profile.name}': {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def create_profile(
        self,
        name: str,
        environment: Environment,
        base_profile: str | None = None,
        description: str = "",
        overrides: dict[str, Any] | None = None,
    ) -> EnvironmentProfile:
        """
        Create new environment profile

        Args:
            name: Profile name
            environment: Target environment
            base_profile: Name of profile to inherit from
            description: Profile description
            overrides: Configuration overrides

        Returns:
            EnvironmentProfile: Created profile
        """
        # Get base configuration
        if base_profile:
            base_config = self.get_profile(base_profile).base_config
        else:
            base_config = create_default_config()

        # Create profile
        profile = EnvironmentProfile(
            name=name,
            environment=environment,
            description=description,
            base_config=base_config,
            overrides=overrides or {},
        )

        # Validate profile
        errors = profile.validate()
        if errors:
            raise ValueError(f"Profile validation failed: {errors}")

        # Save profile
        self.save_profile(profile)

        logger.info(f"✅ Created profile '{name}' for environment {environment.value}")
        return profile

    def detect_environment(self) -> Environment:
        """
        Detect current environment from various sources

        Priority order:
        1. JUSTNEWS_ENVIRONMENT environment variable
        2. Deployment-specific files
        3. Hostname patterns
        4. Default to development

        Returns:
            Environment: Detected environment
        """
        # Check environment variable
        env_var = os.environ.get("JUSTNEWS_ENVIRONMENT")
        if env_var:
            try:
                return Environment(env_var.lower())
            except ValueError:
                logger.warning(f"Invalid JUSTNEWS_ENVIRONMENT value: {env_var}")

        # Check deployment files
        if Path("/etc/justnews/production").exists():
            return Environment.PRODUCTION
        if Path("/etc/justnews/staging").exists():
            return Environment.STAGING

        # Check hostname patterns
        import socket

        hostname = socket.gethostname().lower()
        if "prod" in hostname or "production" in hostname:
            return Environment.PRODUCTION
        if "staging" in hostname or "stage" in hostname:
            return Environment.STAGING

        # Default to development
        return Environment.DEVELOPMENT

    def list_profiles(self) -> list[str]:
        """List all available profile names"""
        # Load any new profiles from files
        self._load_all_profiles_from_files()

        return list(self._profiles.keys())

    def _load_all_profiles_from_files(self):
        """Load all profiles from files"""
        if not self.profiles_dir.exists():
            return

        for profile_file in self.profiles_dir.glob("*.json"):
            profile_name = profile_file.stem
            if profile_name not in self._loaded_profiles:
                self._load_profile_from_file(profile_name)

    def validate_all_profiles(self) -> dict[str, list[str]]:
        """
        Validate all profiles

        Returns:
            Dict[str, List[str]]: Profile name -> validation errors
        """
        self._load_all_profiles_from_files()

        results = {}
        for name, profile in self._profiles.items():
            errors = profile.validate()
            if errors:
                results[name] = errors

        return results

    def get_profile_info(self, name: str) -> dict[str, Any]:
        """Get profile metadata"""
        profile = self.get_profile(name)

        return {
            "name": profile.name,
            "environment": profile.environment.value,
            "description": profile.description,
            "version": profile.version,
            "created_at": profile.created_at.isoformat(),
            "updated_at": profile.updated_at.isoformat(),
            "checksum": profile.checksum,
            "overrides_count": len(profile.overrides),
        }


# ============================================================================
# GLOBAL PROFILE MANAGER INSTANCE
# ============================================================================

_profile_manager: EnvironmentProfileManager | None = None


def get_profile_manager() -> EnvironmentProfileManager:
    """Get global profile manager instance"""
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = EnvironmentProfileManager()
    return _profile_manager


# Export public API
__all__ = ["EnvironmentProfile", "EnvironmentProfileManager", "get_profile_manager"]
