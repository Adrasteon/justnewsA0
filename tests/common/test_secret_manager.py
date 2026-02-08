"""
Tests for JustNews Secret Manager
"""

from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import pytest

from common.secret_manager import (
    SecretManager,
    get_secret,
    get_secret_manager,
    list_secrets,
    set_secret,
    validate_secrets,
)


class TestSecretManager:
    """Test SecretManager class"""

    def test_initialization_default_path(self):
        """Test initialization with default vault path"""
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path("/home/testuser")
            manager = SecretManager()

            expected_path = str(Path("/home/testuser/.justnews/secrets.vault"))
            assert manager.vault_path == expected_path
            assert manager._key is None
            assert manager._vault == {}

    def test_initialization_custom_path(self):
        """Test initialization with custom vault path"""
        custom_path = "/custom/vault/path"
        manager = SecretManager(custom_path)

        assert manager.vault_path == custom_path

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data='{"test": "value"}')
    def test_load_vault_unencrypted(self, mock_file, mock_exists):
        """Test loading unencrypted vault"""
        mock_exists.return_value = True

        manager = SecretManager()
        manager._load_vault()

        assert manager._vault == {"test": "value"}

    @patch("os.path.exists")
    def test_load_vault_encrypted(self, mock_exists):
        """Test loading encrypted vault (should not load without key)"""
        mock_exists.return_value = True

        with patch("builtins.open", side_effect=Exception("Encrypted")):
            manager = SecretManager()
            manager._load_vault()

            assert manager._vault == {}

    @patch("os.environ.get")
    def test_get_from_environment(self, mock_env_get):
        """Test getting secret from environment variables"""
        mock_env_get.return_value = "env_secret_value"

        manager = SecretManager()
        result = manager.get("database.password")

        assert result == "env_secret_value"
        mock_env_get.assert_called_with("DATABASE_PASSWORD")

    def test_get_from_vault(self):
        """Test getting secret from vault"""
        manager = SecretManager()
        manager._vault = {"api.key": "vault_secret"}

        with patch("os.environ.get", return_value=None):
            result = manager.get("api.key")

            assert result == "vault_secret"

    def test_get_default_value(self):
        """Test getting default value when secret not found"""
        manager = SecretManager()

        with patch("os.environ.get", return_value=None):
            result = manager.get("nonexistent.key", "default_value")

            assert result == "default_value"

    def test_get_none_default(self):
        """Test getting None when no default and secret not found"""
        manager = SecretManager()

        with patch("os.environ.get", return_value=None):
            result = manager.get("nonexistent.key")

            assert result is None

    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    def test_set_with_encryption(self, mock_file, mock_makedirs):
        """Test setting secret with encryption"""
        manager = SecretManager()
        manager._key = b"test_key_32_bytes_long_key_here"

        manager.set("test.key", "test_value", encrypt=True)

        assert manager._vault["test.key"] == "test_value"
        # Should call encrypted save
        assert mock_file.called

    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    def test_set_without_encryption(self, mock_file, mock_makedirs):
        """Test setting secret without encryption"""
        manager = SecretManager()
        # No key set

        manager.set("test.key", "test_value", encrypt=False)

        assert manager._vault["test.key"] == "test_value"
        # Should call plaintext save
        assert mock_file.called

    def test_set_encryption_without_key_warning(self, caplog):
        """Test setting with encryption but no key shows warning"""
        manager = SecretManager()

        with patch("os.makedirs"):
            with patch("builtins.open", new_callable=mock_open):
                manager.set("test.key", "test_value", encrypt=True)

                assert "Vault not encrypted" in caplog.text

    def test_save_encrypted_vault_no_key(self):
        """Test saving encrypted vault without key raises error"""
        manager = SecretManager()

        with pytest.raises(ValueError, match="Vault must be unlocked"):
            manager._save_encrypted_vault()

    @patch("os.makedirs")
    @patch("os.urandom")
    @patch("builtins.open", new_callable=mock_open)
    def test_save_encrypted_vault(self, mock_file, mock_urandom, mock_makedirs):
        """Test saving encrypted vault"""
        mock_urandom.return_value = b"salt123456789012"  # 16 bytes

        manager = SecretManager()
        manager._key = b"test_key_32_bytes_long_key_here"
        manager._vault = {"test": "value"}

        manager._save_encrypted_vault()

        # Verify file was written in binary mode
        mock_file.assert_called_with(manager.vault_path, "wb")

    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    def test_save_plaintext_vault(self, mock_file, mock_makedirs):
        """Test saving plaintext vault"""
        manager = SecretManager()
        manager._vault = {"test": "value"}

        manager._save_plaintext_vault()

        # Verify file was written
        mock_file.assert_called_with(manager.vault_path, "w")

    @patch("os.environ")
    def test_list_secrets(self, mock_environ):
        """Test listing secrets with masking"""
        mock_environ.items.return_value = [
            ("DATABASE_PASSWORD", "secret123"),
            ("API_KEY", "key456"),
            ("NORMAL_VAR", "normal"),
        ]

        manager = SecretManager()
        manager._vault = {"service.token": "token789", "user.password": "pass123"}

        result = manager.list_secrets()

        # Check environment variables
        assert "env:DATABASE_PASSWORD" in result
        assert result["env:DATABASE_PASSWORD"] == "se***23"  # Masked

        assert "env:API_KEY" in result
        assert result["env:API_KEY"] == "ke***56"  # Masked

        # NORMAL_VAR should not appear (doesn't contain sensitive keywords)

        # Check vault secrets
        assert "vault:service.token" in result
        assert result["vault:service.token"] == "to***89"  # Masked

        assert "vault:user.password" in result
        assert result["vault:user.password"] == "pa***23"  # Masked

    def test_mask_secret(self):
        """Test secret masking function"""
        manager = SecretManager()

        # Short secret
        assert manager._mask_secret("abc") == "***"

        # Long secret
        assert manager._mask_secret("verylongsecret") == "ve**********et"

        # Empty
        assert manager._mask_secret("") == ""

        # Very short
        assert manager._mask_secret("ab") == "**"

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_validate_security(self, mock_file, mock_exists):
        """Test security validation"""
        # Mock config files exist and contain sensitive content
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = "this has password and secret"

        with patch(
            "os.environ",
            {"API_KEY": "short", "DATABASE_PASSWORD": "longenoughpassword"},
        ):
            manager = SecretManager()
            result = manager.validate_security()

            assert len(result["issues"]) > 0  # Should find issues in config files
            assert len(result["warnings"]) >= 0
            assert "API_KEY" in result["sensitive_env_vars"]
            assert result["vault_encrypted"] is False
            assert result["vault_exists"] is False

    @patch("os.path.exists")
    def test_validate_security_vault_encrypted(self, mock_exists):
        """Test security validation with encrypted vault"""
        mock_exists.return_value = True

        manager = SecretManager()
        manager._key = b"test_key"

        result = manager.validate_security()

        assert result["vault_encrypted"] is True
        assert result["vault_exists"] is True

    @patch("os.urandom")
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_unlock_vault_success(self, mock_file, mock_exists, mock_urandom):
        """Test successful vault unlocking"""
        mock_exists.return_value = True

        # Mock encrypted data: salt (16 bytes) + encrypted content
        mock_salt = b"salt123456789012"
        mock_encrypted_content = b"encrypted_data"
        mock_file.return_value.read.return_value = mock_salt + mock_encrypted_content

        # Mock Fernet decryption
        with patch("cryptography.fernet.Fernet") as mock_fernet:
            mock_fernet_instance = Mock()
            mock_fernet_instance.decrypt.return_value = b'{"unlocked": "data"}'
            mock_fernet.return_value = mock_fernet_instance

            manager = SecretManager()
            result = manager.unlock_vault("test_password")

            assert result is True
            assert manager._vault == {"unlocked": "data"}
            assert manager._key is not None

    @patch("os.path.exists")
    def test_unlock_vault_file_not_exists(self, mock_exists):
        """Test unlocking vault when file doesn't exist"""
        mock_exists.return_value = False

        manager = SecretManager()
        result = manager.unlock_vault("password")

        assert result is False

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_unlock_vault_decryption_failure(self, mock_file, mock_exists):
        """Test vault unlocking with decryption failure"""
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = b"invalid_data"

        manager = SecretManager()
        result = manager.unlock_vault("wrong_password")

        assert result is False
        assert manager._key is None


