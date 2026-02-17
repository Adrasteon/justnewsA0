# JustNews Configuration System Tests
# Phase 2B: Configuration Management Refactoring

"""
Comprehensive test suite for the unified configuration system

Tests cover:
- Schema validation and type safety
- Configuration loading and saving
- Environment abstraction and inheritance
- Validation and error handling
- Legacy migration functionality
- Performance and benchmarking
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config.refactor import (
    ConfigurationError,
    # Core
    ConfigurationManager,
    ConfigurationTester,
    # Validation
    ConfigurationValidator,
    Environment,
    # Environments
    EnvironmentProfile,
    EnvironmentProfileManager,
    # Schemas
    JustNewsConfig,
    LegacyConfigurationMigrator,
    MigrationPlan,
    create_default_config,
    save_config_to_file,
)


class TestConfigurationSchemas:
    """Test configuration schema validation and type safety"""

    def test_default_config_creation(self):
        """Test default configuration creation"""
        config = create_default_config()

        assert isinstance(config, JustNewsConfig)
        assert config.system.environment == Environment.DEVELOPMENT
        assert (
            config.database.host == "localhost"
        )  # DatabaseConfig has host, not enabled
        assert config.gpu.enabled is True  # GPUConfig has enabled

    def test_config_validation(self):
        """Test configuration validation"""
        config = create_default_config()

        # Should validate without errors
        assert config.system.environment in Environment

        # Test serialization
        config_dict = config.model_dump()
        assert isinstance(config_dict, dict)
        assert "system" in config_dict

    def test_environment_enum(self):
        """Test environment enumeration"""
        assert Environment.DEVELOPMENT.value == "development"
        assert Environment.STAGING.value == "staging"
        assert Environment.PRODUCTION.value == "production"

    def test_nested_value_access(self):
        """Test nested value access methods"""
        config = create_default_config()

        # Test successful access
        assert config.get_nested_value("system.environment") == Environment.DEVELOPMENT

        # Test missing key
        with pytest.raises(KeyError):
            config.get_nested_value("nonexistent.key")

        # Test setting nested value
        config.set_nested_value("system.debug_mode", True)
        assert config.system.debug_mode is True


class TestConfigurationManager:
    """Test configuration manager functionality"""

    def test_manager_initialization(self):
        """Test configuration manager initialization"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "test_config.json"

            # Create test config
            test_config = create_default_config()
            save_config_to_file(test_config, config_file)

            # Initialize manager
            manager = ConfigurationManager(config_file=config_file)

            assert manager.config_file == config_file
            assert isinstance(manager.config, JustNewsConfig)

    def test_configuration_reloading(self):
        """Test configuration reloading"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "test_config.json"

            # Create initial config
            test_config = create_default_config()
            save_config_to_file(test_config, config_file)

            manager = ConfigurationManager(config_file=config_file)

            # Modify config file
            test_config.system.debug_mode = True
            save_config_to_file(test_config, config_file)

            # Reload
            manager.reload()

            assert manager.config.system.debug_mode is True

    def test_runtime_configuration_updates(self):
        """Test runtime configuration updates"""
        manager = ConfigurationManager()

        # Test setting values
        manager.set("system.debug_mode", True)
        assert manager.config.system.debug_mode is True

        manager.set("database.host", "testhost")
        assert manager.config.database.host == "testhost"

    def test_configuration_validation_on_update(self):
        """Test configuration validation during updates"""
        manager = ConfigurationManager()

        # Try to set conflicting agent ports (should fail validation)
        with pytest.raises(ConfigurationError):
            manager.set("agents.ports.chief_editor", 8002)  # Conflict with scout port

    def test_audit_trail(self):
        """Test configuration change audit trail"""
        manager = ConfigurationManager()

        # Make some changes
        manager.set("system.debug_mode", True)
        manager.set("database.host", "newhost")

        audit_log = manager.get_audit_log()
        assert len(audit_log) >= 2

        # Check audit entry structure
        entry = audit_log[0]
        assert "timestamp" in entry
        assert "operation" in entry
        assert entry["operation"] == "set"


class TestEnvironmentProfiles:
    """Test environment profile management"""

    def test_builtin_profiles(self):
        """Test built-in environment profiles"""
        profile_manager = EnvironmentProfileManager()

        # Check development profile
        dev_profile = profile_manager.get_profile("development")
        assert dev_profile.environment == Environment.DEVELOPMENT
        assert dev_profile.overrides["system"]["debug_mode"] is True

        # Check production profile
        prod_profile = profile_manager.get_profile("production")
        assert prod_profile.environment == Environment.PRODUCTION
        assert prod_profile.overrides["system"]["debug_mode"] is False

    def test_profile_validation(self):
        """Test profile validation"""
        profile = EnvironmentProfile(
            name="test",
            environment=Environment.DEVELOPMENT,
            overrides={"system": {"debug_mode": True}},
        )

        errors = profile.validate()
        assert len(errors) == 0  # Should be valid

        # Test invalid profile (production with debug enabled)
        invalid_profile = EnvironmentProfile(
            name="invalid",
            environment=Environment.PRODUCTION,
            overrides={"system": {"debug_mode": True}},
        )

        errors = invalid_profile.validate()
        assert len(errors) > 0
        assert "debug_mode" in str(errors[0]).lower()

    def test_profile_inheritance(self):
        """Test profile inheritance and overrides"""
        base_config = create_default_config()
        profile = EnvironmentProfile(
            name="test",
            environment=Environment.DEVELOPMENT,
            overrides={"database": {"host": "overridden_host"}},
        )

        result_config = profile.apply_overrides(base_config)

        # Check that override was applied
        assert result_config.database.host == "overridden_host"

        # Check that other values remain default
        assert result_config.system.environment == Environment.DEVELOPMENT

    def test_environment_detection(self):
        """Test environment detection"""
        profile_manager = EnvironmentProfileManager()

        # Test environment variable detection
        with patch.dict("os.environ", {"JUSTNEWS_ENVIRONMENT": "production"}):
            detected = profile_manager.detect_environment()
            assert detected == Environment.PRODUCTION

        # Test hostname detection
        with patch("socket.gethostname", return_value="prod-server-01"):
            detected = profile_manager.detect_environment()
            assert detected == Environment.PRODUCTION


class TestConfigurationValidation:
    """Test configuration validation"""

    def test_schema_validation(self):
        """Test schema validation"""
        validator = ConfigurationValidator()
        config = create_default_config()

        result = validator.validate(config)

        assert result.is_valid
        assert len(result.errors) == 0
        assert result.duration_ms > 0

    def test_cross_component_validation(self):
        """Test cross-component validation"""
        validator = ConfigurationValidator()

        # Test port conflicts
        config = create_default_config()
        # Create a conflict by setting two ports to the same value
        config.agents.ports.chief_editor = config.agents.ports.scout  # Create conflict

        result = validator.validate(config)

        assert not result.is_valid
        assert any("Port conflict" in error for error in result.errors)

    def test_environment_specific_validation(self):
        """Test environment-specific validation"""
        validator = ConfigurationValidator()

        # Test production requirements
        config = create_default_config()
        config.system.environment = Environment.PRODUCTION
        config.database.password = ""  # Missing required password

        result = validator.validate(config)

        assert not result.is_valid
        assert any("password" in error.lower() for error in result.errors)

    def test_performance_validation(self):
        """Test performance-related validation"""
        validator = ConfigurationValidator()
        config = create_default_config()

        # Test high connection pool
        config.database.connection_pool.max_connections = 200

        result = validator.validate(config)

        assert result.is_valid  # Should be valid but with warnings
        assert len(result.warnings) > 0

    def test_security_validation(self):
        """Test security-related validation"""
        validator = ConfigurationValidator()
        config = create_default_config()

        # Test production security requirements
        config.system.environment = Environment.PRODUCTION
        config.security.api_key_required = False

        result = validator.validate(config)

        assert not result.is_valid
        assert any("api key" in error.lower() for error in result.errors)


class TestConfigurationTesting:
    """Test configuration testing utilities"""

    def test_configuration_loading_test(self):
        """Test configuration loading simulation"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "test_config.json"

            # Create test config
            test_config = create_default_config()
            save_config_to_file(test_config, config_file)

            tester = ConfigurationTester()
            result = tester.test_configuration_loading(config_file)

            assert result.is_valid
            assert "Successfully loaded configuration" in " ".join(result.info)

    def test_agent_startup_simulation(self):
        """Test agent startup simulation"""
        tester = ConfigurationTester()
        config = create_default_config()

        result = tester.simulate_agent_startup(config)

        assert result.is_valid
        assert len(result.info) > 0  # Should have some info messages

    def test_performance_benchmarking(self):
        """Test configuration performance benchmarking"""
        tester = ConfigurationTester()
        config = create_default_config()

        results = tester.benchmark_configuration_performance(config)

        assert "validation_times" in results
        assert "serialization_times" in results
        assert "deserialization_times" in results
        assert "average_validation_time" in results
        assert len(results["validation_times"]) > 0


