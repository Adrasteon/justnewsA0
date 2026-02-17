#!/usr/bin/env python3
"""
Configuration Quick Reference and Management Script

This script provides easy access to view, modify, and manage the centralized
JustNews configuration. Use this to quickly check current settings and
make adjustments without editing the JSON file directly.
"""

import sys
from pathlib import Path

# Add config directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from system_config import config
except ImportError:
    print("❌ Could not import configuration system")
    print("Make sure you're running from the config directory")
    sys.exit(1)


def print_section_header(title: str):
    """Print a formatted section header"""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}")


def print_crawling_config():
    """Display crawling configuration"""
    print_section_header("🤖 CRAWLING CONFIGURATION")

    crawling = config.get_section("crawling")
    rate_limits = crawling.get("rate_limiting", {})

    print("General Settings:")
    print(f"  • Enabled: {crawling.get('enabled', False)}")
    print(f"  • Obey Robots.txt: {crawling.get('obey_robots_txt', False)}")
    print(f"  • Respect Rate Limits: {crawling.get('respect_rate_limits', False)}")
    print(f"  • User Agent: {crawling.get('user_agent', 'Not set')}")
    print(f"  • Robots Cache (hours): {crawling.get('robots_cache_hours', 0)}")

    print("\nRate Limiting:")
    print(f"  • Requests per Minute: {rate_limits.get('requests_per_minute', 0)}")
    print(
        f"  • Delay Between Requests: {rate_limits.get('delay_between_requests_seconds', 0)}s"
    )
    print(f"  • Concurrent Sites: {rate_limits.get('concurrent_sites', 0)}")
    print(f"  • Concurrent Browsers: {rate_limits.get('concurrent_browsers', 0)}")
    print(f"  • Batch Size: {rate_limits.get('batch_size', 0)}")
    print(f"  • Articles per Site: {rate_limits.get('articles_per_site', 0)}")
    print(f"  • Max Total Articles: {rate_limits.get('max_total_articles', 0)}")

    print("\nTimeouts:")
    timeouts = crawling.get("timeouts", {})
    print(f"  • Page Load: {timeouts.get('page_load_timeout_seconds', 0)}ms")
    print(f"  • Modal Dismiss: {timeouts.get('modal_dismiss_timeout_ms', 0)}ms")
    print(f"  • Request: {timeouts.get('request_timeout_seconds', 0)}s")


def print_database_config():
    """Display database configuration"""
    print_section_header("🗄️ DATABASE CONFIGURATION")

    db = config.get_section("database")
    pool = db.get("connection_pool", {})

    print("Connection Settings:")
    print(f"  • Host: {db.get('host', 'Not set')}")
    print(f"  • Port: {db.get('port', 0)}")
    print(f"  • Database: {db.get('database', 'Not set')}")
    print(f"  • User: {db.get('user', 'Not set')}")
    print(
        f"  • Password: {'*' * len(db.get('password', '')) if db.get('password') else 'Not set'}"
    )
    print(f"  • SSL Mode: {db.get('ssl_mode', 'Not set')}")

    print("\nConnection Pool:")
    print(f"  • Min Connections: {pool.get('min_connections', 0)}")
    print(f"  • Max Connections: {pool.get('max_connections', 0)}")
    print(f"  • Connection Timeout: {pool.get('connection_timeout_seconds', 0)}s")
    print(f"  • Command Timeout: {pool.get('command_timeout_seconds', 0)}s")


def print_gpu_config():
    """Display GPU configuration"""
    print_section_header("🎮 GPU CONFIGURATION")

    gpu = config.get_section("gpu")
    devices = gpu.get("devices", {})
    memory = gpu.get("memory_management", {})
    health = gpu.get("health_monitoring", {})

    print("General Settings:")
    print(f"  • Enabled: {gpu.get('enabled', False)}")
    print(f"  • Preferred Devices: {devices.get('preferred', [])}")
    print(f"  • Excluded Devices: {devices.get('excluded', [])}")

    print("\nMemory Management:")
    print(f"  • Max Memory per Agent: {memory.get('max_memory_per_agent_gb', 0)}GB")
    print(f"  • Safety Margin: {memory.get('safety_margin_percent', 0)}%")
    print(f"  • Enable Cleanup: {memory.get('enable_cleanup', False)}")
    print(f"  • Preallocation: {memory.get('preallocation', False)}")

    print("\nPerformance:")
    perf = gpu.get("performance", {})
    print(f"  • Batch Size Optimization: {perf.get('batch_size_optimization', False)}")
    print(f"  • Async Operations: {perf.get('async_operations', False)}")
    print(f"  • Profiling Enabled: {perf.get('profiling_enabled', False)}")
    print(
        f"  • Metrics Interval: {perf.get('metrics_collection_interval_seconds', 0)}s"
    )

    print("\nHealth Monitoring:")
    print(f"  • Enabled: {health.get('enabled', False)}")
    print(f"  • Check Interval: {health.get('check_interval_seconds', 0)}s")
    temp_limits = health.get("temperature_limits", {})
    print(f"  • Warning Temperature: {temp_limits.get('warning_celsius', 0)}°C")
    print(f"  • Critical Temperature: {temp_limits.get('critical_celsius', 0)}°C")
    print(f"  • Shutdown Temperature: {temp_limits.get('shutdown_celsius', 0)}°C")