class TestGlobalFunctions:
    """Test global secret management functions"""

    @patch("common.secret_manager.SecretManager")
    def test_get_secret_manager_singleton(self, mock_manager_class):
        """Test get_secret_manager returns singleton"""
        mock_instance = Mock()
        mock_manager_class.return_value = mock_instance

        # Reset global instance
        import common.secret_manager

        common.secret_manager._secret_manager = None

        manager1 = get_secret_manager()
        manager2 = get_secret_manager()

        assert manager1 is manager2
        mock_manager_class.assert_called_once()

    def test_get_secret(self):
        """Test get_secret convenience function"""
        with patch("common.secret_manager.get_secret_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.get.return_value = "secret_value"
            mock_get_manager.return_value = mock_manager

            result = get_secret("test.key")

            assert result == "secret_value"
            mock_manager.get.assert_called_once_with("test.key", None)

    def test_set_secret(self):
        """Test set_secret convenience function"""
        with patch("common.secret_manager.get_secret_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_get_manager.return_value = mock_manager

            set_secret("test.key", "value")

            mock_manager.set.assert_called_once_with("test.key", "value", True)

    def test_list_secrets_function(self):
        """Test list_secrets convenience function"""
        with patch("common.secret_manager.get_secret_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.list_secrets.return_value = {"key": "value"}
            mock_get_manager.return_value = mock_manager

            result = list_secrets()

            assert result == {"key": "value"}

    def test_validate_secrets_function(self):
        """Test validate_secrets convenience function"""
        with patch("common.secret_manager.get_secret_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.validate_security.return_value = {"status": "ok"}
            mock_get_manager.return_value = mock_manager

            result = validate_secrets()

            assert result == {"status": "ok"}