class TestLegacyMigration:
    """Test legacy configuration migration"""

    def test_legacy_file_discovery(self):
        """Test legacy configuration file discovery"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create some mock legacy files
            (temp_path / "database.json").write_text(
                '{"host": "localhost", "port": 5432}'
            )
            (temp_path / "gpu_config.py").write_text(
                "GPU_ENABLED = True\nBATCH_SIZE = 16"
            )
            (temp_path / "old_config.txt").write_text("some random content")

            migrator = LegacyConfigurationMigrator()
            files = migrator.discover_legacy_configs([temp_path])

            # Should find database.json and gpu_config.py, but not old_config.txt
            assert len(files) >= 2
            config_types = {f.config_type for f in files}
            assert "database" in config_types

    def test_migration_plan_creation(self):
        """Test migration plan creation"""
        migrator = LegacyConfigurationMigrator()

        # Mock some discovered files
        migrator.discovered_files = [
            MagicMock(
                path=Path("/tmp/database.json"),
                format="json",
                config_type="database",
                is_active=True,
                content_hash="test",
            )
        ]

        plan = migrator.create_migration_plan()

        assert isinstance(plan, MigrationPlan)
        assert len(plan.legacy_files) == 1
        assert isinstance(plan.target_config, JustNewsConfig)

    def test_database_config_migration(self):
        """Test database configuration migration"""
        migrator = LegacyConfigurationMigrator()
        config_dict = {}
        legacy_config = {
            "host": "testhost",
            "port": 5433,
            "user": "testuser",
            "password": "testpass",
        }

        steps = migrator._merge_database_config(config_dict, legacy_config)

        assert len(steps) > 0
        assert config_dict["database"]["host"] == "testhost"
        assert config_dict["database"]["port"] == 5433

    def test_compatibility_layer_generation(self):
        """Test compatibility layer generation"""
        migrator = LegacyConfigurationMigrator()

        # Create a simple migration plan
        plan = MigrationPlan(
            legacy_files=[],
            target_config=create_default_config(),
            migration_steps=["Set database.host = localhost"],
            conflicts=[],
            warnings=[],
            estimated_effort="low",
        )

        compat_code = migrator._generate_compatibility_code(plan)

        assert "Legacy Configuration Compatibility Layer" in compat_code
        assert "get_legacy_value" in compat_code
        assert "database_host" in compat_code  # Should create legacy key mapping


class TestIntegration:
    """Integration tests for the configuration system"""

    def test_full_configuration_workflow(self):
        """Test full configuration workflow"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Ensure env does not override file-backed configuration during test
            from unittest.mock import patch

            # Ensure the loader does not import system or repo-level global.env
            # during this test: mark PYTEST_RUNNING so load_global_env skips
            # Provide an empty explicit JUSTNEWS_GLOBAL_ENV inside temp_dir
            # so load_global_env will prefer that path and not load repo/system
            # global.env files which would override our test configuration.
            env_file = Path(temp_dir) / "global.env"
            env_file.write_text("")
            with patch.dict(
                os.environ,
                {"PYTEST_RUNNING": "1", "JUSTNEWS_GLOBAL_ENV": str(env_file)},
                clear=True,
            ):
                temp_path = Path(temp_dir)

                # Create configuration file
                config_file = temp_path / "system_config.json"
                config = create_default_config()
                config.system.debug_mode = True
                save_config_to_file(config, config_file)

                # Initialize manager
                manager = ConfigurationManager(config_file=config_file)

                # Validate configuration
                validator = ConfigurationValidator()
                result = validator.validate(manager.config)

                assert result.is_valid

                # Test configuration updates
                manager.set("database.host", "updated_host")
                assert manager.config.database.host == "updated_host"

                # Save and reload
                manager.save()
                manager.reload()

                assert manager.config.database.host == "updated_host"
                assert manager.config.system.debug_mode is True

    def test_environment_profile_workflow(self):
        """Test environment profile workflow"""
        profile_manager = EnvironmentProfileManager()

        # Get development profile
        dev_profile = profile_manager.get_profile("development")

        # Apply to configuration
        base_config = create_default_config()
        result_config = dev_profile.apply_overrides(base_config)

        # Validate result
        validator = ConfigurationValidator()
        result = validator.validate(result_config)

        assert result.is_valid
        assert result_config.system.debug_mode is True

    def test_validation_workflow(self):
        """Test validation workflow"""
        config = create_default_config()

        # Run comprehensive validation
        validator = ConfigurationValidator()
        result = validator.validate(config)

        assert result.is_valid

        # Run performance testing
        tester = ConfigurationTester()
        perf_results = tester.benchmark_configuration_performance(config)

        assert perf_results["average_validation_time"] > 0

        # Run startup simulation
        startup_result = tester.simulate_agent_startup(config)

        assert startup_result.is_valid


# ============================================================================
# TEST UTILITIES
# ============================================================================


def create_test_config_file(
    config: JustNewsConfig = None, temp_dir: str = None
) -> Path:
    """Create a test configuration file"""
    if config is None:
        config = create_default_config()

    if temp_dir is None:
        temp_dir = tempfile.mkdtemp()

    config_file = Path(temp_dir) / "test_config.json"
    save_config_to_file(config, config_file)

    return config_file


def create_test_legacy_files(temp_dir: str = None) -> list[Path]:
    """Create test legacy configuration files"""
    if temp_dir is None:
        temp_dir = tempfile.mkdtemp()

    temp_path = Path(temp_dir)

    # Create various legacy config files
    files = []

    # JSON database config
    db_file = temp_path / "database.json"
    db_file.write_text('{"host": "legacy-host", "port": 5432}')
    files.append(db_file)

    # Python GPU config
    gpu_file = temp_path / "gpu.py"
    gpu_file.write_text("GPU_ENABLED = True\nBATCH_SIZE = 8")
    files.append(gpu_file)

    # YAML monitoring config
    mon_file = temp_path / "monitoring.yaml"
    mon_file.write_text("enabled: true\nmetrics_enabled: false")
    files.append(mon_file)

    return files
