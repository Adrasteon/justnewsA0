# JustNews Configuration Management - Legacy Migration
# Phase 2B: Configuration Management Refactoring

"""
Legacy Configuration Migration Utilities

Provides migration from scattered configuration files to unified system:
- Legacy configuration discovery and analysis
- Automated migration with conflict resolution
- Migration validation and rollback
- Gradual migration support
- Legacy compatibility layer
"""

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from common.observability import get_logger

from ..schemas import Environment, JustNewsConfig, create_default_config
from ..validation import ConfigurationValidator, ValidationResult

logger = get_logger(__name__)


@dataclass
class LegacyConfigFile:
    """Represents a legacy configuration file"""
    path: Path
    format: str  # 'json', 'python', 'yaml', 'env'
    config_type: str  # 'database', 'gpu', 'agents', etc.
    last_modified: datetime
    size_bytes: int
    content_hash: str

    @property
    def is_active(self) -> bool:
        """Check if file is actively used"""
        # Check if file has been modified recently (last 30 days)
        return (datetime.now() - self.last_modified).days < 30


@dataclass
class MigrationPlan:
    """Configuration migration plan"""
    legacy_files: list[LegacyConfigFile]
    target_config: JustNewsConfig
    migration_steps: list[str]
    conflicts: list[str]
    warnings: list[str]
    estimated_effort: str  # 'low', 'medium', 'high'


