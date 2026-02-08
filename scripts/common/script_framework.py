#!/usr/bin/env python3
"""
JustNews Script Framework Utilities

Common utilities and error handling for all JustNews scripts.
Provides standardized logging, error handling, and configuration management.
"""

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class ScriptConfig:
    """Configuration for script execution"""

    log_level: str = "INFO"
    log_file: str | None = None
    dry_run: bool = False
    verbose: bool = False
    quiet: bool = False


class ScriptFramework:
    """Base framework for JustNews scripts"""

    def __init__(self, script_name: str, description: str = ""):
        self.script_name = script_name
        self.description = description or f"JustNews {script_name} script"
        self.config = ScriptConfig()
        self.logger = None

    def setup_logging(self):
        """Setup standardized logging"""
        log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)

        # Create logger
        self.logger = logging.getLogger(self.script_name)
        self.logger.setLevel(log_level)

        # Remove existing handlers
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        # Console handler
        console_handler = logging.StreamHandler()
        if self.config.quiet:
            console_handler.setLevel(logging.WARNING)
        elif self.config.verbose:
            console_handler.setLevel(logging.DEBUG)
        else:
            console_handler.setLevel(log_level)

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # File handler if specified
        if self.config.log_file:
            file_handler = logging.FileHandler(self.config.log_file)
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    def parse_args(self) -> argparse.Namespace:
        """Parse common command line arguments"""
        parser = argparse.ArgumentParser(
            description=self.description,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )

        # Common arguments
        parser.add_argument(
            "--log-level",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            default="INFO",
            help="Set logging level (default: INFO)",
        )
        parser.add_argument("--log-file", help="Log to file in addition to console")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--verbose", "-v", action="store_true", help="Enable verbose output"
        )
        parser.add_argument(
            "--quiet", "-q", action="store_true", help="Suppress non-error output"
        )

        return parser

    def validate_environment(self) -> bool:
        """Validate that the environment is properly configured"""
        try:
            # Check if we're in the project root
            if not (PROJECT_ROOT / "requirements.txt").exists():
                self.logger.error(
                    f"Not in JustNews project root. Expected requirements.txt at {PROJECT_ROOT}"
                )
                return False

            # Check for conda environment if needed
            conda_env = os.environ.get("CONDA_DEFAULT_ENV")
            if conda_env:
                self.logger.info(f"Running in conda environment: {conda_env}")
            else:
                self.logger.warning("No conda environment detected")

            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Environment validation failed: {e}")
            return False

    def run_with_error_handling(self, main_func, *args, **kwargs):
        """Run main function with standardized error handling"""
        try:
            # Setup logging
            self.setup_logging()

            # Validate environment
            if not self.validate_environment():
                sys.exit(1)

            # Log script start
            if not self.config.quiet:
                self.logger.info(f"Starting {self.script_name}")
                if self.config.dry_run:
                    self.logger.info("DRY RUN MODE - No changes will be made")

            # Run main function
            result = main_func(*args, **kwargs)

            # Log completion
            if not self.config.quiet:
                self.logger.info(f"{self.script_name} completed successfully")

            return result

        except KeyboardInterrupt:
            if self.logger:
                self.logger.info(f"{self.script_name} interrupted by user")
            sys.exit(130)

        except Exception as e:
            if self.logger:
                self.logger.error(f"{self.script_name} failed: {e}", exc_info=True)
            else:
                print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)


def get_database_config() -> dict[str, Any]:
    """Get database configuration from environment"""
    # Use MariaDB environment variables for database configuration
    return {
        "host": os.environ.get("MARIADB_HOST", "localhost"),
        "port": int(os.environ.get("MARIADB_PORT", "3306")),
        "database": os.environ.get("MARIADB_DB", "justnews"),
        "user": os.environ.get("MARIADB_USER", "justnews_user"),
        "password": os.environ.get("MARIADB_PASSWORD", "password123"),
    }


def get_model_store_config() -> dict[str, str]:
    """Get model store configuration"""
    base_dir = os.environ.get("MODEL_STORE_ROOT", str(PROJECT_ROOT / "model_store"))
    return {
        "model_store_root": base_dir,
        "agent_models_dir": os.environ.get(
            "BASE_MODEL_DIR", str(PROJECT_ROOT / "agents")
        ),
    }


def confirm_action(message: str, default: bool = False) -> bool:
    """Get user confirmation for potentially destructive actions"""
    if default:
        prompt = f"{message} [Y/n]: "
    else:
        prompt = f"{message} [y/N]: "

    try:
        response = input(prompt).strip().lower()
        if not response:
            return default
        return response in ("y", "yes")
    except KeyboardInterrupt:
        print("\nOperation cancelled")
        sys.exit(130)
