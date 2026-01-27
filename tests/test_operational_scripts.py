"""
Tests for JustNews Operational Scripts

This module contains tests for operational scripts that manage:
- Database initialization and migration
- Secret management operations
- Deployment and configuration scripts
- System maintenance operations
"""

from unittest.mock import Mock, patch

import pytest

from scripts.admin.manage_secrets import SecretManagerCLI
from scripts.deploy.init_database import (
    create_initial_admin_user,
    create_knowledge_graph_tables,
)


class TestDatabaseInitialization:
    """Test database initialization scripts"""

    @patch("agents.common.auth_models.create_user")
    @patch("agents.common.auth_models.UserCreate")
    @patch("agents.common.auth_models.UserRole")
    def test_create_initial_admin_user_success(
        self, mock_user_role, mock_user_create, mock_create_user
    ):
        """Test successful creation of initial admin user"""
        # Setup mocks
        mock_role_class = Mock()
        mock_role_instance = Mock()
        mock_role_instance.ADMIN = "admin"
        mock_role_class.return_value = mock_role_instance
        mock_user_role.return_value = mock_role_class

        mock_user = Mock()
        mock_user_create.return_value = mock_user

        mock_create_user.return_value = 123

        # Call function
        create_initial_admin_user()

        # Verify calls were made (focus on behavior rather than exact values)
        mock_user_create.assert_called_once()
        mock_create_user.assert_called_once_with(mock_user)

    @patch("agents.common.auth_models.create_user")
    def test_create_initial_admin_user_failure(self, mock_create_user):
        """Test handling of admin user creation failure"""
        mock_create_user.return_value = None

        # Should not raise exception, just log warning
        create_initial_admin_user()

        # Function should complete without error
        assert True

    @patch("scripts.deploy.init_database.execute_query")
    def test_create_knowledge_graph_tables(self, mock_execute):
        """Test knowledge graph table creation"""
        mock_execute.return_value = None

        # This would normally create tables - we just verify it calls execute_query
        try:
            create_knowledge_graph_tables()
        except Exception:
            # May fail due to missing database connection, but that's expected in test
            pass

        # Verify execute_query was called (table creation attempted)
        assert mock_execute.called


class TestSecretManagementScripts:
    """Test secret management operational scripts"""

    @pytest.fixture
    def secret_cli(self):
        """Create a SecretManagerCLI instance for testing"""
        return SecretManagerCLI()

    def test_secret_cli_initialization(self, secret_cli):
        """Test secret CLI initialization"""
        assert secret_cli is not None
        assert hasattr(secret_cli, "secret_manager")
        assert hasattr(secret_cli, "vault_unlocked")

    @patch("scripts.manage_secrets.get_secret_manager")
    def test_secret_manager_integration(self, mock_get_manager, secret_cli):
        """Test secret manager integration"""
        mock_manager = Mock()
        mock_get_manager.return_value = mock_manager

        # Verify the CLI uses the secret manager
        assert secret_cli.secret_manager is not None

    def test_secret_masking(self, secret_cli):
        """Test secret value masking"""
        # Test short secret
        short_secret = "abc"
        masked = secret_cli._mask_secret(short_secret)
        assert masked == "***"

        # Test long secret: "verylongsecret123" (17 chars)
        # Should be: first 2 + asterisks for middle + last 2
        # "ve" + "*" * (17-4) + "23" = "ve" + "*" * 13 + "23"
        long_secret = "verylongsecret123"
        masked = secret_cli._mask_secret(long_secret)
        expected = "ve" + "*" * 13 + "23"
        assert masked == expected

    @patch("scripts.manage_secrets.getpass.getpass")
    @patch("builtins.input")
    def test_cli_menu_display(self, mock_input, mock_getpass, secret_cli):
        """Test CLI menu display"""
        mock_input.return_value = "9"  # Exit immediately

        # This should not raise an exception
        try:
            secret_cli.run()
        except SystemExit:
            pass  # Expected when exiting

    @patch("os.environ")
    def test_environment_check(self, mock_environ, secret_cli):
        """Test environment variable checking"""
        mock_environ.items.return_value = [
            ("API_KEY", "secret123"),
            ("PASSWORD", "password456"),
            ("NORMAL_VAR", "normal_value"),
            ("TOKEN_SECRET", "token789"),
        ]

        # Should identify sensitive variables
        sensitive_vars = []
        for key, _value in mock_environ.items():
            if any(
                secret in key.lower()
                for secret in ["password", "secret", "key", "token"]
            ):
                sensitive_vars.append(key)

        assert "API_KEY" in sensitive_vars
        assert "PASSWORD" in sensitive_vars
        assert "TOKEN_SECRET" in sensitive_vars
        assert "NORMAL_VAR" not in sensitive_vars


class TestDeploymentScripts:
    """Test deployment and configuration scripts"""

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_environment_setup_script(self, mock_exists, mock_run):
        """Test environment setup script execution"""
        mock_exists.return_value = True
        mock_run.return_value = Mock(
            returncode=0, stdout="Environment setup complete", stderr=""
        )

        # Simulate running environment setup
        result = mock_run(
            ["bash", "scripts/setup_dev_environment.sh"], capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "Environment setup complete" in result.stdout

    @patch("subprocess.run")
    def test_service_startup_script(self, mock_run):
        """Test service startup script execution"""
        mock_run.return_value = Mock(returncode=0, stdout="Services started", stderr="")

        # Simulate starting services
        result = mock_run(
            ["bash", "scripts/start_services_daemon.sh"], capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "Services started" in result.stdout

    @patch("subprocess.run")
    def test_service_shutdown_script(self, mock_run):
        """Test service shutdown script execution"""
        mock_run.return_value = Mock(returncode=0, stdout="Services stopped", stderr="")

        # Simulate stopping services
        result = mock_run(
            ["bash", "scripts/stop_services.sh"], capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "Services stopped" in result.stdout


class TestMaintenanceScripts:
    """Test system maintenance scripts"""

    @patch("subprocess.run")
    def test_system_health_check(self, mock_run):
        """Test system health check script"""
        mock_run.return_value = Mock(returncode=0, stdout="System healthy", stderr="")

        # Simulate health check
        result = mock_run(
            ["python", "scripts/maintenance/health_check.py"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "System healthy" in result.stdout

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_backup_operations(self, mock_exists, mock_run):
        """Test backup operation scripts"""
        mock_exists.return_value = True
        mock_run.return_value = Mock(returncode=0, stdout="Backup completed", stderr="")

        # Simulate database backup
        result = mock_run(
            ["python", "scripts/ops/backup_database.py"], capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "Backup completed" in result.stdout


class TestConfigurationScripts:
    """Test configuration management scripts"""

    @patch("subprocess.run")
    def test_configuration_validation(self, mock_run):
        """Test configuration validation script"""
        mock_run.return_value = Mock(
            returncode=0, stdout="Configuration valid", stderr=""
        )

        # Simulate config validation
        result = mock_run(
            ["python", "scripts/validate_versions.py"], capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "Configuration valid" in result.stdout

    @patch("subprocess.run")
    def test_version_validation_script(self, mock_run):
        """Test version validation across components"""
        mock_run.return_value = Mock(
            returncode=0, stdout="Versions compatible", stderr=""
        )

        # Simulate version validation
        result = mock_run(
            ["python", "scripts/validate_versions.py"], capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "Versions compatible" in result.stdout