class LegacyConfigurationMigrator:
    """
    Legacy configuration migration utilities

    Handles migration from scattered config files to unified system with:
    - Automatic discovery of legacy configurations
    - Conflict detection and resolution
    - Gradual migration support
    - Rollback capabilities
    - Legacy compatibility layer
    """

    def __init__(self):
        self.validator = ConfigurationValidator()
        self.discovered_files: list[LegacyConfigFile] = []

    def discover_legacy_configs(self, search_paths: list[str | Path] | None = None) -> list[LegacyConfigFile]:
        """
        Discover legacy configuration files

        Args:
            search_paths: Paths to search for config files

        Returns:
            List[LegacyConfigFile]: Discovered legacy configuration files
        """
        if search_paths is None:
            search_paths = [
                Path.cwd(),
                Path.cwd() / "config",
                Path.cwd() / "agents",
                Path.home() / ".justnews",
                Path("/etc/justnews")
            ]

        self.discovered_files = []

        # Known legacy configuration patterns
        patterns = [
            # JSON files
            ("*.json", "json"),
            # Python config files
            ("*config*.py", "python"),
            ("*settings*.py", "python"),
            # YAML files
            ("*.yaml", "yaml"),
            ("*.yml", "yaml"),
            # Environment files
            (".env*", "env"),
            # Database configs
            ("database.*", "json"),
            ("db.*", "json"),
            # GPU configs
            ("gpu.*", "json"),
            ("cuda.*", "json"),
            # Agent configs
            ("agents.*", "json"),
            ("agent_*.json", "json"),
        ]

        for search_path in search_paths:
            search_path = Path(search_path)
            if not search_path.exists():
                continue

            for pattern, format_type in patterns:
                for file_path in search_path.rglob(pattern):
                    if file_path.is_file() and not self._is_unified_config_file(file_path):
                        try:
                            legacy_file = self._analyze_config_file(file_path, format_type)
                            if legacy_file:
                                self.discovered_files.append(legacy_file)
                        except Exception as e:
                            logger.warning(f"Failed to analyze {file_path}: {e}")

        logger.info(f"Discovered {len(self.discovered_files)} legacy configuration files")
        return self.discovered_files

    def _is_unified_config_file(self, file_path: Path) -> bool:
        """Check if file is part of the new unified configuration system"""
        unified_paths = [
            "config/refactor/",
            "config/system_config.json",
            "config/environments/"
        ]

        file_str = str(file_path)
        return any(unified_path in file_str for unified_path in unified_paths)

    def _analyze_config_file(self, file_path: Path, format_type: str) -> LegacyConfigFile | None:
        """Analyze a configuration file"""
        try:
            stat = file_path.stat()
            content = file_path.read_text()

            # Calculate content hash
            import hashlib
            content_hash = hashlib.sha256(content.encode()).hexdigest()

            # Determine config type from filename and content
            config_type = self._determine_config_type(file_path, content)

            if config_type:
                return LegacyConfigFile(
                    path=file_path,
                    format=format_type,
                    config_type=config_type,
                    last_modified=datetime.fromtimestamp(stat.st_mtime),
                    size_bytes=stat.st_size,
                    content_hash=content_hash
                )

        except Exception as e:
            logger.debug(f"Failed to analyze {file_path}: {e}")

        return None

    def _determine_config_type(self, file_path: Path, content: str) -> str | None:
        """Determine configuration type from file path and content"""
        filename = file_path.name.lower()

        # Database configurations
        if any(keyword in filename or keyword in content.lower()
               for keyword in ['database', 'db', 'postgres', 'mysql', 'mongodb']):
            return 'database'

        # GPU configurations
        if any(keyword in filename or keyword in content.lower()
               for keyword in ['gpu', 'cuda', 'tensorrt', 'nvidia']):
            return 'gpu'

        # Agent configurations
        if any(keyword in filename or keyword in content.lower()
               for keyword in ['agent', 'mcp', 'scout', 'analyst', 'synthesizer']):
            return 'agents'

        # Crawling configurations
        if any(keyword in filename or keyword in content.lower()
               for keyword in ['crawl', 'scrape', 'spider', 'news']):
            return 'crawling'

        # Monitoring configurations
        if any(keyword in filename or keyword in content.lower()
               for keyword in ['monitor', 'metrics', 'alert', 'log']):
            return 'monitoring'

        # Security configurations
        if any(keyword in filename or keyword in content.lower()
               for keyword in ['security', 'auth', 'api_key', 'token']):
            return 'security'

        # Training configurations
        if any(keyword in filename or keyword in content.lower()
               for keyword in ['train', 'model', 'ml', 'ai']):
            return 'training'

        return None

    def create_migration_plan(self, target_environment: Environment = Environment.DEVELOPMENT) -> MigrationPlan:
        """
        Create migration plan from discovered legacy configurations

        Args:
            target_environment: Target environment for migration

        Returns:
            MigrationPlan: Comprehensive migration plan
        """
        # Start with default configuration
        target_config = create_default_config()
        target_config.system.environment = target_environment

        migration_steps = []
        conflicts = []
        warnings = []

        # Process each legacy file
        processed_types: set[str] = set()

        for legacy_file in self.discovered_files:
            if not legacy_file.is_active:
                warnings.append(f"Legacy file {legacy_file.path} appears inactive (not modified recently)")
                continue

            try:
                # Load legacy configuration
                legacy_config = self._load_legacy_config(legacy_file)

                # Check for conflicts
                file_conflicts = self._check_migration_conflicts(legacy_config, processed_types)
                conflicts.extend(file_conflicts)

                # Merge configuration
                merge_result = self._merge_legacy_config(target_config, legacy_config, legacy_file.config_type)
                target_config = merge_result[0]
                migration_steps.extend(merge_result[1])

                processed_types.add(legacy_file.config_type)

            except Exception as e:
                conflicts.append(f"Failed to migrate {legacy_file.path}: {e}")

        # Determine effort level
        effort = self._estimate_migration_effort(len(self.discovered_files), len(conflicts), len(warnings))

        return MigrationPlan(
            legacy_files=self.discovered_files,
            target_config=target_config,
            migration_steps=migration_steps,
            conflicts=conflicts,
            warnings=warnings,
            estimated_effort=effort
        )

    def _load_legacy_config(self, legacy_file: LegacyConfigFile) -> dict[str, Any]:
        """Load configuration from legacy file"""
        try:
            if legacy_file.format == 'json':
                with open(legacy_file.path) as f:
                    return json.load(f)
            elif legacy_file.format == 'python':
                return self._load_python_config(legacy_file.path)
            elif legacy_file.format == 'yaml':
                import yaml
                with open(legacy_file.path) as f:
                    return yaml.safe_load(f)
            elif legacy_file.format == 'env':
                return self._load_env_config(legacy_file.path)
            else:
                raise ValueError(f"Unsupported format: {legacy_file.format}")
        except Exception as e:
            # Preserve original exception context
            raise ValueError(f"Failed to load {legacy_file.path}: {e}") from e

    def _load_python_config(self, file_path: Path) -> dict[str, Any]:
        """Load Python configuration file"""
        # Execute Python file in isolated namespace
        namespace = {}
        exec(file_path.read_text(), namespace)

        # Extract configuration variables (typically uppercase)
        config = {}
        for key, value in namespace.items():
            if key.isupper() and not key.startswith('_'):
                config[key.lower()] = value

        return config

    def _load_env_config(self, file_path: Path) -> dict[str, Any]:
        """Load environment configuration file"""
        config = {}
        content = file_path.read_text()

        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    # Convert common types
                    if value.lower() in ('true', 'false'):
                        value = value.lower() == 'true'
                    elif value.isdigit():
                        value = int(value)
                    elif re.match(r'^\d+\.\d+$', value):
                        value = float(value)

                    config[key.lower()] = value

        return config

    def _check_migration_conflicts(self, legacy_config: dict[str, Any], processed_types: set[str]) -> list[str]:
        """Check for migration conflicts"""
        conflicts = []

        # Check for overlapping configuration types
        config_keys = set(legacy_config.keys())
        overlapping_types = []

        type_mappings = {
            'database': ['db', 'database', 'postgres', 'mysql'],
            'gpu': ['gpu', 'cuda', 'nvidia'],
            'agents': ['agent', 'mcp', 'scout', 'analyst'],
            'crawling': ['crawl', 'news', 'scraper'],
            'monitoring': ['monitor', 'metrics', 'alert'],
            'security': ['security', 'auth', 'api'],
            'training': ['train', 'model', 'ml']
        }

        for config_type, keywords in type_mappings.items():
            if any(keyword in ' '.join(config_keys).lower() for keyword in keywords):
                if config_type in processed_types:
                    overlapping_types.append(config_type)

        if overlapping_types:
            conflicts.append(f"Configuration type overlap: {', '.join(overlapping_types)}")

        return conflicts

    def _merge_legacy_config(
        self,
        target_config: JustNewsConfig,
        legacy_config: dict[str, Any],
        config_type: str
    ) -> tuple[JustNewsConfig, list[str]]:
        """Merge legacy configuration into target config"""
        steps = []
        config_dict = target_config.model_dump()

        # Type-specific merging logic
        if config_type == 'database':
            steps.extend(self._merge_database_config(config_dict, legacy_config))
        elif config_type == 'gpu':
            steps.extend(self._merge_gpu_config(config_dict, legacy_config))
        elif config_type == 'agents':
            steps.extend(self._merge_agents_config(config_dict, legacy_config))
        elif config_type == 'crawling':
            steps.extend(self._merge_crawling_config(config_dict, legacy_config))
        elif config_type == 'monitoring':
            steps.extend(self._merge_monitoring_config(config_dict, legacy_config))
        elif config_type == 'security':
            steps.extend(self._merge_security_config(config_dict, legacy_config))
        elif config_type == 'training':
            steps.extend(self._merge_training_config(config_dict, legacy_config))
        else:
            # Generic merging
            self._generic_merge(config_dict, legacy_config)
            steps.append(f"Generic merge of {config_type} configuration")

        # Create new configuration
        try:
            new_config = JustNewsConfig(**config_dict)
            return new_config, steps
        except Exception as e:
            # Preserve source exception when failing to merge legacy config
            raise ValueError(f"Failed to merge {config_type} configuration: {e}") from e

    def _merge_database_config(self, config_dict: dict[str, Any], legacy: dict[str, Any]) -> list[str]:
        """Merge database configuration"""
        steps = []
        db_config = config_dict.setdefault('database', {})

        # Map common database keys
        key_mappings = {
            'host': ['host', 'hostname', 'server'],
            'port': ['port'],
            'database': ['database', 'db', 'name'],
            'user': ['user', 'username'],
            'password': ['password', 'pass', 'pwd'],
            'max_connections': ['max_connections', 'pool_size'],
            'connection_timeout': ['timeout', 'connect_timeout']
        }

        for target_key, source_keys in key_mappings.items():
            for source_key in source_keys:
                if source_key in legacy:
                    db_config[target_key] = legacy[source_key]
                    steps.append(f"Set database.{target_key} = {legacy[source_key]}")
                    break

        return steps

    def _merge_gpu_config(self, config_dict: dict[str, Any], legacy: dict[str, Any]) -> list[str]:
        """Merge GPU configuration"""
        steps = []
        gpu_config = config_dict.setdefault('gpu', {})

        # Map GPU keys
        if 'enabled' in legacy:
            gpu_config['enabled'] = legacy['enabled']
            steps.append(f"Set GPU enabled = {legacy['enabled']}")

        if 'devices' in legacy:
            gpu_config['devices'] = legacy['devices']
            steps.append("Set GPU devices configuration")

        if 'batch_size' in legacy:
            gpu_config['batch_size'] = legacy['batch_size']
            steps.append(f"Set GPU batch_size = {legacy['batch_size']}")

        return steps

    def _merge_agents_config(self, config_dict: dict[str, Any], legacy: dict[str, Any]) -> list[str]:
        """Merge agents configuration"""
        steps = []
        agents_config = config_dict.setdefault('agents', {})

        # Map agent ports
        port_mappings = {
            'mcp_bus_port': ['mcp_port', 'bus_port'],
            'chief_editor_port': ['chief_port', 'editor_port'],
            'scout_port': ['scout_port'],
            'analyst_port': ['analyst_port'],
            'fact_checker_port': ['fact_checker_port', 'checker_port'],
            'synthesizer_port': ['synthesizer_port', 'synth_port'],
            'critic_port': ['critic_port'],
            'memory_port': ['memory_port'],
            'reasoning_port': ['reasoning_port']
        }

        ports_config = agents_config.setdefault('ports', {})
        for target_key, source_keys in port_mappings.items():
            for source_key in source_keys:
                if source_key in legacy:
                    ports_config[target_key] = legacy[source_key]
                    steps.append(f"Set agents.ports.{target_key} = {legacy[source_key]}")
                    break

        return steps

    def _merge_crawling_config(self, config_dict: dict[str, Any], legacy: dict[str, Any]) -> list[str]:
        """Merge crawling configuration"""
        steps = []
        crawling_config = config_dict.setdefault('crawling', {})

        # Map crawling keys
        if 'enabled' in legacy:
            crawling_config['enabled'] = legacy['enabled']
            steps.append(f"Set crawling enabled = {legacy['enabled']}")

        if 'rate_limiting' in legacy:
            crawling_config['rate_limiting'] = legacy['rate_limiting']
            steps.append("Set crawling rate limiting")

        if 'user_agents' in legacy:
            crawling_config['user_agents'] = legacy['user_agents']
            steps.append("Set crawling user agents")

        return steps

    def _merge_monitoring_config(self, config_dict: dict[str, Any], legacy: dict[str, Any]) -> list[str]:
        """Merge monitoring configuration"""
        steps = []
        monitoring_config = config_dict.setdefault('monitoring', {})

        # Map monitoring keys
        if 'enabled' in legacy:
            monitoring_config['enabled'] = legacy['enabled']
            steps.append(f"Set monitoring enabled = {legacy['enabled']}")

        if 'metrics_enabled' in legacy:
            monitoring_config['metrics_enabled'] = legacy['metrics_enabled']
            steps.append(f"Set monitoring metrics_enabled = {legacy['metrics_enabled']}")

        return steps

    def _merge_security_config(self, config_dict: dict[str, Any], legacy: dict[str, Any]) -> list[str]:
        """Merge security configuration"""
        steps = []
        security_config = config_dict.setdefault('security', {})

        # Map security keys
        if 'api_key_required' in legacy:
            security_config['api_key_required'] = legacy['api_key_required']
            steps.append(f"Set security api_key_required = {legacy['api_key_required']}")

        if 'allowed_hosts' in legacy:
            security_config['allowed_hosts'] = legacy['allowed_hosts']
            steps.append("Set security allowed_hosts")

        return steps

    def _merge_training_config(self, config_dict: dict[str, Any], legacy: dict[str, Any]) -> list[str]:
        """Merge training configuration"""
        steps = []
        training_config = config_dict.setdefault('training', {})

        # Map training keys
        if 'enabled' in legacy:
            training_config['enabled'] = legacy['enabled']
            steps.append(f"Set training enabled = {legacy['enabled']}")

        if 'dataset_path' in legacy:
            training_config['dataset_path'] = legacy['dataset_path']
            steps.append(f"Set training dataset_path = {legacy['dataset_path']}")

        return steps

    def _generic_merge(self, config_dict: dict[str, Any], legacy: dict[str, Any]):
        """Generic configuration merging"""
        def deep_merge(target: dict[str, Any], source: dict[str, Any]):
            for key, value in source.items():
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    deep_merge(target[key], value)
                else:
                    target[key] = value

        deep_merge(config_dict, legacy)

    def _estimate_migration_effort(self, file_count: int, conflict_count: int, warning_count: int) -> str:
        """Estimate migration effort level"""
        score = file_count + (conflict_count * 2) + warning_count

        if score <= 5:
            return 'low'
        elif score <= 15:
            return 'medium'
        else:
            return 'high'

    def execute_migration(self, plan: MigrationPlan, backup: bool = True) -> ValidationResult:
        """
        Execute migration plan

        Args:
            plan: Migration plan to execute
            backup: Whether to backup legacy files

        Returns:
            ValidationResult: Migration execution results
        """
        start_time = datetime.now()
        errors = []
        warnings = []
        info = []

        try:
            # Validate target configuration
            validation = self.validator.validate(plan.target_config)
            if not validation.is_valid:
                errors.extend(validation.errors)
                return ValidationResult(
                    is_valid=False,
                    errors=errors,
                    warnings=warnings,
                    info=info,
                    duration_ms=(datetime.now() - start_time).total_seconds() * 1000
                )

            # Create backup if requested
            if backup:
                backup_dir = Path.cwd() / "config" / "legacy_backup" / start_time.strftime("%Y%m%d_%H%M%S")
                backup_dir.mkdir(parents=True, exist_ok=True)

                for legacy_file in plan.legacy_files:
                    if legacy_file.is_active:
                        backup_path = backup_dir / legacy_file.path.name
                        shutil.copy2(legacy_file.path, backup_path)
                        info.append(f"Backed up {legacy_file.path} to {backup_path}")

            # Save new unified configuration
            config_path = Path.cwd() / "config" / "system_config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)

            with open(config_path, 'w') as f:
                json.dump(plan.target_config.model_dump(), f, indent=2)

            info.append(f"Created unified configuration at {config_path}")
            info.extend(plan.migration_steps)

            # Report conflicts and warnings
            warnings.extend(plan.warnings)
            if plan.conflicts:
                errors.extend(plan.conflicts)

        except Exception as e:
            errors.append(f"Migration execution failed: {e}")

        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            info=info,
            duration_ms=duration_ms
        )

    def create_compatibility_layer(self, plan: MigrationPlan) -> str:
        """
        Create compatibility layer for gradual migration

        Args:
            plan: Migration plan

        Returns:
            str: Path to compatibility layer file
        """
        compatibility_code = self._generate_compatibility_code(plan)

        compat_file = Path.cwd() / "config" / "refactor" / "legacy" / "compatibility.py"
        compat_file.parent.mkdir(parents=True, exist_ok=True)

        with open(compat_file, 'w') as f:
            f.write(compatibility_code)

        logger.info(f"Created compatibility layer at {compat_file}")
        return str(compat_file)

    def _generate_compatibility_code(self, plan: MigrationPlan) -> str:
        """Generate compatibility layer code"""
        code_lines = [
            "# Legacy Configuration Compatibility Layer",
            "# Auto-generated for gradual migration",
            "",
            "import json",
            "import warnings",
            "from pathlib import Path",
            "from typing import Dict, Any",
            "",
            "from ..core import get_config",
            "",
            "",
            "class LegacyConfigCompat:",
            '    """Compatibility layer for legacy configuration access"""',
            "",
            "    def __init__(self):",
            "        self._config = get_config()",
            "        self._warned_keys = set()",
            "",
            "    def get_legacy_value(self, key_path: str, default: Any = None) -> Any:",
            '        """Get configuration value with legacy key mapping"""',
            "        # Map legacy keys to new configuration paths",
            "        key_mappings = {"
        ]

        # Add key mappings based on migration plan
        mappings = self._generate_key_mappings(plan)
        for legacy_key, new_path in mappings.items():
            code_lines.append(f'            "{legacy_key}": "{new_path}",')

        code_lines.extend([
            "        }",
            "",
            "        if key_path in key_mappings:",
            "            new_path = key_mappings[key_path]",
            "            if key_path not in self._warned_keys:",
            '                warnings.warn(',
            '                    f"Legacy config key \'{key_path}\' is deprecated. "',
            '                    f"Use \'{new_path}\' instead.",',
            "                    DeprecationWarning,",
            "                    stacklevel=2",
            "                )",
            "                self._warned_keys.add(key_path)",
            "            ",
            "            return self._config.get_nested_value(new_path)",
            "",
            "        return default",
            "",
            "",
            "# Global compatibility instance",
            "_compat = None",
            "",
            "def get_legacy_config():",
            '    """Get legacy configuration compatibility interface"""',
            "    global _compat",
            "    if _compat is None:",
            "        _compat = LegacyConfigCompat()",
            "    return _compat"
        ])

        return "\n".join(code_lines)

    def _generate_key_mappings(self, plan: MigrationPlan) -> dict[str, str]:
        """Generate key mappings for compatibility layer"""
        mappings = {}

        # Based on migration steps, create reverse mappings
        for step in plan.migration_steps:
            if "Set" in step:
                parts = step.split("Set ")[1].split(" = ")
                if len(parts) == 2:
                    config_path = parts[0]
                    # Create legacy-style key from config path
                    legacy_key = config_path.replace(".", "_").lower()
                    mappings[legacy_key] = config_path

        return mappings


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def discover_and_migrate_configs(
    target_environment: Environment = Environment.DEVELOPMENT,
    execute: bool = False,
    backup: bool = True
) -> tuple[MigrationPlan, ValidationResult | None]:
    """
    Discover legacy configurations and optionally execute migration

    Args:
        target_environment: Target environment for migration
        execute: Whether to execute the migration
        backup: Whether to backup legacy files

    Returns:
        Tuple[MigrationPlan, Optional[ValidationResult]]: Migration plan and execution result
    """
    migrator = LegacyConfigurationMigrator()

    # Discover legacy configurations
    migrator.discover_legacy_configs()

    # Create migration plan
    plan = migrator.create_migration_plan(target_environment)

    # Execute migration if requested
    result = None
    if execute:
        result = migrator.execute_migration(plan, backup)

    return plan, result

def create_legacy_compatibility_layer(plan: MigrationPlan) -> str:
    """
    Create compatibility layer for legacy configurations

    Args:
        plan: Migration plan

    Returns:
        str: Path to compatibility layer file
    """
    migrator = LegacyConfigurationMigrator()
    return migrator.create_compatibility_layer(plan)

# Export public API
__all__ = [
    'LegacyConfigFile',
    'MigrationPlan',
    'LegacyConfigurationMigrator',
    'discover_and_migrate_configs',
    'create_legacy_compatibility_layer'
]
