#!/usr/bin/env python3
import getpass
import os
import sys
from pathlib import Path

from common.secret_manager import get_secret_manager

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

"""
Interactive Secret Management Tool for JustNews

This script provides an interactive interface for managing secrets, environment
variables, and validating security configuration.

Usage:
    python scripts/manage_secrets.py
"""


class SecretManagerCLI:
    """Interactive CLI for secret management"""

    def __init__(self):
        self.secret_manager = get_secret_manager()
        self.vault_unlocked = False

    def print_header(self, title: str):
        """Print a formatted header"""
        print(f"\n{'=' * 50}")
        print(f" {title}")
        print(f"{'=' * 50}")

    def print_menu(self):
        """Print the main menu"""
        self.print_header("JustNews Secret Manager")

        print("\nAvailable Commands:")
        print("1. List all secrets (masked)")
        print("2. Get a specific secret")
        print("3. Set a new secret")
        print("4. Unlock encrypted vault")
        print("5. Validate security configuration")
        print("6. Check environment variables")
        print("7. Generate .env template")
        print("8. Test pre-commit hook")
        print("9. Exit")

        print(
            f"\nVault Status: {'🔓 Unlocked' if self.vault_unlocked else '🔒 Locked'}"
        )
        print(f"Vault Path: {self.secret_manager.vault_path}")

    def list_secrets(self):
        """List all available secrets"""
        self.print_header("Available Secrets")

        secrets = self.secret_manager.list_secrets()

        if not secrets:
            print("No secrets found")
            return

        print("\nEnvironment Variables:")
        env_secrets = {k: v for k, v in secrets.items() if k.startswith("env:")}
        if env_secrets:
            for key, value in env_secrets.items():
                print(f"  {key}: {value}")
        else:
            print("  None found")

        print("\nVault Secrets:")
        vault_secrets = {k: v for k, v in secrets.items() if k.startswith("vault:")}
        if vault_secrets:
            for key, value in vault_secrets.items():
                print(f"  {key}: {value}")
        else:
            print("  None found (unlock vault to access)")

    def get_secret(self):
        """Get a specific secret"""
        self.print_header("Get Secret")

        key = input("Enter secret key: ").strip()
        if not key:
            print("❌ Key cannot be empty")
            return

        value = self.secret_manager.get(key)
        if value is not None:
            print(f"Secret '{key}': {self._mask_secret(str(value))}")
        else:
            print(f"❌ Secret '{key}' not found")

    def set_secret(self):
        """Set a new secret"""
        self.print_header("Set Secret")

        key = input("Enter secret key: ").strip()
        if not key:
            print("❌ Key cannot be empty")
            return

        value = getpass.getpass("Enter secret value (hidden): ").strip()
        if not value:
            print("❌ Value cannot be empty")
            return

        encrypt = input("Encrypt this secret? (y/n) [y]: ").strip().lower()
        encrypt = encrypt in ("", "y", "yes")

        try:
            self.secret_manager.set(key, value, encrypt=encrypt)
            print(f"✅ Secret '{key}' set successfully")
        except Exception as e:
            print(f"❌ Failed to set secret: {e}")

    def unlock_vault(self):
        """Unlock the encrypted vault"""
        self.print_header("Unlock Vault")

        if self.vault_unlocked:
            print("Vault is already unlocked")
            return

        password = getpass.getpass("Enter vault password: ")
        if not password:
            print("❌ Password cannot be empty")
            return

        if self.secret_manager.unlock_vault(password):
            self.vault_unlocked = True
            print("✅ Vault unlocked successfully")
        else:
            print("❌ Failed to unlock vault")

    def validate_security(self):
        """Validate security configuration"""
        self.print_header("Security Validation")

        validation = self.secret_manager.validate_security()

        if validation["issues"]:
            print("\n🚨 Security Issues:")
            for issue in validation["issues"]:
                print(f"  • {issue}")

        if validation["warnings"]:
            print("\n⚠️ Security Warnings:")
            for warning in validation["warnings"]:
                print(f"  • {warning}")

        print("\nVault Status:")
        print(f"  • Encrypted: {validation['vault_encrypted']}")
        print(f"  • Exists: {validation['vault_exists']}")

        if validation["sensitive_env_vars"]:
            print(
                f"\nSensitive Environment Variables: {len(validation['sensitive_env_vars'])}"
            )
            for var in validation["sensitive_env_vars"][:5]:  # Show first 5
                print(f"  • {var}")
            if len(validation["sensitive_env_vars"]) > 5:
                print(f"  ... and {len(validation['sensitive_env_vars']) - 5} more")

        if not validation["issues"] and not validation["warnings"]:
            print("\n✅ No security issues found!")

    def check_environment(self):
        """Check environment variables"""
        self.print_header("Environment Variables")

        sensitive_vars = []
        all_vars = []

        for key, _value in os.environ.items():
            all_vars.append(key)
            if any(
                secret in key.lower()
                for secret in ["password", "secret", "key", "token"]
            ):
                sensitive_vars.append(key)

        print(f"Total Environment Variables: {len(all_vars)}")
        print(f"Sensitive Variables: {len(sensitive_vars)}")

        if sensitive_vars:
            print("\nSensitive Variables Found:")
            for var in sensitive_vars:
                masked_value = self._mask_secret(os.environ[var])
                print(f"  • {var}: {masked_value}")

    def generate_env_template(self):
        """Generate .env template"""
        self.print_header("Generate .env Template")

        template_path = project_root / ".env.example"

        if template_path.exists():
            overwrite = (
                input(".env.example already exists. Overwrite? (y/n) [n]: ")
                .strip()
                .lower()
            )
            if overwrite not in ("y", "yes"):
                print("❌ Operation cancelled")
                return

        template_content = """# JustNews Environment Configuration
    # Copy this file to .env and fill in your actual values
    # NEVER commit .env to git!

    # Database Configuration (migrated)
    # The system now uses MariaDB + Chroma for article storage. Set these
    # values in your deployment secret manager and never commit credentials.
    MARIADB_HOST=localhost
    MARIADB_PORT=3306
    MARIADB_DB=justnews
    MARIADB_USER=justnews_user
    MARIADB_PASSWORD=your_secure_password_here

    # External API Keys (if needed)
    # OPENAI_API_KEY=sk-your-openai-key-here
    # ANTHROPIC_API_KEY=sk-ant-your-anthropic-key-here

    # Crawling Configuration
    CRAWLER_REQUESTS_PER_MINUTE=20
    CRAWLER_DELAY_BETWEEN_REQUESTS=2.0
    CRAWLER_CONCURRENT_SITES=3

    # System Configuration
    LOG_LEVEL=INFO
    DEBUG_MODE=false
    GPU_ENABLED=true

    # Optional: GPU Configuration
    # CUDA_VISIBLE_DEVICES=0
    # GPU_MEMORY_FRACTION=0.8

    # Optional: Model Cache Directories
    # MODEL_STORE_ROOT=/path/to/model/store
    # SYNTHESIZER_MODEL_CACHE=/path/to/synthesizer/cache

    # Optional: Logging
    # LOG_FILE=/var/log/justnews.log
    """

        try:
            with open(template_path, "w") as f:
                f.write(template_content)
            print(f"✅ .env.example generated at {template_path}")
        except Exception as e:
            print(f"❌ Failed to generate template: {e}")

    def test_precommit_hook(self):
        """Test the pre-commit hook"""
        self.print_header("Test Pre-commit Hook")

        # Create a test file with potential secrets
        test_file = project_root / "test_secrets.txt"
        test_content = """
# This file contains test secrets for pre-commit hook testing
API_KEY=sk-test123456789012345678901234567890
PASSWORD=mysecretpassword
TOKEN=abc123def456ghi789jkl012mno345pqr678stu901vwx
"""

        try:
            with open(test_file, "w") as f:
                f.write(test_content)

            print("✅ Test file created with sample secrets")
            print(f"📁 File: {test_file}")
            print("\nTo test the pre-commit hook:")
            print("1. Stage the test file: git add test_secrets.txt")
            print("2. Try to commit: git commit -m 'test'")
            print("3. The hook should block the commit")
            print("4. Clean up: git reset HEAD test_secrets.txt && rm test_secrets.txt")

        except Exception as e:
            print(f"❌ Failed to create test file: {e}")

    def _mask_secret(self, value: str) -> str:
        """Mask a secret value for display"""
        if len(value) <= 4:
            return "*" * len(value)
        return value[:2] + "*" * (len(value) - 4) + value[-2:]

    def run(self):
        """Main CLI loop"""
        while True:
            self.print_menu()
            try:
                choice = input("\nEnter your choice (1-9): ").strip()

                if choice == "1":
                    self.list_secrets()
                elif choice == "2":
                    self.get_secret()
                elif choice == "3":
                    self.set_secret()
                elif choice == "4":
                    self.unlock_vault()
                elif choice == "5":
                    self.validate_security()
                elif choice == "6":
                    self.check_environment()
                elif choice == "7":
                    self.generate_env_template()
                elif choice == "8":
                    self.test_precommit_hook()
                elif choice == "9":
                    print("\n👋 Goodbye!")
                    break
                else:
                    print("❌ Invalid choice. Please enter 1-9.")

                input("\nPress Enter to continue...")

            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                input("\nPress Enter to continue...")


def main():
    """Main entry point"""
    cli = SecretManagerCLI()
    cli.run()


if __name__ == "__main__":
    main()
