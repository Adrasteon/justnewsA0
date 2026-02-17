"""
Alert Dashboard for JustNews Monitoring System

This module provides centralized alert visualization and management for the
JustNews monitoring system. It handles alert aggregation, prioritization,
notification routing, and alert lifecycle management.

Author: JustNews Development Team
Date: October 22, 2025
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Configure logging
logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Alert status values"""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class NotificationChannel(Enum):
    """Available notification channels"""

    EMAIL = "email"
    SMS = "sms"
    SLACK = "slack"
    WEBHOOK = "webhook"
    DASHBOARD = "dashboard"


class AlertRule(BaseModel):
    """Alert rule configuration"""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique rule identifier"
    )
    name: str = Field(..., description="Rule name")
    description: str | None = Field(None, description="Rule description")
    query: str = Field(..., description="Prometheus-style query or condition")
    severity: AlertSeverity = Field(..., description="Alert severity level")
    threshold: float = Field(..., description="Alert threshold value")
    duration: int = Field(300, description="Duration in seconds before alert fires")
    labels: dict[str, str] = Field(default_factory=dict, description="Alert labels")
    annotations: dict[str, str] = Field(
        default_factory=dict, description="Alert annotations"
    )
    enabled: bool = Field(True, description="Whether the rule is enabled")

    @field_validator("duration")
    @classmethod
    def validate_duration(cls, v):
        """Validate duration is positive"""
        if v <= 0:
            raise ValueError("Duration must be positive")
        return v


class Alert(BaseModel):
    """Alert instance"""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique alert identifier"
    )
    rule_id: str = Field(..., description="Associated rule ID")
    rule_name: str = Field(..., description="Associated rule name")
    severity: AlertSeverity = Field(..., description="Alert severity")
    status: AlertStatus = Field(AlertStatus.ACTIVE, description="Alert status")
    summary: str = Field(..., description="Alert summary")
    description: str = Field(..., description="Detailed alert description")
    value: float = Field(..., description="Alert value")
    labels: dict[str, str] = Field(default_factory=dict, description="Alert labels")
    annotations: dict[str, str] = Field(
        default_factory=dict, description="Alert annotations"
    )
    starts_at: datetime = Field(
        default_factory=datetime.now, description="Alert start time"
    )
    ends_at: datetime | None = Field(None, description="Alert end time")
    acknowledged_by: str | None = Field(None, description="User who acknowledged")
    acknowledged_at: datetime | None = Field(None, description="Acknowledgement time")
    resolved_by: str | None = Field(None, description="User who resolved")
    resolved_at: datetime | None = Field(None, description="Resolution time")


class NotificationConfig(BaseModel):
    """Notification configuration"""

    channel: NotificationChannel = Field(..., description="Notification channel")
    enabled: bool = Field(True, description="Whether notifications are enabled")
    recipients: list[str] = Field(
        default_factory=list, description="Notification recipients"
    )
    template: str | None = Field(None, description="Notification template")
    filters: dict[str, Any] = Field(
        default_factory=dict, description="Notification filters"
    )


