#!/usr/bin/env python3
"""
Configuration Generator for JustNews
Generates environment-specific configuration files from Jinja2 templates
"""

import argparse
import json
import secrets
import string
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader


class ConfigGenerator:
    """Configuration file generator using Jinja2 templates"""

    def __init__(self, template_dir: str, output_dir: str):
        self.template_dir = Path(template_dir)
        self.output_dir = Path(output_dir)
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate_secret(self, length: int = 32) -> str:
        """Generate a cryptographically secure random string"""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def load_config_values(self, config_file: str = None) -> dict[str, Any]:
        """Load configuration values from file or use defaults"""
        defaults = {
            "deploy_env": "development",
            "deploy_target": "systemd",
            # Prefer MariaDB settings; provide psycopg2/postgres vars for compatibility
            "mariadb_host": "localhost",
            "mariadb_port": 3306,
            "mariadb_db": "justnews",
            "mariadb_user": "justnews",
            "mariadb_password": self.generate_secret(16),
            "postgres_host": "localhost",
            "postgres_port": 5432,
            "postgres_db": "justnews",
            "postgres_user": "justnews",
            "postgres_password": self.generate_secret(16),
            "redis_host": "localhost",
            "redis_port": 6379,
            "redis_password": "",
            "gpu_orchestrator_host": "localhost",
            "gpu_orchestrator_port": 8014,
            "cuda_visible_devices": "0",
            "mcp_bus_host": "localhost",
            "mcp_bus_port": 8000,
            "grafana_admin_password": "admin",
            "prometheus_retention_time": "30d",
            "log_level": "INFO",
            "log_format": "json",
            "secret_key": self.generate_secret(32),
            "jwt_secret_key": self.generate_secret(32),
        }

        if config_file and Path(config_file).exists():
            with open(config_file) as f:
                user_config = json.load(f)
            defaults.update(user_config)

        return defaults

    def generate_config(
        self, template_name: str, output_name: str, config_values: dict[str, Any]
    ) -> None:
        """Generate a configuration file from template"""
        template = self.jinja_env.get_template(template_name)
        output_content = template.render(**config_values)

        output_path = self.output_dir / output_name
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            f.write(output_content)

        print(f"Generated: {output_path}")

    def generate_all_configs(self, config_file: str = None) -> None:
        """Generate all configuration files for the deployment"""
        config_values = self.load_config_values(config_file)

        # Generate environment files for each environment
        environments = ["development", "staging", "production"]

        for env in environments:
            env_config = config_values.copy()
            env_config["deploy_env"] = env

            # Environment-specific adjustments
            if env == "production":
                env_config["log_level"] = "WARNING"
                env_config["cuda_visible_devices"] = "all"
            elif env == "staging":
                env_config["log_level"] = "INFO"
            elif env == "development":
                env_config["log_level"] = "DEBUG"
                env_config["log_format"] = "text"

            self.generate_config(
                "environment.env.j2", f"environments/{env}.env", env_config
            )

        print("Configuration generation completed!")


def main():
    parser = argparse.ArgumentParser(
        description="Generate JustNews configuration files"
    )
    parser.add_argument(
        "--template-dir",
        default="templates",
        help="Directory containing Jinja2 templates",
    )
    parser.add_argument(
        "--output-dir",
        default="config",
        help="Directory to output generated configuration files",
    )
    parser.add_argument("--config-file", help="JSON file with configuration overrides")
    parser.add_argument("--template", help="Specific template to generate")
    parser.add_argument(
        "--output", help="Output file name for single template generation"
    )

    args = parser.parse_args()

    # Adjust paths relative to script location
    script_dir = Path(__file__).parent
    template_dir = (
        script_dir.parent / args.template_dir
    )  # Go up one level to deploy/refactor
    output_dir = script_dir.parent / args.output_dir

    generator = ConfigGenerator(template_dir, output_dir)

    if args.template and args.output:
        # Generate single template
        config_values = generator.load_config_values(args.config_file)
        generator.generate_config(args.template, args.output, config_values)
    else:
        # Generate all configurations
        generator.generate_all_configs(args.config_file)


if __name__ == "__main__":
    main()
