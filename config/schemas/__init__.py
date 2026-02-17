# JustNews Configuration Management - Unified Schema
# Phase 2B: Configuration Management Refactoring

"""
Unified Configuration Schema for JustNews

This module defines the complete type-safe configuration schema using Pydantic,
providing validation, environment abstraction, and centralized configuration management.

Key Features:
- Type-safe configuration with Pydantic validation
- Environment abstraction (dev/staging/production)
- Runtime configuration updates
- Comprehensive validation and error handling
- IDE support with auto-completion
"""

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic.types import NonNegativeInt, PositiveFloat, PositiveInt

# ============================================================================
# ENUMERATIONS
# ============================================================================


class Environment(str, Enum):
    """Environment types"""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(str, Enum):
    """Logging levels"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class CompressionAlgorithm(str, Enum):
    """Data compression algorithms"""

    GZIP = "gzip"
    LZ4 = "lz4"
    ZSTD = "zstd"
    NONE = "none"


class DatabaseSSLMode(str, Enum):
    """Database SSL modes (generic). Previously this enum was documented
    as Postgres-specific; the modes remain an abstract representation of
    TLS/SSL connection behavior applicable to MySQL/MariaDB and Postgres.
    """

    DISABLE = "disable"
    ALLOW = "allow"
    PREFER = "prefer"
    REQUIRE = "require"
    VERIFY_CA = "verify-ca"
    VERIFY_FULL = "verify-full"


# ============================================================================
# SYSTEM CONFIGURATION
# ============================================================================


class SystemConfig(BaseModel):
    """Core system configuration"""

    name: str = Field(default="JustNews", description="System name")
    version: str = Field(default="4.0", description="System version")
    environment: Environment = Field(
        default=Environment.DEVELOPMENT, description="Deployment environment"
    )
    log_level: LogLevel = Field(
        default=LogLevel.INFO, description="Default logging level"
    )
    debug_mode: bool = Field(default=False, description="Enable debug mode")
    conda_environment: str | None = Field(
        default=None, description="Conda environment name"
    )

    model_config = ConfigDict(use_enum_values=True)


# ============================================================================
# MCP BUS CONFIGURATION
# ============================================================================


class MCPBusConfig(BaseModel):
    """MCP Bus communication configuration"""

    host: str = Field(default="localhost", description="MCP Bus host")
    port: PositiveInt = Field(default=8000, description="MCP Bus port")
    url: str | None = Field(default=None, description="Full MCP Bus URL")
    timeout_seconds: PositiveFloat = Field(default=30.0, description="Request timeout")
    max_retries: NonNegativeInt = Field(default=3, description="Maximum retry attempts")
    retry_delay_seconds: PositiveFloat = Field(
        default=1.0, description="Delay between retries"
    )

    @model_validator(mode="before")
    def build_url(cls, values):
        """Auto-build URL from host and port if not provided"""
        if not values.get("url") and values.get("host") and values.get("port"):
            values["url"] = f"http://{values['host']}:{values['port']}"
        return values


# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================


class DatabaseConnectionPoolConfig(BaseModel):
    """Database connection pool settings"""

    min_connections: NonNegativeInt = Field(
        default=2, description="Minimum pool connections"
    )
    max_connections: PositiveInt = Field(
        default=10, description="Maximum pool connections"
    )
    connection_timeout_seconds: PositiveFloat = Field(
        default=3.0, description="Connection timeout"
    )
    command_timeout_seconds: PositiveFloat = Field(
        default=30.0, description="Command timeout"
    )


class DatabaseConfig(BaseModel):
    """Database configuration"""

    host: str = Field(default="localhost", description="Database host")
    port: PositiveInt = Field(
        default=3306, description="Database port (default: MariaDB 3306)"
    )
    database: str = Field(default="justnews", description="Database name")
    user: str = Field(default="justnews_user", description="Database user")
    password: str = Field(default="", description="Database password")
    connection_pool: DatabaseConnectionPoolConfig = Field(
        default_factory=DatabaseConnectionPoolConfig
    )
    ssl_mode: DatabaseSSLMode = Field(
        default=DatabaseSSLMode.PREFER, description="SSL mode"
    )

    model_config = ConfigDict(use_enum_values=True)


# ============================================================================
# CRAWLING CONFIGURATION
# ============================================================================


class CrawlingRateLimits(BaseModel):
    """Crawling rate limiting configuration"""

    requests_per_minute: PositiveInt = Field(
        default=20, description="Max requests per minute"
    )
    delay_between_requests_seconds: PositiveFloat = Field(
        default=2.0, description="Delay between requests"
    )
    concurrent_sites: PositiveInt = Field(
        default=3, description="Concurrent sites to crawl"
    )
    concurrent_browsers: PositiveInt = Field(
        default=3, description="Concurrent browser instances"
    )
    batch_size: PositiveInt = Field(default=10, description="Articles per batch")
    articles_per_site: PositiveInt = Field(
        default=25, description="Max articles per site"
    )
    max_total_articles: PositiveInt = Field(
        default=100, description="Total articles limit"
    )


class CrawlingTimeouts(BaseModel):
    """Crawling timeout settings"""

    page_load_timeout_seconds: PositiveInt = Field(
        default=120, description="Page load timeout"
    )
    modal_dismiss_timeout_ms: PositiveInt = Field(
        default=1000, description="Modal dismiss timeout"
    )
    request_timeout_seconds: PositiveInt = Field(
        default=30, description="Request timeout"
    )


class ConsentCookieConfig(BaseModel):
    """Synthetic consent cookie values."""

    name: str = Field(default="justnews_cookie_consent", min_length=1)
    value: str = Field(default="1", min_length=1)


class PaywallDetectorConfig(BaseModel):
    """Paywall detector configuration."""

    enable_remote_analysis: bool = Field(
        default=False, description="Delegate to Analyst agent"
    )
    max_remote_chars: PositiveInt = Field(
        default=6000, description="Max characters for remote analysis"
    )


class StealthProfileConfig(BaseModel):
    """Stealth browser profile configuration."""

    user_agent: str = Field(..., description="User agent string")
    accept_language: str = Field(
        default="en-US,en;q=0.9", description="Accept-Language header"
    )
    accept_encoding: str = Field(
        default="gzip, deflate, br", description="Accept-Encoding header"
    )
    headers: dict[str, str] = Field(
        default_factory=dict, description="Additional HTTP headers"
    )


class CrawlingEnhancementsConfig(BaseModel):
    """Optional enhancement toggles for the crawler."""

    enable_user_agent_rotation: bool = Field(
        default=False, description="Rotate user agents"
    )
    enable_proxy_pool: bool = Field(default=False, description="Use proxy pool")
    enable_modal_handler: bool = Field(
        default=False, description="Strip consent modals"
    )
    enable_paywall_detector: bool = Field(default=False, description="Detect paywalls")
    enable_stealth_headers: bool = Field(
        default=False, description="Apply stealth HTTP headers"
    )
    enable_pia_socks5: bool = Field(default=False, description="Use PIA SOCKS5 proxy")
    user_agent_pool: list[str] = Field(
        default_factory=list, description="User agent pool"
    )
    per_domain_user_agents: dict[str, list[str]] = Field(
        default_factory=dict, description="Domain specific user agents"
    )
    proxy_pool: list[str] = Field(default_factory=list, description="Proxy URLs")
    pia_socks5_username: str | None = Field(
        default=None, description="PIA SOCKS5 username"
    )
    pia_socks5_password: str | None = Field(
        default=None, description="PIA SOCKS5 password"
    )
    stealth_profiles: list[StealthProfileConfig] = Field(
        default_factory=list, description="Stealth header profiles"
    )
    consent_cookie: ConsentCookieConfig = Field(default_factory=ConsentCookieConfig)
    paywall_detector: PaywallDetectorConfig = Field(
        default_factory=PaywallDetectorConfig
    )


class CrawlingDelays(BaseModel):
    """Crawling delay settings"""

    between_batches_seconds: PositiveFloat = Field(
        default=0.5, description="Delay between batches"
    )
    between_requests_random_min: PositiveFloat = Field(
        default=1.0, description="Min random delay"
    )
    between_requests_random_max: PositiveFloat = Field(
        default=3.0, description="Max random delay"
    )


class CrawlingConfig(BaseModel):
    """Web crawling configuration"""

    enabled: bool = Field(default=True, description="Enable crawling")
    obey_robots_txt: bool = Field(default=True, description="Respect robots.txt")
    enhancements: CrawlingEnhancementsConfig = Field(
        default_factory=CrawlingEnhancementsConfig
    )
    respect_rate_limits: bool = Field(default=True, description="Respect rate limits")
    user_agent: str = Field(default="JustNews/4.0", description="HTTP user agent")
    robots_cache_hours: PositiveInt = Field(
        default=1, description="Robots.txt cache duration"
    )

    rate_limiting: CrawlingRateLimits = Field(default_factory=CrawlingRateLimits)
    timeouts: CrawlingTimeouts = Field(default_factory=CrawlingTimeouts)
    delays: CrawlingDelays = Field(default_factory=CrawlingDelays)


# ============================================================================
# GPU CONFIGURATION
# ============================================================================


class GPUDeviceLimits(BaseModel):
    """GPU device-specific limits"""

    memory_gb: PositiveFloat | None = Field(
        default=None, description="Memory limit in GB"
    )
    temperature_limits: dict[str, PositiveInt] = Field(
        default_factory=lambda: {"warning": 75, "critical": 85, "shutdown": 95},
        description="Temperature limits in Celsius",
    )


class GPUDevicesConfig(BaseModel):
    """GPU devices configuration"""

    preferred: list[NonNegativeInt] = Field(
        default_factory=lambda: [0], description="Preferred GPU devices"
    )
    excluded: list[NonNegativeInt] = Field(
        default_factory=list, description="Excluded GPU devices"
    )
    device_limits: dict[str, GPUDeviceLimits] = Field(
        default_factory=dict, description="Per-device limits"
    )


class GPUMemoryConfig(BaseModel):
    """GPU memory management configuration"""

    max_memory_per_agent_gb: PositiveFloat = Field(
        default=8.0, description="Max memory per agent"
    )
    safety_margin_percent: PositiveFloat = Field(
        default=15.0, description="Memory safety margin"
    )
    enable_cleanup: bool = Field(default=True, description="Enable memory cleanup")
    preallocation: bool = Field(default=False, description="Pre-allocate memory")


class GPUPerformanceConfig(BaseModel):
    """GPU performance configuration"""

    batch_size_optimization: bool = Field(
        default=True, description="Optimize batch sizes"
    )
    async_operations: bool = Field(default=True, description="Enable async operations")
    profiling_enabled: bool = Field(
        default=False, description="Enable performance profiling"
    )
    metrics_collection_interval_seconds: PositiveFloat = Field(
        default=10.0, description="Metrics interval"
    )


class GPUHealthConfig(BaseModel):
    """GPU health monitoring configuration"""

    enabled: bool = Field(default=True, description="Enable health monitoring")
    check_interval_seconds: PositiveFloat = Field(
        default=30.0, description="Health check interval"
    )
    temperature_limits: dict[str, PositiveInt] = Field(
        default_factory=lambda: {
            "warning_celsius": 75,
            "critical_celsius": 85,
            "shutdown_celsius": 95,
        },
        description="Temperature limits",
    )


class GPUConfig(BaseModel):
    """GPU configuration"""

    enabled: bool = Field(default=True, description="Enable GPU support")
    devices: GPUDevicesConfig = Field(default_factory=GPUDevicesConfig)
    memory_management: GPUMemoryConfig = Field(default_factory=GPUMemoryConfig)
    performance: GPUPerformanceConfig = Field(default_factory=GPUPerformanceConfig)
    health_monitoring: GPUHealthConfig = Field(default_factory=GPUHealthConfig)


# ============================================================================
# AGENT CONFIGURATION
# ============================================================================


class AgentTimeouts(BaseModel):
    """Agent timeout configuration"""

    agent_response_timeout_seconds: PositiveInt = Field(
        default=300, description="Agent response timeout"
    )
    health_check_timeout_seconds: PositiveInt = Field(
        default=10, description="Health check timeout"
    )


class AgentBatchSizes(BaseModel):
    """Agent batch size configuration"""

    scout_batch_size: PositiveInt = Field(default=10, description="Scout batch size")
    analyst_batch_size: PositiveInt = Field(
        default=16, description="Analyst batch size"
    )
    synthesizer_batch_size: PositiveInt = Field(
        default=8, description="Synthesizer batch size"
    )


class AgentPorts(BaseModel):
    """Agent port configuration"""

    scout: PositiveInt = Field(default=8002, description="Scout agent port")
    analyst: PositiveInt = Field(default=8004, description="Analyst agent port")
    fact_checker: PositiveInt = Field(
        default=8018, description="Fact checker agent port"
    )
    synthesizer: PositiveInt = Field(default=8005, description="Synthesizer agent port")
    critic: PositiveInt = Field(default=8006, description="Critic agent port")
    chief_editor: PositiveInt = Field(
        default=8001, description="Chief editor agent port"
    )
    memory: PositiveInt = Field(default=8007, description="Memory agent port")
    reasoning: PositiveInt = Field(default=8008, description="Reasoning agent port")
    dashboard: PositiveInt = Field(default=8013, description="Dashboard port")


class PublishingConfig(BaseModel):
    """Publishing and editorial workflow configuration"""

    require_draft_fact_check_pass_for_publish: bool = Field(default=False)
    chief_editor_review_required: bool = Field(default=True)
    allow_publish_override_by_agent: list[str] = Field(default_factory=list)


class AgentsConfig(BaseModel):
    """Agent configuration"""

    ports: AgentPorts = Field(default_factory=AgentPorts)
    timeouts: AgentTimeouts = Field(default_factory=AgentTimeouts)
    batch_sizes: AgentBatchSizes = Field(default_factory=AgentBatchSizes)
    publishing: PublishingConfig = Field(default_factory=PublishingConfig)


# ============================================================================
# TRAINING CONFIGURATION
# ============================================================================


class TrainingConfig(BaseModel):
    """ML training configuration"""

    enabled: bool = Field(default=True, description="Enable training")
    continuous_learning: bool = Field(
        default=True, description="Enable continuous learning"
    )
    ewc_lambda: PositiveFloat = Field(
        default=0.1, description="EWC regularization parameter"
    )
    learning_rate: PositiveFloat = Field(default=0.001, description="Learning rate")
    batch_size: PositiveInt = Field(default=32, description="Training batch size")
    epochs: PositiveInt = Field(default=10, description="Training epochs")
    validation_split: PositiveFloat = Field(
        default=0.2, description="Validation split ratio"
    )
    early_stopping_patience: PositiveInt = Field(
        default=5, description="Early stopping patience"
    )
    model_save_interval: PositiveInt = Field(
        default=100, description="Model save interval"
    )
    max_memory_samples: PositiveInt = Field(
        default=10000, description="Max memory samples"
    )


# ============================================================================
# SECURITY CONFIGURATION
# ============================================================================


class SecurityConfig(BaseModel):
    """Security configuration"""

    max_requests_per_minute: PositiveInt = Field(
        default=60, description="Rate limit per minute"
    )
    rate_limit_window_seconds: PositiveInt = Field(
        default=60, description="Rate limit window"
    )
    enable_ip_filtering: bool = Field(default=False, description="Enable IP filtering")
    allowed_ips: list[str] = Field(
        default_factory=list, description="Allowed IP addresses"
    )
    api_key_required: bool = Field(default=False, description="Require API key")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["*"], description="CORS allowed origins"
    )
    session_timeout_minutes: PositiveInt = Field(
        default=30, description="Session timeout"
    )


# ============================================================================
# MONITORING CONFIGURATION
# ============================================================================


class MonitoringAlertThresholds(BaseModel):
    """Monitoring alert thresholds"""

    cpu_usage_percent: PositiveInt = Field(
        default=90, description="CPU usage threshold"
    )
    memory_usage_percent: PositiveInt = Field(
        default=85, description="Memory usage threshold"
    )
    disk_usage_percent: PositiveInt = Field(
        default=90, description="Disk usage threshold"
    )
    gpu_memory_percent: PositiveInt = Field(
        default=90, description="GPU memory threshold"
    )
    gpu_temperature_celsius: PositiveInt = Field(
        default=85, description="GPU temperature threshold"
    )


class MonitoringEmailConfig(BaseModel):
    """Email alert configuration"""

    enabled: bool = Field(default=False, description="Enable email alerts")
    smtp_server: str | None = Field(default=None, description="SMTP server")
    smtp_port: PositiveInt = Field(default=587, description="SMTP port")
    recipients: list[str] = Field(default_factory=list, description="Email recipients")


class MonitoringLogConfig(BaseModel):
    """Log rotation configuration"""

    max_file_size_mb: PositiveInt = Field(default=100, description="Max log file size")
    backup_count: PositiveInt = Field(default=5, description="Number of backup files")


class MonitoringConfig(BaseModel):
    """Monitoring and alerting configuration"""

    enabled: bool = Field(default=True, description="Enable monitoring")
    metrics_collection_interval_seconds: PositiveInt = Field(
        default=60, description="Metrics interval"
    )
    alert_thresholds: MonitoringAlertThresholds = Field(
        default_factory=MonitoringAlertThresholds
    )
    alert_cooldown_minutes: PositiveInt = Field(default=5, description="Alert cooldown")
    email_alerts: MonitoringEmailConfig = Field(default_factory=MonitoringEmailConfig)
    log_rotation: MonitoringLogConfig = Field(default_factory=MonitoringLogConfig)


# ============================================================================
# DATA MANAGEMENT CONFIGURATION
# ============================================================================


class DataRetentionConfig(BaseModel):
    """Data retention policies"""

    articles: PositiveInt = Field(default=365, description="Article retention days")
    logs: PositiveInt = Field(default=90, description="Log retention days")
    metrics: PositiveInt = Field(default=30, description="Metrics retention days")
    cache: PositiveInt = Field(default=7, description="Cache retention days")


class DataCompressionConfig(BaseModel):
    """Data compression settings"""

    enabled: bool = Field(default=True, description="Enable compression")
    algorithm: CompressionAlgorithm = Field(
        default=CompressionAlgorithm.GZIP, description="Compression algorithm"
    )
    level: PositiveInt = Field(default=6, description="Compression level")


class DataAnonymizationConfig(BaseModel):
    """Data anonymization settings"""

    enabled: bool = Field(default=True, description="Enable anonymization")
    fields: list[str] = Field(
        default_factory=lambda: ["ip_address", "user_agent", "session_id"],
        description="Fields to anonymize",
    )


class DataMinimizationConfig(BaseModel):
    """Data minimization configuration"""

    enabled: bool = Field(default=True, description="Enable data minimization")
    retention_days: DataRetentionConfig = Field(default_factory=DataRetentionConfig)
    compression: DataCompressionConfig = Field(default_factory=DataCompressionConfig)
    anonymization: DataAnonymizationConfig = Field(
        default_factory=DataAnonymizationConfig
    )


# ============================================================================
# PERFORMANCE CONFIGURATION
# ============================================================================


class PerformanceCacheConfig(BaseModel):
    """Cache configuration"""

    enabled: bool = Field(default=True, description="Enable caching")
    ttl_seconds: PositiveInt = Field(default=3600, description="Cache TTL")
    max_size_mb: PositiveInt = Field(default=512, description="Max cache size")


class PerformanceConfig(BaseModel):
    """Performance optimization configuration"""

    optimization_level: str = Field(
        default="balanced", description="Optimization level"
    )
    memory_pool_size_mb: PositiveInt = Field(
        default=1024, description="Memory pool size"
    )
    thread_pool_size: PositiveInt = Field(default=10, description="Thread pool size")
    async_queue_size: PositiveInt = Field(default=1000, description="Async queue size")
    cache_settings: PerformanceCacheConfig = Field(
        default_factory=PerformanceCacheConfig
    )


# ============================================================================
# EXTERNAL SERVICES CONFIGURATION
# ============================================================================


class ExternalNewsSourcesConfig(BaseModel):
    """External news sources configuration"""

    verification_required: bool = Field(
        default=True, description="Require source verification"
    )
    max_age_days: PositiveInt = Field(default=30, description="Max source age")
    auto_discovery: bool = Field(default=False, description="Enable auto-discovery")


class ExternalAPIsConfig(BaseModel):
    """External API configuration"""

    timeout_seconds: PositiveInt = Field(default=10, description="API timeout")
    retry_attempts: NonNegativeInt = Field(default=3, description="Retry attempts")
    rate_limit_per_minute: PositiveInt = Field(
        default=100, description="Rate limit per minute"
    )


class ExternalServicesConfig(BaseModel):
    """External services configuration"""

    news_sources: ExternalNewsSourcesConfig = Field(
        default_factory=ExternalNewsSourcesConfig
    )
    apis: ExternalAPIsConfig = Field(default_factory=ExternalAPIsConfig)


# ============================================================================
# PUBLISHING CONFIGURATION
# ============================================================================


# PublishingConfig defined earlier to avoid forward reference issues


# ============================================================================
# MAIN CONFIGURATION SCHEMA
# ============================================================================


class JustNewsConfig(BaseModel):
    """Complete JustNews configuration schema"""

    system: SystemConfig = Field(default_factory=SystemConfig)
    mcp_bus: MCPBusConfig = Field(default_factory=MCPBusConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    crawling: CrawlingConfig = Field(default_factory=CrawlingConfig)
    gpu: GPUConfig = Field(default_factory=GPUConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    data_minimization: DataMinimizationConfig = Field(
        default_factory=DataMinimizationConfig
    )
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    external_services: ExternalServicesConfig = Field(
        default_factory=ExternalServicesConfig
    )

    model_config = ConfigDict(validate_assignment=True, use_enum_values=True)

    @field_validator("system")
    def validate_environment_consistency(cls, v, values):
        """Validate environment-specific constraints"""
        if v.environment == Environment.PRODUCTION:
            # Production-specific validations
            if not values.get("database", DatabaseConfig()).password:
                raise ValueError("Database password required in production")
            if values.get("system", SystemConfig()).debug_mode:
                raise ValueError("Debug mode must be disabled in production")
        return v

    def get_nested_value(self, key_path: str) -> Any:
        """Get nested configuration value using dot notation"""
        keys = key_path.split(".")
        current = self

        try:
            for key in keys:
                current = getattr(current, key)
            return current
        except AttributeError as exc:
            # Chain the AttributeError for clearer tracebacks
            raise KeyError(f"Configuration key not found: {key_path}") from exc

    def set_nested_value(self, key_path: str, value: Any):
        """Set nested configuration value using dot notation"""
        keys = key_path.split(".")
        current = self

        for key in keys[:-1]:
            if not hasattr(current, key):
                raise KeyError(
                    f"Invalid configuration path: {'.'.join(keys[: keys.index(key) + 1])}"
                )
            current = getattr(current, key)

        if not hasattr(current, keys[-1]):
            raise KeyError(f"Configuration key not found: {key_path}")

        setattr(current, keys[-1], value)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def load_config_from_file(file_path: str | Path) -> JustNewsConfig:
    """Load configuration from JSON file"""
    import json

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    with open(file_path) as f:
        data = json.load(f)

    return JustNewsConfig(**data)


def save_config_to_file(config: JustNewsConfig, file_path: str | Path):
    """Save configuration to JSON file"""
    import json

    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "w") as f:
        json.dump(config.model_dump(), f, indent=2, default=str)


def create_default_config() -> JustNewsConfig:
    """Create default configuration"""
    return JustNewsConfig()


def merge_configs(base: JustNewsConfig, override: JustNewsConfig) -> JustNewsConfig:
    """Merge two configurations with override taking precedence"""
    # This would implement deep merging logic
    # For now, return the override config
    return override


# Export public API
__all__ = [
    "JustNewsConfig",
    "Environment",
    "SystemConfig",
    "MCPBusConfig",
    "DatabaseConfig",
    "CrawlingConfig",
    "GPUConfig",
    "AgentsConfig",
    "TrainingConfig",
    "SecurityConfig",
    "MonitoringConfig",
    "DataMinimizationConfig",
    "PerformanceConfig",
    "ExternalServicesConfig",
    "LogLevel",
    "CompressionAlgorithm",
    "DatabaseSSLMode",
    "load_config_from_file",
    "save_config_to_file",
    "create_default_config",
    "merge_configs",
]
