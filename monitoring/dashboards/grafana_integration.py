"""
Grafana Integration for JustNews Monitoring System

This module provides comprehensive Grafana integration for advanced visualization,
custom dashboard deployment, and monitoring panel management. It enables
seamless integration between the monitoring system and Grafana for
enterprise-grade dashboards and alerting.

Author: JustNews Development Team
Date: October 22, 2025
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from pydantic import BaseModel, Field, field_validator

# Configure logging
logger = logging.getLogger(__name__)


class GrafanaConfig(BaseModel):
    """Grafana configuration"""

    url: str = Field(..., description="Grafana server URL")
    api_key: str = Field(..., description="Grafana API key")
    datasource_name: str = Field("prometheus", description="Default datasource name")
    folder_name: str = Field("JustNews", description="Dashboard folder name")
    organization_id: int = Field(1, description="Grafana organization ID")
    timeout: int = Field(30, description="Request timeout in seconds")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v):
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v.rstrip("/")


class DashboardPanel(BaseModel):
    """Grafana dashboard panel configuration"""

    id: int | None = Field(None, description="Panel ID")
    title: str = Field(..., description="Panel title")
    type: str = Field(..., description="Panel type (graph, table, heatmap, etc.)")
    targets: list[dict[str, Any]] = Field(
        default_factory=list, description="Query targets"
    )
    grid_pos: dict[str, Any] = Field(..., description="Grid position")
    options: dict[str, Any] = Field(default_factory=dict, description="Panel options")
    field_config: dict[str, Any] = Field(
        default_factory=dict, description="Field configuration"
    )
    transformations: list[dict[str, Any]] = Field(
        default_factory=list, description="Data transformations"
    )


class DashboardTemplate(BaseModel):
    """Grafana dashboard template"""

    name: str = Field(..., description="Template name")
    description: str = Field("", description="Template description")
    tags: list[str] = Field(default_factory=list, description="Dashboard tags")
    panels: list[DashboardPanel] = Field(
        default_factory=list, description="Dashboard panels"
    )
    templating: dict[str, Any] = Field(
        default_factory=dict, description="Template variables"
    )
    time: dict[str, Any] = Field(
        default_factory=lambda: {"from": "now-1h", "to": "now"},
        description="Time range",
    )
    refresh: str = Field("30s", description="Refresh interval")


class GrafanaAlertRule(BaseModel):
    """Grafana alert rule configuration"""

    name: str = Field(..., description="Alert rule name")
    query: str = Field(..., description="PromQL query")
    condition: str = Field(..., description="Alert condition")
    duration: str = Field("5m", description="For duration")
    severity: str = Field("warning", description="Alert severity")
    labels: dict[str, str] = Field(default_factory=dict, description="Alert labels")
    annotations: dict[str, str] = Field(
        default_factory=dict, description="Alert annotations"
    )


@dataclass
class GrafanaIntegration:
    """
    Grafana integration for advanced visualization and monitoring.

    This class provides comprehensive integration with Grafana for:
    - Automated dashboard deployment
    - Custom panel creation and management
    - Alert rule synchronization
    - Data source management
    - Folder and permission management
    """

    config: GrafanaConfig
    session: aiohttp.ClientSession | None = None

    # Dashboard templates
    templates: dict[str, DashboardTemplate] = field(default_factory=dict)

    # Deployed dashboards
    deployed_dashboards: dict[str, str] = field(default_factory=dict)  # name -> uid

    # Alert rules
    alert_rules: dict[str, GrafanaAlertRule] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize Grafana integration"""
        self._setup_default_templates()
        self._setup_default_alert_rules()

    def _setup_default_templates(self):
        """Setup default dashboard templates"""
        # System Overview Dashboard
        system_overview = DashboardTemplate(
            name="System Overview",
            description="Comprehensive system monitoring dashboard",
            tags=["system", "overview", "justnews"],
            panels=[
                DashboardPanel(
                    title="CPU Usage",
                    type="graph",
                    targets=[
                        {
                            "expr": '100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
                            "legendFormat": "{{instance}}",
                        }
                    ],
                    grid_pos={"h": 8, "w": 12, "x": 0, "y": 0},
                ),
                DashboardPanel(
                    title="Memory Usage",
                    type="graph",
                    targets=[
                        {
                            "expr": "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100",
                            "legendFormat": "{{instance}}",
                        }
                    ],
                    grid_pos={"h": 8, "w": 12, "x": 12, "y": 0},
                ),
                DashboardPanel(
                    title="System Uptime",
                    type="stat",
                    targets=[{"expr": "up", "legendFormat": "{{instance}}"}],
                    grid_pos={"h": 4, "w": 8, "x": 0, "y": 8},
                ),
                DashboardPanel(
                    title="Error Rate",
                    type="graph",
                    targets=[
                        {
                            "expr": 'rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) * 100',
                            "legendFormat": "{{service}}",
                        }
                    ],
                    grid_pos={"h": 8, "w": 16, "x": 8, "y": 8},
                ),
            ],
        )

        # Business Metrics Dashboard
        business_metrics = DashboardTemplate(
            name="Business Metrics",
            description="Key business performance indicators",
            tags=["business", "kpi", "justnews"],
            panels=[
                DashboardPanel(
                    title="Monthly Active Users",
                    type="stat",
                    targets=[{"expr": "monthly_active_users", "legendFormat": "MAU"}],
                    grid_pos={"h": 4, "w": 6, "x": 0, "y": 0},
                ),
                DashboardPanel(
                    title="Revenue Growth",
                    type="graph",
                    targets=[{"expr": "revenue_total", "legendFormat": "Revenue"}],
                    grid_pos={"h": 8, "w": 12, "x": 6, "y": 0},
                ),
                DashboardPanel(
                    title="Content Accuracy Score",
                    type="gauge",
                    targets=[
                        {"expr": "content_accuracy_score", "legendFormat": "Accuracy"}
                    ],
                    grid_pos={"h": 6, "w": 6, "x": 18, "y": 0},
                ),
                DashboardPanel(
                    title="Customer Satisfaction",
                    type="stat",
                    targets=[
                        {"expr": "customer_satisfaction_score", "legendFormat": "CSAT"}
                    ],
                    grid_pos={"h": 4, "w": 6, "x": 0, "y": 4},
                ),
            ],
        )

        # Agent Performance Dashboard
        agent_performance = DashboardTemplate(
            name="Agent Performance",
            description="AI agent performance and metrics",
            tags=["agents", "performance", "ai"],
            panels=[
                DashboardPanel(
                    title="Agent Response Times",
                    type="heatmap",
                    targets=[
                        {
                            "expr": "agent_response_time_seconds",
                            "legendFormat": "{{agent}}",
                        }
                    ],
                    grid_pos={"h": 8, "w": 16, "x": 0, "y": 0},
                ),
                DashboardPanel(
                    title="Agent Success Rate",
                    type="bargauge",
                    targets=[
                        {"expr": "agent_success_rate", "legendFormat": "{{agent}}"}
                    ],
                    grid_pos={"h": 8, "w": 8, "x": 16, "y": 0},
                ),
                DashboardPanel(
                    title="Content Processing Queue",
                    type="graph",
                    targets=[
                        {
                            "expr": "content_processing_queue_length",
                            "legendFormat": "Queue Length",
                        }
                    ],
                    grid_pos={"h": 6, "w": 12, "x": 0, "y": 8},
                ),
            ],
        )

        self.templates = {
            "system_overview": system_overview,
            "business_metrics": business_metrics,
            "agent_performance": agent_performance,
        }

    def _setup_default_alert_rules(self):
        """Setup default alert rules"""
        default_rules = [
            GrafanaAlertRule(
                name="High CPU Usage",
                query='100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 90',
                condition="CPU usage > 90%",
                duration="5m",
                severity="critical",
                labels={"service": "system", "severity": "critical"},
                annotations={
                    "summary": "High CPU usage detected",
                    "description": "CPU usage is above 90% for more than 5 minutes",
                },
            ),
            GrafanaAlertRule(
                name="High Memory Usage",
                query="(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100 > 95",
                condition="Memory usage > 95%",
                duration="3m",
                severity="warning",
                labels={"service": "system", "severity": "warning"},
                annotations={
                    "summary": "High memory usage detected",
                    "description": "Memory usage is above 95% for more than 3 minutes",
                },
            ),
            GrafanaAlertRule(
                name="Service Down",
                query="up == 0",
                condition="Service is down",
                duration="1m",
                severity="critical",
                labels={"service": "availability", "severity": "critical"},
                annotations={
                    "summary": "Service is down",
                    "description": "Service {{ $labels.instance }} is not responding",
                },
            ),
            GrafanaAlertRule(
                name="High Error Rate",
                query='rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) * 100 > 5',
                condition="Error rate > 5%",
                duration="5m",
                severity="warning",
                labels={"service": "api", "severity": "warning"},
                annotations={
                    "summary": "High error rate detected",
                    "description": "Error rate is above 5% for more than 5 minutes",
                },
            ),
        ]

        for rule in default_rules:
            self.alert_rules[rule.name] = rule

    async def initialize(self):
        """Initialize Grafana integration"""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            )

        # Test connection
        await self._test_connection()

        # Ensure folder exists
        await self._ensure_folder()

        logger.info("Grafana integration initialized successfully")

    async def _test_connection(self):
        """Test connection to Grafana"""
        try:
            async with self.session.get(f"{self.config.url}/api/health") as response:
                if response.status != 200:
                    raise Exception(f"Grafana health check failed: {response.status}")
                logger.info("Grafana connection test successful")
        except Exception as e:
            logger.error(f"Failed to connect to Grafana: {e}")
            raise

    async def _ensure_folder(self):
        """Ensure the dashboard folder exists"""
        try:
            # Check if folder exists
            async with self.session.get(f"{self.config.url}/api/folders") as response:
                if response.status == 200:
                    folders = await response.json()
                    folder_exists = any(
                        f["title"] == self.config.folder_name for f in folders
                    )

                    if not folder_exists:
                        # Create folder
                        folder_data = {
                            "title": self.config.folder_name,
                            "uid": self.config.folder_name.lower().replace(" ", "_"),
                        }
                        async with self.session.post(
                            f"{self.config.url}/api/folders", json=folder_data
                        ) as create_response:
                            if create_response.status not in [200, 201]:
                                logger.warning(
                                    f"Failed to create folder: {create_response.status}"
                                )
                            else:
                                logger.info(
                                    f"Created Grafana folder: {self.config.folder_name}"
                                )
                else:
                    logger.warning(f"Failed to check folders: {response.status}")
        except Exception as e:
            logger.error(f"Error ensuring folder exists: {e}")

    async def deploy_dashboard(
        self, template_name: str, dashboard_name: str | None = None
    ) -> str:
        """
        Deploy a dashboard from template

        Args:
            template_name: Name of the template to deploy
            dashboard_name: Custom name for the dashboard (optional)

        Returns:
            Dashboard UID
        """
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")

        template = self.templates[template_name]
        name = dashboard_name or template.name

        # Create dashboard JSON
        dashboard_json = self._create_dashboard_json(template, name)

        try:
            async with self.session.post(
                f"{self.config.url}/api/dashboards/db", json=dashboard_json
            ) as response:
                if response.status in [200, 201]:
                    result = await response.json()
                    uid = result["uid"]
                    self.deployed_dashboards[name] = uid
                    logger.info(
                        f"Successfully deployed dashboard '{name}' with UID: {uid}"
                    )
                    return uid
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"Failed to deploy dashboard: {response.status} - {error_text}"
                    )
        except Exception as e:
            logger.error(f"Error deploying dashboard '{name}': {e}")
            raise

    def _create_dashboard_json(
        self, template: DashboardTemplate, name: str
    ) -> dict[str, Any]:
        """Create Grafana dashboard JSON from template"""
        dashboard = {
            "dashboard": {
                "title": name,
                "tags": template.tags,
                "timezone": "browser",
                "panels": [
                    panel.model_dump(exclude_none=True) for panel in template.panels
                ],
                "time": template.time,
                "refresh": template.refresh,
                "templating": template.templating,
                "version": 1,
                "schemaVersion": 36,
                "style": "dark",
                "editable": True,
                "hideControls": False,
                "graphTooltip": 1,
            },
            "folderUid": self.config.folder_name.lower().replace(" ", "_"),
            "overwrite": True,
        }

        return dashboard

    async def update_dashboard(self, dashboard_name: str, updates: dict[str, Any]):
        """
        Update an existing dashboard

        Args:
            dashboard_name: Name of the dashboard to update
            updates: Updates to apply
        """
        if dashboard_name not in self.deployed_dashboards:
            raise ValueError(f"Dashboard '{dashboard_name}' not deployed")

        uid = self.deployed_dashboards[dashboard_name]

        try:
            # Get current dashboard
            async with self.session.get(
                f"{self.config.url}/api/dashboards/uid/{uid}"
            ) as response:
                if response.status != 200:
                    raise Exception(f"Failed to get dashboard: {response.status}")

                current = await response.json()
                dashboard = current["dashboard"]

                # Apply updates
                self._apply_dashboard_updates(dashboard, updates)

                # Update dashboard
                update_data = {
                    "dashboard": dashboard,
                    "folderUid": current.get("meta", {}).get("folderUid"),
                    "overwrite": True,
                }

                async with self.session.post(
                    f"{self.config.url}/api/dashboards/db", json=update_data
                ) as update_response:
                    if update_response.status not in [200, 201]:
                        error_text = await update_response.text()
                        raise Exception(
                            f"Failed to update dashboard: {update_response.status} - {error_text}"
                        )

                    logger.info(f"Successfully updated dashboard '{dashboard_name}'")

        except Exception as e:
            logger.error(f"Error updating dashboard '{dashboard_name}': {e}")
            raise

    def _apply_dashboard_updates(
        self, dashboard: dict[str, Any], updates: dict[str, Any]
    ):
        """Apply updates to dashboard JSON"""
        for key, value in updates.items():
            if key == "panels":
                # Handle panel updates
                for panel_update in value:
                    panel_id = panel_update.get("id")
                    if panel_id is not None:
                        # Find and update existing panel
                        for panel in dashboard.get("panels", []):
                            if panel.get("id") == panel_id:
                                panel.update(panel_update)
                                break
                    else:
                        # Add new panel
                        dashboard["panels"].append(panel_update)
            else:
                # Direct update
                dashboard[key] = value

    async def delete_dashboard(self, dashboard_name: str):
        """
        Delete a deployed dashboard

        Args:
            dashboard_name: Name of the dashboard to delete
        """
        if dashboard_name not in self.deployed_dashboards:
            raise ValueError(f"Dashboard '{dashboard_name}' not deployed")

        uid = self.deployed_dashboards[dashboard_name]

        try:
            async with self.session.delete(
                f"{self.config.url}/api/dashboards/uid/{uid}"
            ) as response:
                if response.status == 200:
                    del self.deployed_dashboards[dashboard_name]
                    logger.info(f"Successfully deleted dashboard '{dashboard_name}'")
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"Failed to delete dashboard: {response.status} - {error_text}"
                    )
        except Exception as e:
            logger.error(f"Error deleting dashboard '{dashboard_name}': {e}")
            raise

    async def create_alert_rule(self, rule: GrafanaAlertRule):
        """
        Create a Grafana alert rule

        Args:
            rule: Alert rule configuration
        """
        try:
            rule_data = {
                "name": rule.name,
                "query": rule.query,
                "condition": rule.condition,
                "duration": rule.duration,
                "severity": rule.severity,
                "labels": rule.labels,
                "annotations": rule.annotations,
            }

            async with self.session.post(
                f"{self.config.url}/api/v1/provisioning/alert-rules", json=rule_data
            ) as response:
                if response.status in [200, 201]:
                    self.alert_rules[rule.name] = rule
                    logger.info(f"Successfully created alert rule '{rule.name}'")
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"Failed to create alert rule: {response.status} - {error_text}"
                    )
        except Exception as e:
            logger.error(f"Error creating alert rule '{rule.name}': {e}")
            raise

    async def update_alert_rule(self, rule_name: str, updates: dict[str, Any]):
        """
        Update an existing alert rule

        Args:
            rule_name: Name of the alert rule to update
            updates: Updates to apply
        """
        if rule_name not in self.alert_rules:
            raise ValueError(f"Alert rule '{rule_name}' not found")

        rule = self.alert_rules[rule_name]

        # Apply updates
        for key, value in updates.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        # Recreate the rule (Grafana doesn't support direct updates)
        await self.delete_alert_rule(rule_name)
        await self.create_alert_rule(rule)

    async def delete_alert_rule(self, rule_name: str):
        """
        Delete an alert rule

        Args:
            rule_name: Name of the alert rule to delete
        """
        if rule_name not in self.alert_rules:
            raise ValueError(f"Alert rule '{rule_name}' not found")

        # Note: Grafana alert rule deletion requires the rule ID
        # This is a simplified implementation
        try:
            # In a real implementation, you'd need to get the rule ID first
            logger.warning(
                f"Alert rule deletion not fully implemented for '{rule_name}'"
            )
            del self.alert_rules[rule_name]
        except Exception as e:
            logger.error(f"Error deleting alert rule '{rule_name}': {e}")
            raise

    async def get_dashboard_metrics(self, dashboard_name: str) -> dict[str, Any]:
        """
        Get metrics about a dashboard

        Args:
            dashboard_name: Name of the dashboard

        Returns:
            Dashboard metrics
        """
        if dashboard_name not in self.deployed_dashboards:
            raise ValueError(f"Dashboard '{dashboard_name}' not deployed")

        uid = self.deployed_dashboards[dashboard_name]

        try:
            async with self.session.get(
                f"{self.config.url}/api/dashboards/uid/{uid}"
            ) as response:
                if response.status != 200:
                    raise Exception(f"Failed to get dashboard: {response.status}")

                dashboard_data = await response.json()
                dashboard = dashboard_data["dashboard"]

                return {
                    "name": dashboard_name,
                    "uid": uid,
                    "title": dashboard.get("title"),
                    "panels_count": len(dashboard.get("panels", [])),
                    "tags": dashboard.get("tags", []),
                    "version": dashboard.get("version"),
                    "last_updated": dashboard_data.get("meta", {}).get("updated"),
                    "folder": dashboard_data.get("meta", {}).get("folderTitle"),
                }
        except Exception as e:
            logger.error(f"Error getting dashboard metrics for '{dashboard_name}': {e}")
            raise

    async def export_dashboard(self, dashboard_name: str, file_path: str):
        """
        Export a dashboard to a JSON file

        Args:
            dashboard_name: Name of the dashboard to export
            file_path: Path to save the exported dashboard
        """
        if dashboard_name not in self.deployed_dashboards:
            raise ValueError(f"Dashboard '{dashboard_name}' not deployed")

        uid = self.deployed_dashboards[dashboard_name]

        try:
            async with self.session.get(
                f"{self.config.url}/api/dashboards/uid/{uid}"
            ) as response:
                if response.status != 200:
                    raise Exception(f"Failed to get dashboard: {response.status}")

                dashboard_data = await response.json()

                # Save to file
                with open(file_path, "w") as f:
                    json.dump(dashboard_data, f, indent=2)

                logger.info(
                    f"Successfully exported dashboard '{dashboard_name}' to {file_path}"
                )

        except Exception as e:
            logger.error(f"Error exporting dashboard '{dashboard_name}': {e}")
            raise

    async def import_dashboard(
        self, file_path: str, dashboard_name: str | None = None
    ) -> str:
        """
        Import a dashboard from a JSON file

        Args:
            file_path: Path to the dashboard JSON file
            dashboard_name: Custom name for the imported dashboard

        Returns:
            Dashboard UID
        """
        try:
            with open(file_path) as f:
                dashboard_data = json.load(f)

            if dashboard_name:
                dashboard_data["dashboard"]["title"] = dashboard_name

            async with self.session.post(
                f"{self.config.url}/api/dashboards/db", json=dashboard_data
            ) as response:
                if response.status in [200, 201]:
                    result = await response.json()
                    uid = result["uid"]
                    name = dashboard_data["dashboard"]["title"]
                    self.deployed_dashboards[name] = uid
                    logger.info(
                        f"Successfully imported dashboard '{name}' with UID: {uid}"
                    )
                    return uid
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"Failed to import dashboard: {response.status} - {error_text}"
                    )
        except Exception as e:
            logger.error(f"Error importing dashboard from {file_path}: {e}")
            raise

    async def list_dashboards(self) -> list[dict[str, Any]]:
        """
        List all dashboards in the organization

        Returns:
            List of dashboard information
        """
        try:
            async with self.session.get(
                f"{self.config.url}/api/search?type=dash-db"
            ) as response:
                if response.status != 200:
                    raise Exception(f"Failed to list dashboards: {response.status}")

                dashboards = await response.json()
                return dashboards
        except Exception as e:
            logger.error(f"Error listing dashboards: {e}")
            raise

    async def get_system_status(self) -> dict[str, Any]:
        """
        Get Grafana system status

        Returns:
            System status information
        """
        try:
            async with self.session.get(f"{self.config.url}/api/health") as response:
                if response.status != 200:
                    raise Exception(f"Failed to get system status: {response.status}")

                status = await response.json()
                return status
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            raise

    async def close(self):
        """Close the integration and cleanup resources"""
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("Grafana integration closed")

    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
