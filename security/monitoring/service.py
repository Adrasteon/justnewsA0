"""
JustNews Security Monitoring Service

Provides real-time security monitoring, threat detection, alerting, and security event analysis.
"""

import asyncio
import json
import logging
import secrets
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import aiofiles
from pydantic import BaseModel, Field

from ..models import SecurityConfig

logger = logging.getLogger(__name__)


class SecurityEventType(Enum):
    """Security event types"""

    AUTHENTICATION_SUCCESS = "authentication_success"
    AUTHENTICATION_FAILURE = "authentication_failure"
    AUTHENTICATION_BLOCKED = "authentication_blocked"
    AUTHORIZATION_DENIED = "authorization_denied"
    PERMISSION_CHECK = "permission_check"
    DATA_ENCRYPTION = "data_encryption"
    DATA_DECRYPTION = "data_decryption"
    COMPLIANCE_VIOLATION = "compliance_violation"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    BRUTE_FORCE_ATTACK = "brute_force_attack"
    UNUSUAL_TRAFFIC = "unusual_traffic"
    DATA_BREACH_ATTEMPT = "data_breach_attempt"


class AlertSeverity(Enum):
    """Alert severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityAlert(BaseModel):
    """Security alert"""

    id: str
    timestamp: datetime
    event_type: str
    severity: AlertSeverity
    title: str
    description: str
    details: dict[str, Any] = Field(default_factory=dict)
    user_id: int | None = None
    ip_address: str | None = None
    resolved: bool = False
    resolved_at: datetime | None = None
    resolution_notes: str | None = None


class SecurityMetrics(BaseModel):
    """Security metrics snapshot"""

    timestamp: datetime
    total_events: int
    events_by_type: dict[str, int]
    active_alerts: int
    alerts_by_severity: dict[str, int]
    failed_auth_attempts: int
    suspicious_ips: list[str]
    top_attack_vectors: list[dict[str, Any]]


class MonitoringRule(BaseModel):
    """Monitoring rule for threat detection"""

    id: str
    name: str
    description: str
    event_pattern: dict[str, Any]  # Pattern to match events
    condition: str  # Python expression to evaluate
    severity: AlertSeverity
    enabled: bool = True
    cooldown_minutes: int = 5  # Minimum time between alerts
    last_triggered: datetime | None = None


@dataclass
class MonitoringConfig:
    """Monitoring service configuration"""

    alert_thresholds: dict[str, Any] = None
    monitoring_window_minutes: int = 60
    max_events_in_memory: int = 10000
    alert_retention_days: int = 30
    enable_real_time_alerts: bool = True
    suspicious_activity_threshold: int = 10

    def __post_init__(self):
        if self.alert_thresholds is None:
            self.alert_thresholds = {
                "failed_logins_per_hour": 10,
                "suspicious_activities_per_day": 5,
                "unusual_traffic_burst": 100,
                "brute_force_attempts": 5,
            }


class SecurityMonitor:
    """
    Security monitoring service for real-time threat detection and alerting

    Monitors security events, detects threats, generates alerts, and provides
    security analytics and reporting.
    """

    def __init__(self, config: SecurityConfig):
        self.config = config
        self.monitoring_config = MonitoringConfig()
        self._security_events: deque = deque(
            maxlen=self.monitoring_config.max_events_in_memory
        )
        self._active_alerts: dict[str, SecurityAlert] = {}
        self._monitoring_rules = self._get_default_rules()
        self._event_counts: dict[str, int] = defaultdict(int)
        self._ip_activity: dict[str, list[datetime]] = defaultdict(list)
        self._alert_handlers: list[Callable] = []

    def _get_default_rules(self) -> dict[str, MonitoringRule]:
        """Get default monitoring rules"""
        return {
            "brute_force_login": MonitoringRule(
                id="brute_force_login",
                name="Brute Force Login Detection",
                description="Detect multiple failed login attempts from same IP",
                event_pattern={"event_type": "authentication_failure"},
                condition="len([e for e in recent_events if e.get('ip_address') == event.get('ip_address')]) >= 5",
                severity=AlertSeverity.HIGH,
            ),
            "unusual_traffic": MonitoringRule(
                id="unusual_traffic",
                name="Unusual Traffic Pattern",
                description="Detect unusual traffic patterns",
                event_pattern={"event_type": "suspicious_activity"},
                condition="event_counts.get('suspicious_activity', 0) > 50",
                severity=AlertSeverity.MEDIUM,
            ),
            "account_lockout": MonitoringRule(
                id="account_lockout",
                name="Account Lockout",
                description="Account locked due to failed attempts",
                event_pattern={"event_type": "authentication_blocked"},
                condition="True",  # Always alert on account lockouts
                severity=AlertSeverity.MEDIUM,
            ),
            "data_breach_attempt": MonitoringRule(
                id="data_breach_attempt",
                name="Data Breach Attempt",
                description="Detect potential data breach attempts",
                event_pattern={"event_type": "data_breach_attempt"},
                condition="True",
                severity=AlertSeverity.CRITICAL,
            ),
            "compliance_violation": MonitoringRule(
                id="compliance_violation",
                name="Compliance Violation",
                description="Detect compliance violations",
                event_pattern={"event_type": "compliance_violation"},
                condition="True",
                severity=AlertSeverity.HIGH,
            ),
        }

    async def initialize(self) -> None:
        """Initialize monitoring service"""
        await self._load_monitoring_data()
        await self._schedule_cleanup_tasks()
        logger.info("SecurityMonitor initialized")

    async def shutdown(self) -> None:
        """Shutdown monitoring service"""
        await self._save_monitoring_data()
        logger.info("SecurityMonitor shutdown")

    async def log_security_event(
        self,
        event_type: str,
        user_id: int | None,
        details: dict[str, Any],
        severity: AlertSeverity = AlertSeverity.LOW,
    ) -> None:
        """
        Log security event and check for threats

        Args:
            event_type: Type of security event
            user_id: Optional user ID
            details: Event details
            severity: Event severity
        """
        try:
            event = {
                "timestamp": datetime.now(UTC),
                "event_type": event_type,
                "user_id": user_id,
                "severity": severity.value,
                "details": details,
                "ip_address": details.get("ip_address"),
                "user_agent": details.get("user_agent"),
            }

            # Add to event queue
            self._security_events.append(event)

            # Update counters
            self._event_counts[event_type] += 1

            # Track IP activity
            if event["ip_address"]:
                self._ip_activity[event["ip_address"]].append(event["timestamp"])

            # Check monitoring rules
            await self._check_monitoring_rules(event)

            # Cleanup old IP activity
            await self._cleanup_old_ip_activity()

            logger.debug(f"Logged security event: {event_type}")

        except Exception as e:
            logger.error(f"Failed to log security event: {e}")

    async def get_active_alerts(self) -> list[dict[str, Any]]:
        """
        Get all active security alerts

        Returns:
            List of active alerts
        """
        return [
            {
                "id": alert.id,
                "timestamp": alert.timestamp.isoformat(),
                "event_type": alert.event_type,
                "severity": alert.severity.value,
                "title": alert.title,
                "description": alert.description,
                "details": alert.details,
                "user_id": alert.user_id,
                "ip_address": alert.ip_address,
                "resolved": alert.resolved,
            }
            for alert in self._active_alerts.values()
            if not alert.resolved
        ]

    async def resolve_alert(self, alert_id: str, resolution_notes: str) -> None:
        """
        Resolve a security alert

        Args:
            alert_id: Alert ID to resolve
            resolution_notes: Notes about resolution
        """
        if alert_id in self._active_alerts:
            alert = self._active_alerts[alert_id]
            alert.resolved = True
            alert.resolved_at = datetime.now(UTC)
            alert.resolution_notes = resolution_notes

            await self._save_monitoring_data()
            logger.info(f"Resolved alert {alert_id}: {resolution_notes}")

    async def get_security_metrics(self, hours: int = 24) -> SecurityMetrics:
        """
        Get security metrics for the specified time period

        Args:
            hours: Number of hours to look back

        Returns:
            Security metrics
        """
        try:
            cutoff_time = datetime.now(UTC) - timedelta(hours=hours)

            # Filter events in time window
            recent_events = [
                e for e in self._security_events if e["timestamp"] > cutoff_time
            ]

            # Count events by type
            events_by_type = defaultdict(int)
            for event in recent_events:
                events_by_type[event["event_type"]] += 1

            # Count alerts by severity
            alerts_by_severity = defaultdict(int)
            for alert in self._active_alerts.values():
                if not alert.resolved and alert.timestamp > cutoff_time:
                    alerts_by_severity[alert.severity.value] += 1

            # Get failed auth attempts
            failed_auth_attempts = events_by_type.get("authentication_failure", 0)

            # Get suspicious IPs (more than threshold events)
            suspicious_ips = [
                ip
                for ip, timestamps in self._ip_activity.items()
                if len([t for t in timestamps if t > cutoff_time])
                > self.monitoring_config.suspicious_activity_threshold
            ]

            # Get top attack vectors
            top_attack_vectors = sorted(
                [
                    {"event_type": et, "count": count}
                    for et, count in events_by_type.items()
                ],
                key=lambda x: x["count"],
                reverse=True,
            )[:5]

            return SecurityMetrics(
                timestamp=datetime.now(UTC),
                total_events=len(recent_events),
                events_by_type=dict(events_by_type),
                active_alerts=len(
                    [a for a in self._active_alerts.values() if not a.resolved]
                ),
                alerts_by_severity=dict(alerts_by_severity),
                failed_auth_attempts=failed_auth_attempts,
                suspicious_ips=suspicious_ips,
                top_attack_vectors=top_attack_vectors,
            )

        except Exception as e:
            logger.error(f"Failed to get security metrics: {e}")
            return SecurityMetrics(
                timestamp=datetime.now(UTC),
                total_events=0,
                events_by_type={},
                active_alerts=0,
                alerts_by_severity={},
                failed_auth_attempts=0,
                suspicious_ips=[],
                top_attack_vectors=[],
            )

    async def add_monitoring_rule(self, rule: MonitoringRule) -> None:
        """
        Add custom monitoring rule

        Args:
            rule: Monitoring rule to add
        """
        self._monitoring_rules[rule.id] = rule
        await self._save_monitoring_data()
        logger.info(f"Added monitoring rule: {rule.name}")

    async def remove_monitoring_rule(self, rule_id: str) -> None:
        """
        Remove monitoring rule

        Args:
            rule_id: Rule ID to remove
        """
        if rule_id in self._monitoring_rules:
            del self._monitoring_rules[rule_id]
            await self._save_monitoring_data()
            logger.info(f"Removed monitoring rule: {rule_id}")

    async def add_alert_handler(self, handler: Callable) -> None:
        """
        Add alert handler function

        Args:
            handler: Function to call when alert is generated (receives SecurityAlert)
        """
        self._alert_handlers.append(handler)

    def get_monitoring_rules(self) -> dict[str, dict[str, Any]]:
        """
        Get all monitoring rules

        Returns:
            Dict of rule ID -> rule data
        """
        return {
            rule_id: {
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "event_pattern": rule.event_pattern,
                "condition": rule.condition,
                "severity": rule.severity.value,
                "enabled": rule.enabled,
                "cooldown_minutes": rule.cooldown_minutes,
                "last_triggered": rule.last_triggered.isoformat()
                if rule.last_triggered
                else None,
            }
            for rule_id, rule in self._monitoring_rules.items()
        }

    async def get_status(self) -> dict[str, Any]:
        """
        Get monitoring service status

        Returns:
            Status information
        """
        active_alerts = len([a for a in self._active_alerts.values() if not a.resolved])

        return {
            "status": "healthy",
            "events_in_memory": len(self._security_events),
            "active_alerts": active_alerts,
            "monitoring_rules": len(self._monitoring_rules),
            "tracked_ips": len(self._ip_activity),
            "alert_handlers": len(self._alert_handlers),
        }

    async def _check_monitoring_rules(self, event: dict[str, Any]) -> None:
        """Check monitoring rules against event"""
        try:
            for rule in self._monitoring_rules.values():
                if not rule.enabled:
                    continue

                # Check cooldown
                if rule.last_triggered:
                    cooldown_end = rule.last_triggered + timedelta(
                        minutes=rule.cooldown_minutes
                    )
                    if datetime.now(UTC) < cooldown_end:
                        continue

                # Check event pattern match
                if not self._matches_pattern(event, rule.event_pattern):
                    continue

                # Evaluate condition
                if await self._evaluate_condition(event, rule):
                    # Generate alert
                    await self._generate_alert(event, rule)
                    rule.last_triggered = datetime.now(UTC)

        except Exception as e:
            logger.error(f"Error checking monitoring rules: {e}")

    def _matches_pattern(self, event: dict[str, Any], pattern: dict[str, Any]) -> bool:
        """Check if event matches pattern"""
        for key, value in pattern.items():
            if key not in event or event[key] != value:
                return False
        return True

    async def _evaluate_condition(
        self, event: dict[str, Any], rule: MonitoringRule
    ) -> bool:
        """Evaluate monitoring rule condition"""
        try:
            # Get recent events for context
            recent_events = list(self._security_events)[-100:]  # Last 100 events

            # Create evaluation context
            context = {
                "event": event,
                "recent_events": recent_events,
                "event_counts": dict(self._event_counts),
            }

            # Evaluate condition (in a safe way)
            # Note: In production, this should be more secure
            allowed_builtins = {
                "len": len,
                "sum": sum,
                "max": max,
                "min": min,
                "abs": abs,
                "all": all,
                "any": any,
                "bool": bool,
                "int": int,
                "float": float,
                "str": str,
                "list": list,
                "dict": dict,
                "set": set,
                "tuple": tuple,
            }
            condition_result = eval(
                rule.condition, {"__builtins__": allowed_builtins}, context
            )

            return bool(condition_result)

        except Exception as e:
            logger.error(f"Error evaluating condition for rule {rule.id}: {e}")
            return False

    async def _generate_alert(
        self, event: dict[str, Any], rule: MonitoringRule
    ) -> None:
        """Generate security alert"""
        try:
            alert_id = f"alert_{datetime.now(UTC).timestamp()}_{secrets.token_hex(4)}"

            alert = SecurityAlert(
                id=alert_id,
                timestamp=datetime.now(UTC),
                event_type=event["event_type"],
                severity=rule.severity,
                title=f"Security Alert: {rule.name}",
                description=rule.description,
                details={
                    "triggering_event": event,
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                },
                user_id=event.get("user_id"),
                ip_address=event.get("ip_address"),
            )

            self._active_alerts[alert_id] = alert

            # Notify alert handlers
            for handler in self._alert_handlers:
                try:
                    await handler(alert)
                except Exception as e:
                    logger.error(f"Alert handler error: {e}")

            logger.warning(
                f"Generated security alert: {alert.title} (severity: {alert.severity.value})"
            )

        except Exception as e:
            logger.error(f"Failed to generate alert: {e}")

    async def _cleanup_old_ip_activity(self) -> None:
        """Cleanup old IP activity data"""
        try:
            cutoff_time = datetime.now(UTC) - timedelta(hours=24)

            for ip in list(self._ip_activity.keys()):
                self._ip_activity[ip] = [
                    timestamp
                    for timestamp in self._ip_activity[ip]
                    if timestamp > cutoff_time
                ]

                if not self._ip_activity[ip]:
                    del self._ip_activity[ip]

        except Exception as e:
            logger.error(f"Error cleaning up IP activity: {e}")

    async def _schedule_cleanup_tasks(self) -> None:
        """Schedule automatic cleanup tasks"""
        # Cleanup old alerts
        asyncio.create_task(self._cleanup_old_alerts())

        # Reset event counters periodically
        asyncio.create_task(self._reset_event_counters())

    async def _cleanup_old_alerts(self) -> None:
        """Cleanup old resolved alerts"""
        while True:
            try:
                await asyncio.sleep(86400)  # Run daily

                cutoff_date = datetime.now(UTC) - timedelta(
                    days=self.monitoring_config.alert_retention_days
                )

                alerts_to_remove = []
                for alert_id, alert in self._active_alerts.items():
                    if (
                        alert.resolved
                        and alert.resolved_at
                        and alert.resolved_at < cutoff_date
                    ):
                        alerts_to_remove.append(alert_id)

                for alert_id in alerts_to_remove:
                    del self._active_alerts[alert_id]

                if alerts_to_remove:
                    logger.info(f"Cleaned up {len(alerts_to_remove)} old alerts")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Alert cleanup error: {e}")

    async def _reset_event_counters(self) -> None:
        """Reset event counters periodically"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run hourly

                # Keep some history but reset high-frequency counters
                for event_type in list(self._event_counts.keys()):
                    if event_type in ["authentication_failure", "suspicious_activity"]:
                        self._event_counts[event_type] = max(
                            0, self._event_counts[event_type] - 10
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Counter reset error: {e}")

    async def _load_monitoring_data(self) -> None:
        """Load monitoring data from storage"""
        try:
            # Load active alerts
            async with aiofiles.open("data/security_alerts.json") as f:
                alerts_data = json.loads(await f.read())
                self._active_alerts = {}
                for alert_dict in alerts_data.get("alerts", []):
                    # Convert timestamp strings back to datetime
                    alert_dict["timestamp"] = datetime.fromisoformat(
                        alert_dict["timestamp"]
                    )
                    if alert_dict.get("resolved_at"):
                        alert_dict["resolved_at"] = datetime.fromisoformat(
                            alert_dict["resolved_at"]
                        )
                    self._active_alerts[alert_dict["id"]] = SecurityAlert(**alert_dict)

            # Load monitoring rules
            async with aiofiles.open("data/monitoring_rules.json") as f:
                rules_data = json.loads(await f.read())
                for rule_dict in rules_data.get("rules", []):
                    if rule_dict.get("last_triggered"):
                        rule_dict["last_triggered"] = datetime.fromisoformat(
                            rule_dict["last_triggered"]
                        )
                    rule = MonitoringRule(**rule_dict)
                    self._monitoring_rules[rule.id] = rule

            logger.info("Loaded monitoring data from storage")

        except FileNotFoundError:
            logger.info("No monitoring data files found, using defaults")
        except Exception as e:
            logger.error(f"Failed to load monitoring data: {e}")

    async def _save_monitoring_data(self) -> None:
        """Save monitoring data to storage"""
        try:
            # Save active alerts
            alerts_data = {
                "alerts": [
                    {
                        "id": alert.id,
                        "timestamp": alert.timestamp.isoformat(),
                        "event_type": alert.event_type,
                        "severity": alert.severity.value,
                        "title": alert.title,
                        "description": alert.description,
                        "details": alert.details,
                        "user_id": alert.user_id,
                        "ip_address": alert.ip_address,
                        "resolved": alert.resolved,
                        "resolved_at": alert.resolved_at.isoformat()
                        if alert.resolved_at
                        else None,
                        "resolution_notes": alert.resolution_notes,
                    }
                    for alert in self._active_alerts.values()
                ]
            }

            async with aiofiles.open("data/security_alerts.json", "w") as f:
                await f.write(json.dumps(alerts_data, indent=2))

            # Save monitoring rules
            rules_data = {
                "rules": [
                    {
                        "id": rule.id,
                        "name": rule.name,
                        "description": rule.description,
                        "event_pattern": rule.event_pattern,
                        "condition": rule.condition,
                        "severity": rule.severity.value,
                        "enabled": rule.enabled,
                        "cooldown_minutes": rule.cooldown_minutes,
                        "last_triggered": rule.last_triggered.isoformat()
                        if rule.last_triggered
                        else None,
                    }
                    for rule in self._monitoring_rules.values()
                ]
            }

            async with aiofiles.open("data/monitoring_rules.json", "w") as f:
                await f.write(json.dumps(rules_data, indent=2))

        except Exception as e:
            logger.error(f"Failed to save monitoring data: {e}")