def print_system_config():
    """Display system configuration"""
    print_section_header("⚙️ SYSTEM CONFIGURATION")

    system = config.get_section("system")
    mcp = config.get_section("mcp_bus")

    print("System Info:")
    print(f"  • Name: {system.get('name', 'Not set')}")
    print(f"  • Version: {system.get('version', 'Not set')}")
    print(f"  • Environment: {system.get('environment', 'Not set')}")
    print(f"  • Log Level: {system.get('log_level', 'Not set')}")
    print(f"  • Debug Mode: {system.get('debug_mode', False)}")

    print("\nMCP Bus:")
    print(f"  • Host: {mcp.get('host', 'Not set')}")
    print(f"  • Port: {mcp.get('port', 0)}")
    print(f"  • URL: {mcp.get('url', 'Not set')}")
    print(f"  • Timeout: {mcp.get('timeout_seconds', 0)}s")
    print(f"  • Max Retries: {mcp.get('max_retries', 0)}")
    print(f"  • Retry Delay: {mcp.get('retry_delay_seconds', 0)}s")


def print_agent_ports():
    """Display agent port configuration"""
    print_section_header("🔌 AGENT PORTS")

    agents = config.get_section("agents")
    ports = agents.get("ports", {})

    print("Agent Services:")
    for agent, port in ports.items():
        print(f"  • {agent.replace('_', ' ').title()}: {port}")

    print("\nTimeouts:")
    timeouts = agents.get("timeouts", {})
    print(f"  • Agent Response: {timeouts.get('agent_response_timeout_seconds', 0)}s")
    print(f"  • Health Check: {timeouts.get('health_check_timeout_seconds', 0)}s")


def print_monitoring_config():
    """Display monitoring configuration"""
    print_section_header("📊 MONITORING CONFIGURATION")

    monitoring = config.get_section("monitoring")
    alerts = monitoring.get("alert_thresholds", {})

    print("General Settings:")
    print(f"  • Enabled: {monitoring.get('enabled', False)}")
    print(
        f"  • Metrics Interval: {monitoring.get('metrics_collection_interval_seconds', 0)}s"
    )
    print(f"  • Alert Cooldown: {monitoring.get('alert_cooldown_minutes', 0)} minutes")

    print("\nAlert Thresholds:")
    print(f"  • CPU Usage: {alerts.get('cpu_usage_percent', 0)}%")
    print(f"  • Memory Usage: {alerts.get('memory_usage_percent', 0)}%")
    print(f"  • Disk Usage: {alerts.get('disk_usage_percent', 0)}%")
    print(f"  • GPU Memory: {alerts.get('gpu_memory_percent', 0)}%")
    print(f"  • GPU Temperature: {alerts.get('gpu_temperature_celsius', 0)}°C")


def show_usage_examples():
    """Show usage examples"""
    print_section_header("📚 USAGE EXAMPLES")

    print("Python Code Examples:")
    print("# Import configuration")
    print("from config.system_config import config")
    print("")
    print("# Get crawling settings")
    print("crawl_config = config.get('crawling')")
    print("rpm = config.get('crawling.rate_limiting.requests_per_minute')")
    print("")
    print("# Get database settings")
    print("db_config = config.get('database')")
    print("db_host = config.get('database.host')")
    print("")
    print("# Check if GPU is enabled")
    print("gpu_enabled = config.get('gpu.enabled')")
    print("")
    print("# Environment Variables (override config):")
    print("export CRAWLER_REQUESTS_PER_MINUTE=15")
    print("export MARIADB_HOST=your-db-host")
    print("export LOG_LEVEL=DEBUG")


def main():
    """Main function"""
    print("🎯 JustNews Configuration Quick Reference")
    print(f"📁 Config File: {config.config_file}")

    # Display all sections
    print_system_config()
    print_crawling_config()
    print_database_config()
    print_gpu_config()
    print_agent_ports()
    print_monitoring_config()
    show_usage_examples()

    print_section_header("✅ CONFIGURATION LOADED")
    print(f"Total configuration sections: {len(list(config.keys()))}")
    print("Use 'python config/validate_config.py' to validate configuration")


if __name__ == "__main__":
    main()
