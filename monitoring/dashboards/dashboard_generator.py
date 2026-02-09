"""
Dashboard Generator for JustNews Monitoring System

This module provides automated dashboard creation and configuration for the
JustNews observability platform. It generates Grafana dashboards,
Prometheus alerting rules, and custom visualizations for comprehensive
monitoring and alerting.

Author: JustNews Development Team
Date: October 22, 2025
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Configure logging
logger = logging.getLogger(__name__)


class DashboardConfig(BaseModel):
    """Configuration for dashboard generation"""

    title: str = Field(..., description="Dashboard title")
    description: str | None = Field(None, description="Dashboard description")
    tags: list[str] = Field(default_factory=list, description="Dashboard tags")
    refresh: str = Field("30s", description="Dashboard refresh interval")
    time_range: str = Field("1h", description="Default time range")
    timezone: str = Field("timezone.utc", description="Dashboard timezone")

    @field_validator("refresh")
    @classmethod
    def validate_refresh(cls, v):
        """Validate refresh interval format"""
        valid_intervals = [
            "5s",
            "10s",
            "30s",
            "1m",
            "5m",
            "15m",
            "30m",
            "1h",
            "2h",
            "1d",
        ]
        if v not in valid_intervals:
            raise ValueError(f"Refresh interval must be one of: {valid_intervals}")
        return v


class PanelConfig(BaseModel):
    """Configuration for individual dashboard panels"""

    title: str = Field(..., description="Panel title")
    type: str = Field(..., description="Panel type (graph, table, heatmap, etc.)")
    targets: list[dict[str, Any]] = Field(
        default_factory=list, description="Prometheus targets"
    )
    grid_pos: dict[str, int] = Field(..., description="Grid position (h, w, x, y)")
    description: str | None = Field(None, description="Panel description")
    options: dict[str, Any] = Field(
        default_factory=dict, description="Panel-specific options"
    )


class DashboardTemplate(BaseModel):
    """Template for dashboard generation"""

    name: str = Field(..., description="Template name")
    config: DashboardConfig = Field(..., description="Dashboard configuration")
    panels: list[PanelConfig] = Field(
        default_factory=list, description="Dashboard panels"
    )
    variables: list[dict[str, Any]] = Field(
        default_factory=list, description="Template variables"
    )
    annotations: list[dict[str, Any]] = Field(
        default_factory=list, description="Dashboard annotations"
    )


@dataclass
class DashboardGenerator:
    """
    Automated dashboard generator for JustNews monitoring system.

    This class provides methods to generate Grafana dashboards, Prometheus
    alerting rules, and custom visualizations based on system metrics and
    business requirements.
    """

    # Dashboard templates
    templates: dict[str, DashboardTemplate] = field(default_factory=dict)

    # Output directory for generated dashboards
    output_dir: Path = field(
        default_factory=lambda: Path("monitoring/dashboards/generated")
    )

    # Grafana API configuration
    grafana_url: str = field(default="http://localhost:3000")
    grafana_api_key: str | None = field(default=None)

    def __post_init__(self):
        """Initialize dashboard generator"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._load_default_templates()

    def _load_default_templates(self):
        """Load default dashboard templates"""
        self.templates.update(
            {
                "system_overview": self._create_system_overview_template(),
                "agent_performance": self._create_agent_performance_template(),
                "content_quality": self._create_content_quality_template(),
                "security_monitoring": self._create_security_monitoring_template(),
                "business_metrics": self._create_business_metrics_template(),
            }
        )

    def _create_system_overview_template(self) -> DashboardTemplate:
        """Create system overview dashboard template"""
        return DashboardTemplate(
            name="system_overview",
            config=DashboardConfig(
                title="JustNews System Overview",
                description="Comprehensive system health and performance monitoring",
                tags=["system", "overview", "health"],
                refresh="30s",
                time_range="1h",
            ),
            panels=[
                PanelConfig(
                    title="System CPU Usage",
                    type="graph",
                    targets=[
                        {
                            "expr": '100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
                            "legendFormat": "{{instance}}",
                        }
                    ],
                    grid_pos={"h": 8, "w": 12, "x": 0, "y": 0},
                    description="CPU usage across all system instances",
                ),
                PanelConfig(
                    title="System Memory Usage",
                    type="graph",
                    targets=[
                        {
                            "expr": "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100",
                            "legendFormat": "{{instance}}",
                        }
                    ],
                    grid_pos={"h": 8, "w": 12, "x": 12, "y": 0},
                    description="Memory usage percentage across all instances",
                ),
                PanelConfig(
                    title="Active Agents",
                    type="stat",
                    targets=[
                        {"expr": 'up{job=~"justnews-.*"}', "legendFormat": "{{job}}"}
                    ],
                    grid_pos={"h": 4, "w": 8, "x": 0, "y": 8},
                    description="Number of active JustNews services",
                ),
                PanelConfig(
                    title="MCP Bus Requests",
                    type="graph",
                    targets=[
                        {
                            "expr": "rate(mcp_bus_requests_total[5m])",
                            "legendFormat": "Requests/sec",
                        }
                    ],
                    grid_pos={"h": 8, "w": 16, "x": 8, "y": 8},
                    description="MCP Bus request rate over time",
                ),
                PanelConfig(
                    title="Adaptive Articles Produced",
                    type="stat",
                    targets=[
                        {
                            "expr": "justnews_crawler_scheduler_adaptive_articles_total",
                            "legendFormat": "Adaptive Articles",
                        }
                    ],
                    grid_pos={"h": 4, "w": 6, "x": 0, "y": 16},
                    description="Adaptive Crawl4AI article output for the latest scheduler window",
                ),
                PanelConfig(
                    title="Adaptive Sufficiency Rate",
                    type="stat",
                    targets=[
                        {
                            "expr": "justnews_crawler_scheduler_adaptive_articles_sufficient_total / clamp_min(justnews_crawler_scheduler_adaptive_articles_total, 1) * 100",
                            "legendFormat": "Sufficient %",
                        }
                    ],
                    grid_pos={"h": 4, "w": 6, "x": 6, "y": 16},
                    description="Percentage of adaptive articles meeting sufficiency criteria",
                ),
                PanelConfig(
                    title="Adaptive Confidence Average",
                    type="stat",
                    targets=[
                        {
                            "expr": "justnews_crawler_scheduler_adaptive_confidence_average",
                            "legendFormat": "Confidence",
                        }
                    ],
                    grid_pos={"h": 4, "w": 6, "x": 12, "y": 16},
                    description="Average model confidence emitted by adaptive runs",
                ),
                PanelConfig(
                    title="Adaptive Pages per Article",
                    type="stat",
                    targets=[
                        {
                            "expr": "justnews_crawler_scheduler_adaptive_pages_crawled_average",
                            "legendFormat": "Pages",
                        }
                    ],
                    grid_pos={"h": 4, "w": 6, "x": 18, "y": 16},
                    description="Average Crawl4AI pages crawled per adaptive article",
                ),
                PanelConfig(
                    title="Adaptive Stop Reasons",
                    type="bargauge",
                    targets=[
                        {
                            "expr": "sum by(reason) (justnews_crawler_scheduler_adaptive_stop_reasons_total)",
                            "legendFormat": "{{reason}}",
                        }
                    ],
                    grid_pos={"h": 8, "w": 24, "x": 0, "y": 20},
                    description="Distribution of adaptive stop reasons captured by the scheduler",
                ),
            ],
            variables=[
                {
                    "name": "instance",
                    "label": "Instance",
                    "type": "query",
                    "query": "label_values(up, instance)",
                    "multi": True,
                }
            ],
        )

    def _create_agent_performance_template(self) -> DashboardTemplate:
        """Create agent performance dashboard template"""
        return DashboardTemplate(
            name="agent_performance",
            config=DashboardConfig(
                title="Agent Performance Dashboard",
                description="Detailed performance metrics for all JustNews services",
                tags=["agents", "performance", "monitoring"],
                refresh="15m",
                time_range="30m",
            ),
            panels=[
                PanelConfig(
                    title="Agent Response Times",
                    type="graph",
                    targets=[
                        {
                            "expr": "histogram_quantile(0.95, rate(agent_request_duration_seconds_bucket[5m]))",
                            "legendFormat": "{{agent}} P95",
                        }
                    ],
                    grid_pos={"h": 8, "w": 16, "x": 0, "y": 0},
                    description="95th percentile response times by agent",
                ),
                PanelConfig(
                    title="Agent Throughput",
                    type="graph",
                    targets=[
                        {
                            "expr": "rate(agent_requests_total[5m])",
                            "legendFormat": "{{agent}} req/sec",
                        }
                    ],
                    grid_pos={"h": 8, "w": 16, "x": 0, "y": 8},
                    description="Request throughput by agent",
                ),
                PanelConfig(
                    title="Agent Error Rates",
                    type="graph",
                    targets=[
                        {
                            "expr": "rate(agent_errors_total[5m]) / rate(agent_requests_total[5m]) * 100",
                            "legendFormat": "{{agent}} error %",
                        }
                    ],
                    grid_pos={"h": 8, "w": 16, "x": 0, "y": 16},
                    description="Error rates by agent as percentage",
                ),
                PanelConfig(
                    title="GPU Memory Usage",
                    type="graph",
                    targets=[
                        {
                            "expr": "gpu_memory_used_bytes / gpu_memory_total_bytes * 100",
                            "legendFormat": "{{gpu}} {{agent}}",
                        }
                    ],
                    grid_pos={"h": 8, "w": 12, "x": 0, "y": 24},
                    description="GPU memory utilization by agent",
                ),
                PanelConfig(
                    title="Agent Health Status",
                    type="table",
                    targets=[
                        {"expr": 'up{job=~"justnews-.*"}', "legendFormat": "{{job}}"}
                    ],
                    grid_pos={"h": 6, "w": 12, "x": 12, "y": 24},
                    description="Current health status of all agents",
                ),
            ],
        )

    def _create_content_quality_template(self) -> DashboardTemplate:
        """Create content quality dashboard template"""
        return DashboardTemplate(
            name="content_quality",
            config=DashboardConfig(
                title="Content Quality Dashboard",
                description="News content quality metrics and analysis",
                tags=["content", "quality", "news"],
                refresh="1m",
                time_range="6h",
            ),
            panels=[
                PanelConfig(
                    title="Content Accuracy Score",
                    type="graph",
                    targets=[
                        {
                            "expr": "content_accuracy_score",
                            "legendFormat": "Accuracy Score",
                        }
                    ],
                    grid_pos={"h": 8, "w": 12, "x": 0, "y": 0},
                    description="Content accuracy scores over time",
                ),
                PanelConfig(
                    title="Fact-Checking Results",
                    type="stat",
                    targets=[
                        {
                            "expr": "fact_check_passed_total / (fact_check_passed_total + fact_check_failed_total) * 100",
                            "legendFormat": "Pass Rate %",
                        }
                    ],
                    grid_pos={"h": 4, "w": 6, "x": 12, "y": 0},
                    description="Percentage of articles passing fact-checking",
                ),
                PanelConfig(
                    title="Bias Detection Scores",
                    type="heatmap",
                    targets=[
                        {"expr": "content_bias_score", "legendFormat": "Bias Score"}
                    ],
                    grid_pos={"h": 8, "w": 12, "x": 0, "y": 8},
                    description="Content bias detection heatmap",
                ),
                PanelConfig(
                    title="Content Processing Rate",
                    type="graph",
                    targets=[
                        {
                            "expr": "rate(content_processed_total[5m])",
                            "legendFormat": "Articles/min",
                        }
                    ],
                    grid_pos={"h": 8, "w": 12, "x": 12, "y": 8},
                    description="Rate of content processing",
                ),
            ],
        )

    def _create_security_monitoring_template(self) -> DashboardTemplate:
        """Create security monitoring dashboard template"""
        return DashboardTemplate(
            name="security_monitoring",
            config=DashboardConfig(
                title="Security Monitoring Dashboard",
                description="Security events, threats, and compliance monitoring",
                tags=["security", "monitoring", "compliance"],
                refresh="30s",
                time_range="24h",
            ),
            panels=[
                PanelConfig(
                    title="Security Events",
                    type="graph",
                    targets=[
                        {
                            "expr": "rate(security_events_total[5m])",
                            "legendFormat": "{{type}}",
                        }
                    ],
                    grid_pos={"h": 8, "w": 16, "x": 0, "y": 0},
                    description="Security events by type",
                ),
                PanelConfig(
                    title="Failed Authentication Attempts",
                    type="graph",
                    targets=[
                        {
                            "expr": "rate(auth_failures_total[5m])",
                            "legendFormat": "Failures",
                        }
                    ],
                    grid_pos={"h": 6, "w": 8, "x": 0, "y": 8},
                    description="Authentication failure rate",
                ),
                PanelConfig(
                    title="Active Security Alerts",
                    type="stat",
                    targets=[
                        {
                            "expr": "security_alerts_active",
                            "legendFormat": "Active Alerts",
                        }
                    ],
                    grid_pos={"h": 6, "w": 8, "x": 8, "y": 8},
                    description="Number of active security alerts",
                ),
                PanelConfig(
                    title="Compliance Violations",
                    type="table",
                    targets=[
                        {
                            "expr": "compliance_violations_total",
                            "legendFormat": "{{regulation}}",
                        }
                    ],
                    grid_pos={"h": 8, "w": 16, "x": 0, "y": 14},
                    description="Compliance violations by regulation",
                ),
            ],
        )

    def _create_business_metrics_template(self) -> DashboardTemplate:
        """Create business metrics dashboard template"""
        return DashboardTemplate(
            name="business_metrics",
            config=DashboardConfig(
                title="Business Metrics Dashboard",
                description="Key business performance indicators and KPIs",
                tags=["business", "kpi", "metrics"],
                refresh="5m",
                time_range="7d",
            ),
            panels=[
                PanelConfig(
                    title="Daily Active Users",
                    type="graph",
                    targets=[{"expr": "daily_active_users", "legendFormat": "DAU"}],
                    grid_pos={"h": 8, "w": 12, "x": 0, "y": 0},
                    description="Daily active user count",
                ),
                PanelConfig(
                    title="Content Engagement",
                    type="graph",
                    targets=[
                        {
                            "expr": "content_engagement_score",
                            "legendFormat": "Engagement",
                        }
                    ],
                    grid_pos={"h": 8, "w": 12, "x": 12, "y": 0},
                    description="Content engagement metrics",
                ),
                PanelConfig(
                    title="Revenue Metrics",
                    type="stat",
                    targets=[
                        {"expr": "revenue_total", "legendFormat": "Total Revenue"}
                    ],
                    grid_pos={"h": 4, "w": 8, "x": 0, "y": 8},
                    description="Total revenue generated",
                ),
                PanelConfig(
                    title="Customer Satisfaction",
                    type="gauge",
                    targets=[
                        {"expr": "customer_satisfaction_score", "legendFormat": "CSAT"}
                    ],
                    grid_pos={"h": 6, "w": 8, "x": 8, "y": 8},
                    description="Customer satisfaction score",
                ),
                PanelConfig(
                    title="Market Share",
                    type="bargauge",
                    targets=[
                        {
                            "expr": "market_share_percentage",
                            "legendFormat": "{{segment}}",
                        }
                    ],
                    grid_pos={"h": 8, "w": 16, "x": 0, "y": 14},
                    description="Market share by segment",
                ),
            ],
        )

    def _create_otel_collectors_template(self) -> DashboardTemplate:
        """Create OpenTelemetry collector health dashboard template"""
        # NOTE: This template is intentionally not registered by default while OTEL metrics are disabled
        # (Nov 2025). Re-add it via add_template() once the metrics pipeline returns.
        # Surface the key OTEL pipeline stages so ops can spot back pressure quickly.
        return DashboardTemplate(
            name="otel_collectors",
            config=DashboardConfig(
                title="OpenTelemetry Collectors",
                description="Health and throughput metrics for the node and central OTEL collectors",
                tags=["otel", "collectors", "monitoring"],
                refresh="30s",
                time_range="30m",
            ),
            panels=[
                PanelConfig(
                    title="Collector Target Status",
                    type="table",
                    targets=[
                        {
                            "expr": 'up{job="justnews-otel-collectors"}',
                            "legendFormat": "{{instance}}",
                        }
                    ],
                    grid_pos={"h": 6, "w": 8, "x": 0, "y": 0},
                    description="Target availability for each OTEL collector scrape endpoint",
                ),
                PanelConfig(
                    title="Receiver Accepted Rate",
                    type="graph",
                    targets=[
                        {
                            "expr": 'sum by(instance) (rate(otelcol_receiver_accepted_metric_points{job="justnews-otel-collectors"}[5m]))',
                            "legendFormat": "{{instance}} accepted",
                        }
                    ],
                    grid_pos={"h": 8, "w": 16, "x": 8, "y": 0},
                    description="Incoming OTLP metrics successfully accepted by each collector",
                ),
                PanelConfig(
                    title="Receiver Refused Rate",
                    type="graph",
                    targets=[
                        {
                            "expr": 'sum by(instance) (rate(otelcol_receiver_refused_metric_points{job="justnews-otel-collectors"}[5m]))',
                            "legendFormat": "{{instance}} refused",
                        }
                    ],
                    grid_pos={"h": 8, "w": 8, "x": 0, "y": 6},
                    description="Drop or refusal rate from the collector receivers",
                ),
                PanelConfig(
                    title="Exporter Queue Size",
                    type="graph",
                    targets=[
                        {
                            "expr": 'otelcol_exporter_queue_size{job="justnews-otel-collectors"}',
                            "legendFormat": "{{instance}} → {{exporter}}",
                        }
                    ],
                    grid_pos={"h": 8, "w": 8, "x": 8, "y": 8},
                    description="Current exporter queue depth per collector/exporter",
                ),
                PanelConfig(
                    title="Exporter Send Failures",
                    type="graph",
                    targets=[
                        {
                            "expr": 'sum by(instance) (rate(otelcol_exporter_send_failed_metric_points{job="justnews-otel-collectors"}[5m]))',
                            "legendFormat": "{{instance}} failed",
                        }
                    ],
                    grid_pos={"h": 8, "w": 8, "x": 16, "y": 8},
                    description="Failed metric point transmissions to downstream systems",
                ),
                PanelConfig(
                    title="Exporter Throughput",
                    type="graph",
                    targets=[
                        {
                            "expr": 'sum by(instance) (rate(otelcol_exporter_sent_metric_points{job="justnews-otel-collectors"}[5m]))',
                            "legendFormat": "{{instance}} sent",
                        }
                    ],
                    grid_pos={"h": 8, "w": 12, "x": 0, "y": 14},
                    description="Metric points per second successfully delivered downstream",
                ),
                PanelConfig(
                    title="Filtered Datapoints",
                    type="graph",
                    targets=[
                        {
                            "expr": 'sum by(instance) (increase(otelcol_processor_filter_datapoints_filtered{job="justnews-otel-collectors"}[15m]))',
                            "legendFormat": "{{instance}} filtered",
                        }
                    ],
                    grid_pos={"h": 8, "w": 12, "x": 12, "y": 14},
                    description="Number of datapoints dropped by filter processors",
                ),
                PanelConfig(
                    title="Process Uptime",
                    type="stat",
                    targets=[
                        {
                            "expr": 'otelcol_process_uptime{job="justnews-otel-collectors"}',
                            "legendFormat": "{{instance}}",
                        }
                    ],
                    grid_pos={"h": 4, "w": 8, "x": 0, "y": 22},
                    description="Seconds each collector process has been running",
                ),
                PanelConfig(
                    title="Scraper Errors vs Scrapes",
                    type="graph",
                    targets=[
                        {
                            "expr": 'sum by(instance) (rate(otelcol_scraper_scraped_metric_points{job="justnews-otel-collectors"}[5m]))',
                            "legendFormat": "{{instance}} scraped",
                        },
                        {
                            "expr": 'sum by(instance) (rate(otelcol_scraper_errored_metric_points{job="justnews-otel-collectors"}[5m]))',
                            "legendFormat": "{{instance}} errors",
                        },
                    ],
                    grid_pos={"h": 8, "w": 16, "x": 8, "y": 22},
                    description="Comparison of successful scraper pulls vs errors",
                ),
            ],
            variables=[
                {
                    "name": "instance",
                    "label": "Instance",
                    "type": "query",
                    "query": 'label_values(up{job="justnews-otel-collectors"}, instance)',
                    "multi": True,
                },
                {
                    "name": "exporter",
                    "label": "Exporter",
                    "type": "query",
                    "query": 'label_values(otelcol_exporter_queue_size{job="justnews-otel-collectors"}, exporter)',
                    "multi": True,
                },
            ],
        )

    async def generate_dashboard(
        self, template_name: str, custom_config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Generate a dashboard from template

        Args:
            template_name: Name of the template to use
            custom_config: Optional custom configuration overrides

        Returns:
            Generated Grafana dashboard JSON

        Raises:
            ValueError: If template doesn't exist
        """
        if template_name not in self.templates:
            available_templates = list(self.templates.keys())
            raise ValueError(
                f"Template '{template_name}' not found. Available templates: {available_templates}"
            )

        template = self.templates[template_name]

        # Apply custom configuration if provided
        if custom_config:
            template = self._apply_custom_config(template, custom_config)

        # Generate dashboard JSON
        dashboard_json = self._template_to_grafana_json(template)

        # Add metadata
        dashboard_json.update(
            {
                "dashboard": {
                    "id": None,
                    "title": template.config.title,
                    "description": template.config.description,
                    "tags": template.config.tags,
                    "timezone": template.config.timezone,
                    "refresh": template.config.refresh,
                    "time": {"from": f"now-{template.config.time_range}", "to": "now"},
                    "timepicker": {},
                    "templating": {"list": template.variables},
                    "annotations": {"list": template.annotations},
                    "panels": [
                        self._panel_config_to_grafana(panel)
                        for panel in template.panels
                    ],
                    "version": 1,
                    "schemaVersion": 36,
                    "style": "dark",
                }
            }
        )

        logger.info(
            f"Generated dashboard '{template.config.title}' from template '{template_name}'"
        )
        return dashboard_json

    def _apply_custom_config(
        self, template: DashboardTemplate, custom_config: dict[str, Any]
    ) -> DashboardTemplate:
        """Apply custom configuration to template"""
        # Create a copy of the template
        updated_template = template.copy()

        # Update config if provided
        if "config" in custom_config:
            config_updates = custom_config["config"]
            for key, value in config_updates.items():
                if hasattr(updated_template.config, key):
                    setattr(updated_template.config, key, value)

        # Update panels if provided
        if "panels" in custom_config:
            panel_updates = custom_config["panels"]
            for i, panel_update in enumerate(panel_updates):
                if i < len(updated_template.panels):
                    for key, value in panel_update.items():
                        if hasattr(updated_template.panels[i], key):
                            setattr(updated_template.panels[i], key, value)

        return updated_template

    def _template_to_grafana_json(self, template: DashboardTemplate) -> dict[str, Any]:
        """Convert template to Grafana dashboard JSON format"""
        return {
            "dashboard": {
                "title": template.config.title,
                "description": template.config.description,
                "tags": template.config.tags,
                "timezone": template.config.timezone,
                "refresh": template.config.refresh,
                "time": {"from": f"now-{template.config.time_range}", "to": "now"},
                "panels": [
                    self._panel_config_to_grafana(panel) for panel in template.panels
                ],
                "templating": {"list": template.variables},
                "annotations": {"list": template.annotations},
            },
            "overwrite": False,
        }

    def _panel_config_to_grafana(self, panel: PanelConfig) -> dict[str, Any]:
        """Convert panel config to Grafana panel format"""
        return {
            "id": None,  # Will be assigned by Grafana
            "title": panel.title,
            "type": panel.type,
            "description": panel.description,
            "gridPos": panel.grid_pos,
            "targets": panel.targets,
            "options": panel.options,
            "fieldConfig": {"defaults": {}, "overrides": []},
            "pluginVersion": "8.0.0",
        }

    async def save_dashboard(
        self, dashboard_json: dict[str, Any], filename: str | None = None
    ) -> Path:
        """
        Save dashboard to file

        Args:
            dashboard_json: Dashboard JSON data
            filename: Optional filename (auto-generated if not provided)

        Returns:
            Path to saved dashboard file
        """
        if filename is None:
            title = dashboard_json["dashboard"]["title"].lower().replace(" ", "_")
            filename = f"{title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        filepath = self.output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(dashboard_json, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved dashboard to {filepath}")
        return filepath

    async def deploy_dashboard(
        self, dashboard_json: dict[str, Any], folder_id: int | None = None
    ) -> int | None:
        """
        Deploy dashboard to Grafana

        Args:
            dashboard_json: Dashboard JSON data
            folder_id: Optional Grafana folder ID

        Returns:
            Dashboard ID if successful, None otherwise
        """
        if not self.grafana_api_key:
            logger.warning("Grafana API key not configured, skipping deployment")
            return None

        try:
            import aiohttp

            headers = {
                "Authorization": f"Bearer {self.grafana_api_key}",
                "Content-Type": "application/json",
            }

            # Add folder ID if provided
            if folder_id:
                dashboard_json["folderId"] = folder_id

            async with aiohttp.ClientSession() as session:
                url = f"{self.grafana_url}/api/dashboards/db"
                async with session.post(
                    url, json=dashboard_json, headers=headers
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        dashboard_id = result.get("id")
                        logger.info(
                            f"Successfully deployed dashboard with ID: {dashboard_id}"
                        )
                        return dashboard_id
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"Failed to deploy dashboard: {response.status} - {error_text}"
                        )
                        return None

        except ImportError:
            logger.error("aiohttp not available for Grafana deployment")
            return None
        except Exception as e:
            logger.error(f"Error deploying dashboard to Grafana: {e}")
            return None

    async def generate_all_dashboards(self) -> list[Path]:
        """
        Generate all available dashboard templates

        Returns:
            List of paths to generated dashboard files
        """
        generated_files = []

        for template_name in self.templates.keys():
            try:
                dashboard_json = await self.generate_dashboard(template_name)
                filepath = await self.save_dashboard(dashboard_json)
                generated_files.append(filepath)
                logger.info(f"Generated dashboard for template '{template_name}'")
            except Exception as e:
                logger.error(
                    f"Failed to generate dashboard for template '{template_name}': {e}"
                )

        return generated_files

    def add_template(self, template: DashboardTemplate):
        """
        Add a custom dashboard template

        Args:
            template: Dashboard template to add
        """
        self.templates[template.name] = template
        logger.info(f"Added custom dashboard template '{template.name}'")

    def list_templates(self) -> list[str]:
        """
        List available dashboard templates

        Returns:
            List of template names
        """
        return list(self.templates.keys())

    async def create_custom_dashboard(
        self,
        title: str,
        panels: list[PanelConfig],
        tags: list[str] | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a custom dashboard from scratch

        Args:
            title: Dashboard title
            panels: List of panel configurations
            tags: Optional dashboard tags
            description: Optional dashboard description

        Returns:
            Generated dashboard JSON
        """
        config = DashboardConfig(
            title=title,
            description=description or f"Custom dashboard: {title}",
            tags=tags or ["custom"],
            refresh="30s",
            time_range="1h",
        )

        template = DashboardTemplate(
            name=f"custom_{title.lower().replace(' ', '_')}",
            config=config,
            panels=panels,
        )

        return await self.generate_dashboard(
            template.name,
            {"config": config.model_dump(), "panels": [p.model_dump() for p in panels]},
        )