@dataclass
class AlertDashboard:
    """
    Centralized alert dashboard for JustNews monitoring system.

    This class manages alert rules, alert instances, notification routing,
    and provides a centralized interface for alert visualization and management.
    """

    # Alert rules
    rules: dict[str, AlertRule] = field(default_factory=dict)

    # Active alerts
    active_alerts: dict[str, Alert] = field(default_factory=dict)

    # Alert history
    alert_history: list[Alert] = field(default_factory=list)

    # Notification configurations
    notification_configs: dict[NotificationChannel, NotificationConfig] = field(
        default_factory=dict
    )

    # Alert handlers
    alert_handlers: dict[str, list[Callable]] = field(default_factory=dict)

    # Dashboard statistics
    stats: dict[str, Any] = field(
        default_factory=lambda: {
            "total_alerts": 0,
            "active_alerts": 0,
            "acknowledged_alerts": 0,
            "resolved_alerts": 0,
            "suppressed_alerts": 0,
            "alerts_by_severity": {"low": 0, "medium": 0, "high": 0, "critical": 0},
        }
    )

    # Configuration
    max_history_size: int = field(default=10000)
    alert_retention_days: int = field(default=30)

    def __post_init__(self):
        """Initialize alert dashboard"""
        self._setup_default_rules()
        self._setup_default_notifications()

    def _setup_default_rules(self):
        """Setup default alert rules"""
        default_rules = [
            AlertRule(
                name="High CPU Usage",
                description="CPU usage above 90% for 5 minutes",
                query="cpu_usage_percent > 90",
                severity=AlertSeverity.HIGH,
                threshold=90.0,
                duration=300,
                labels={"component": "system", "resource": "cpu"},
                annotations={
                    "summary": "High CPU usage detected",
                    "description": "CPU usage is above 90% for more than 5 minutes",
                },
            ),
            AlertRule(
                name="Memory Usage Critical",
                description="Memory usage above 95% for 2 minutes",
                query="memory_usage_percent > 95",
                severity=AlertSeverity.CRITICAL,
                threshold=95.0,
                duration=120,
                labels={"component": "system", "resource": "memory"},
                annotations={
                    "summary": "Critical memory usage",
                    "description": "Memory usage is above 95% for more than 2 minutes",
                },
            ),
            AlertRule(
                name="Agent Down",
                description="Agent service is not responding",
                query='up{job=~"justnews-.*"} == 0',
                severity=AlertSeverity.CRITICAL,
                threshold=0.0,
                duration=60,
                labels={"component": "agent", "type": "availability"},
                annotations={
                    "summary": "Agent service down",
                    "description": "Agent service has stopped responding",
                },
            ),
            AlertRule(
                name="High Error Rate",
                description="Error rate above 5% for 10 minutes",
                query="error_rate_percent > 5",
                severity=AlertSeverity.MEDIUM,
                threshold=5.0,
                duration=600,
                labels={"component": "application", "type": "errors"},
                annotations={
                    "summary": "High error rate detected",
                    "description": "Application error rate is above 5% for more than 10 minutes",
                },
            ),
            AlertRule(
                name="Security Alert",
                description="Security incident detected",
                query="security_alerts_total > 0",
                severity=AlertSeverity.HIGH,
                threshold=0.0,
                duration=30,
                labels={"component": "security", "type": "incident"},
                annotations={
                    "summary": "Security alert triggered",
                    "description": "Security monitoring has detected an incident",
                },
            ),
        ]

        for rule in default_rules:
            self.add_rule(rule)

    def _setup_default_notifications(self):
        """Setup default notification configurations"""
        default_configs = [
            NotificationConfig(
                channel=NotificationChannel.EMAIL,
                enabled=True,
                recipients=["alerts@justnews.com"],
                filters={"severity": ["high", "critical"]},
            ),
            NotificationConfig(
                channel=NotificationChannel.SLACK,
                enabled=True,
                recipients=["#alerts"],
                filters={"severity": ["medium", "high", "critical"]},
            ),
            NotificationConfig(
                channel=NotificationChannel.SMS,
                enabled=False,  # Disabled by default
                recipients=["+1234567890"],
                filters={"severity": ["critical"]},
            ),
            NotificationConfig(
                channel=NotificationChannel.WEBHOOK,
                enabled=True,
                recipients=["https://api.pagerduty.com/v2/enqueue"],
                filters={"severity": ["high", "critical"]},
            ),
        ]

        for config in default_configs:
            self.notification_configs[config.channel] = config

    def add_rule(self, rule: AlertRule):
        """Add an alert rule"""
        self.rules[rule.id] = rule
        logger.info(f"Added alert rule '{rule.name}' with ID {rule.id}")

    def remove_rule(self, rule_id: str):
        """Remove an alert rule"""
        if rule_id in self.rules:
            rule = self.rules.pop(rule_id)
            logger.info(f"Removed alert rule '{rule.name}' with ID {rule_id}")
        else:
            logger.warning(f"Alert rule with ID {rule_id} not found")

    def update_rule(self, rule_id: str, updates: dict[str, Any]):
        """Update an alert rule"""
        if rule_id not in self.rules:
            raise ValueError(f"Alert rule with ID {rule_id} not found")

        rule = self.rules[rule_id]
        for key, value in updates.items():
            if hasattr(rule, key):
                setattr(rule, key, value)

        logger.info(f"Updated alert rule '{rule.name}' with ID {rule_id}")

    def enable_rule(self, rule_id: str):
        """Enable an alert rule"""
        if rule_id in self.rules:
            self.rules[rule_id].enabled = True
            logger.info(f"Enabled alert rule '{self.rules[rule_id].name}'")

    def disable_rule(self, rule_id: str):
        """Disable an alert rule"""
        if rule_id in self.rules:
            self.rules[rule_id].enabled = False
            logger.info(f"Disabled alert rule '{self.rules[rule_id].name}'")

    async def evaluate_rules(self, metrics_data: dict[str, Any]):
        """
        Evaluate alert rules against metrics data

        Args:
            metrics_data: Dictionary of metric name -> value mappings
        """
        for rule in self.rules.values():
            if not rule.enabled:
                continue

            try:
                # Evaluate rule condition
                if await self._evaluate_condition(rule, metrics_data):
                    await self._fire_alert(rule, metrics_data)
            except Exception as e:
                logger.error(f"Error evaluating rule '{rule.name}': {e}")

    async def _evaluate_condition(
        self, rule: AlertRule, metrics_data: dict[str, Any]
    ) -> bool:
        """Evaluate alert rule condition"""
        # Simple threshold-based evaluation
        # In a real implementation, this would parse the query and evaluate it
        metric_name = (
            rule.query.split(">")[0].strip() if ">" in rule.query else rule.query
        )

        if metric_name in metrics_data:
            value = metrics_data[metric_name]
            if ">" in rule.query:
                threshold = float(rule.query.split(">")[1].strip())
                return value > threshold
            elif "<" in rule.query:
                threshold = float(rule.query.split("<")[1].strip())
                return value < threshold
            elif "==" in rule.query:
                threshold = float(rule.query.split("==")[1].strip())
                return value == threshold

        return False

    async def _fire_alert(self, rule: AlertRule, metrics_data: dict[str, Any]):
        """Fire an alert for a rule"""
        # Check if alert already exists
        existing_alert = None
        for alert in self.active_alerts.values():
            if alert.rule_id == rule.id and alert.status == AlertStatus.ACTIVE:
                existing_alert = alert
                break

        if existing_alert:
            # Update existing alert
            existing_alert.value = metrics_data.get(rule.query.split(">")[0].strip(), 0)
            logger.debug(f"Updated existing alert for rule '{rule.name}'")
            return

        # Create new alert
        alert = Alert(
            rule_id=rule.id,
            rule_name=rule.name,
            severity=rule.severity,
            summary=rule.annotations.get("summary", f"Alert: {rule.name}"),
            description=rule.annotations.get(
                "description", f"Alert triggered for rule: {rule.name}"
            ),
            value=metrics_data.get(rule.query.split(">")[0].strip(), 0),
            labels=rule.labels.copy(),
            annotations=rule.annotations.copy(),
        )

        self.active_alerts[alert.id] = alert
        self.stats["total_alerts"] += 1
        self.stats["active_alerts"] += 1
        self.stats["alerts_by_severity"][rule.severity.value] += 1

        logger.warning(
            f"Fired alert: {alert.summary} (severity: {alert.severity.value})"
        )

        # Send notifications
        await self._send_notifications(alert)

        # Trigger alert handlers
        await self._trigger_alert_handlers("alert_fired", alert)

    async def acknowledge_alert(self, alert_id: str, user: str):
        """Acknowledge an alert"""
        if alert_id not in self.active_alerts:
            raise ValueError(f"Alert with ID {alert_id} not found")

        alert = self.active_alerts[alert_id]
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_by = user
        alert.acknowledged_at = datetime.now()

        self.stats["acknowledged_alerts"] += 1

        logger.info(f"Alert '{alert.summary}' acknowledged by {user}")

        # Trigger alert handlers
        await self._trigger_alert_handlers("alert_acknowledged", alert)

    async def resolve_alert(self, alert_id: str, user: str):
        """Resolve an alert"""
        if alert_id not in self.active_alerts:
            raise ValueError(f"Alert with ID {alert_id} not found")

        alert = self.active_alerts[alert_id]
        alert.status = AlertStatus.RESOLVED
        alert.resolved_by = user
        alert.resolved_at = datetime.now()
        alert.ends_at = datetime.now()

        self.stats["resolved_alerts"] += 1
        self.stats["active_alerts"] -= 1
        self.stats["alerts_by_severity"][alert.severity.value] -= 1

        # Move to history
        self.alert_history.append(alert)
        del self.active_alerts[alert_id]

        # Maintain history size
        if len(self.alert_history) > self.max_history_size:
            self.alert_history.pop(0)

        logger.info(f"Alert '{alert.summary}' resolved by {user}")

        # Trigger alert handlers
        await self._trigger_alert_handlers("alert_resolved", alert)

    async def suppress_alert(self, alert_id: str, duration: int, user: str):
        """Suppress an alert for a duration"""
        if alert_id not in self.active_alerts:
            raise ValueError(f"Alert with ID {alert_id} not found")

        alert = self.active_alerts[alert_id]
        alert.status = AlertStatus.SUPPRESSED

        # Schedule unsuppression
        asyncio.create_task(self._unsuppress_alert(alert_id, duration))

        logger.info(f"Alert '{alert.summary}' suppressed for {duration}s by {user}")

    async def _unsuppress_alert(self, alert_id: str, duration: int):
        """Unsuppress an alert after duration"""
        await asyncio.sleep(duration)

        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            if alert.status == AlertStatus.SUPPRESSED:
                alert.status = AlertStatus.ACTIVE
                logger.info(f"Alert '{alert.summary}' unsuppressed")

    async def _send_notifications(self, alert: Alert):
        """Send notifications for an alert"""
        for channel, config in self.notification_configs.items():
            if not config.enabled:
                continue

            # Check filters
            if not self._matches_filters(alert, config.filters):
                continue

            try:
                await self._send_notification(channel, config, alert)
            except Exception as e:
                logger.error(f"Failed to send {channel.value} notification: {e}")

    def _matches_filters(self, alert: Alert, filters: dict[str, Any]) -> bool:
        """Check if alert matches notification filters"""
        for filter_key, filter_values in filters.items():
            if filter_key == "severity":
                if alert.severity.value not in filter_values:
                    return False
            elif filter_key == "labels":
                for label_key, label_value in filter_values.items():
                    if alert.labels.get(label_key) != label_value:
                        return False
        return True

    async def _send_notification(
        self, channel: NotificationChannel, config: NotificationConfig, alert: Alert
    ):
        """Send notification via specific channel"""
        if channel == NotificationChannel.EMAIL:
            await self._send_email_notification(config, alert)
        elif channel == NotificationChannel.SLACK:
            await self._send_slack_notification(config, alert)
        elif channel == NotificationChannel.SMS:
            await self._send_sms_notification(config, alert)
        elif channel == NotificationChannel.WEBHOOK:
            await self._send_webhook_notification(config, alert)

    async def _send_email_notification(self, config: NotificationConfig, alert: Alert):
        """Send email notification"""
        # Implementation would integrate with email service
        logger.info(
            f"Sending email notification to {config.recipients} for alert: {alert.summary}"
        )

    async def _send_slack_notification(self, config: NotificationConfig, alert: Alert):
        """Send Slack notification"""
        # Implementation would integrate with Slack API
        logger.info(
            f"Sending Slack notification to {config.recipients} for alert: {alert.summary}"
        )

    async def _send_sms_notification(self, config: NotificationConfig, alert: Alert):
        """Send SMS notification"""
        # Implementation would integrate with SMS service
        logger.info(
            f"Sending SMS notification to {config.recipients} for alert: {alert.summary}"
        )

    async def _send_webhook_notification(
        self, config: NotificationConfig, alert: Alert
    ):
        """Send webhook notification"""
        # Implementation would send HTTP POST to webhook URL
        logger.info(
            f"Sending webhook notification to {config.recipients} for alert: {alert.summary}"
        )

    async def _trigger_alert_handlers(self, event_type: str, alert: Alert):
        """Trigger alert event handlers"""
        handlers = self.alert_handlers.get(event_type, [])
        for handler in handlers:
            try:
                await handler(alert)
            except Exception as e:
                logger.error(f"Error in alert handler for event '{event_type}': {e}")

    def add_alert_handler(self, event_type: str, handler: Callable):
        """Add alert event handler"""
        if event_type not in self.alert_handlers:
            self.alert_handlers[event_type] = []
        self.alert_handlers[event_type].append(handler)
        logger.info(f"Added alert handler for event type '{event_type}'")

    def get_active_alerts(
        self, severity_filter: AlertSeverity | None = None
    ) -> list[Alert]:
        """Get active alerts, optionally filtered by severity"""
        alerts = list(self.active_alerts.values())
        if severity_filter:
            alerts = [a for a in alerts if a.severity == severity_filter]
        return sorted(alerts, key=lambda x: x.starts_at, reverse=True)

    def get_alert_history(self, days: int = 7) -> list[Alert]:
        """Get alert history for specified days"""
        cutoff = datetime.now() - timedelta(days=days)
        return [a for a in self.alert_history if a.starts_at >= cutoff]

    def get_alert_stats(self) -> dict[str, Any]:
        """Get alert statistics"""
        return self.stats.copy()

    def get_rules(self) -> list[AlertRule]:
        """Get all alert rules"""
        return list(self.rules.values())

    def get_rule(self, rule_id: str) -> AlertRule | None:
        """Get specific alert rule"""
        return self.rules.get(rule_id)

    async def cleanup_old_alerts(self):
        """Clean up old resolved alerts from history"""
        cutoff = datetime.now() - timedelta(days=self.alert_retention_days)
        original_count = len(self.alert_history)

        self.alert_history = [
            alert
            for alert in self.alert_history
            if alert.resolved_at and alert.resolved_at >= cutoff
        ]

        removed_count = original_count - len(self.alert_history)
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old alerts from history")

    def export_alerts(self, format: str = "json") -> str:
        """Export alerts in specified format"""
        alerts_data = {
            "active_alerts": [
                alert.model_dump() for alert in self.active_alerts.values()
            ],
            "alert_history": [
                alert.model_dump() for alert in self.alert_history[-100:]
            ],  # Last 100
            "rules": [rule.model_dump() for rule in self.rules.values()],
            "stats": self.stats,
            "exported_at": datetime.now().isoformat(),
        }

        if format == "json":
            return json.dumps(alerts_data, indent=2, default=str)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    async def import_alerts(self, data: str, format: str = "json"):
        """Import alerts from exported data"""
        if format == "json":
            alerts_data = json.loads(data)

            # Import rules
            for rule_data in alerts_data.get("rules", []):
                rule = AlertRule(**rule_data)
                self.add_rule(rule)

            logger.info("Imported alert configuration")
        else:
            raise ValueError(f"Unsupported import format: {format}")
