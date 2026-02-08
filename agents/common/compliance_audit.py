#!/usr/bin/env python3
"""
Compliance Audit Logging System

Comprehensive audit logging for GDPR/CCPA compliance. Tracks all data access,
modification, and deletion operations with detailed metadata.

Features:
- Structured audit log entries with timestamps
- User activity tracking
- Data access logging
- Compliance event logging
- Automated log rotation and retention
- Search and reporting capabilities
"""

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from common.observability import get_logger

logger = get_logger(__name__)


class AuditEventType(Enum):
    """Types of audit events"""

    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    DATA_DELETION = "data_deletion"
    DATA_EXPORT = "data_export"
    PERMISSION_CHANGE = "permission_change"
    COMPLIANCE_CHECK = "compliance_check"
    RETENTION_CLEANUP = "retention_cleanup"
    SECURITY_EVENT = "security_event"


class AuditEventSeverity(Enum):
    """Severity levels for audit events"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Audit event data structure"""

    event_id: str
    event_type: AuditEventType
    severity: AuditEventSeverity
    timestamp: datetime
    user_id: int | None
    user_email: str | None
    ip_address: str | None
    user_agent: str | None
    resource_type: str
    resource_id: str | None
    action: str
    details: dict[str, Any]
    compliance_relevant: bool = False
    gdpr_article: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage"""
        data = asdict(self)
        data["event_type"] = self.event_type.value
        data["severity"] = self.severity.value
        data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditEvent":
        """Create from dictionary"""
        data["event_type"] = AuditEventType(data["event_type"])
        data["severity"] = AuditEventSeverity(data["severity"])
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


class ComplianceAuditLogger:
    """
    Main audit logging system for compliance tracking

    Provides structured logging of all compliance-relevant events
    """

    def __init__(self, log_dir: str = "./logs/compliance_audit"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Current log file
        self.current_log_file = None
        self._rotate_log_file()

        logger.info("🛡️ Compliance Audit Logger initialized")

    def _rotate_log_file(self):
        """Rotate to a new log file if needed"""
        today = datetime.now().strftime("%Y%m%d")
        log_file = self.log_dir / f"audit_{today}.jsonl"

        if self.current_log_file != log_file:
            self.current_log_file = log_file
            logger.info(f"📝 Rotated to new audit log: {log_file}")

    def _write_audit_event(self, event: AuditEvent):
        """Write audit event to log file"""
        try:
            self._rotate_log_file()

            with open(self.current_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

        except Exception as e:
            logger.error(f"Failed to write audit event: {e}")

    def log_event(
        self,
        event_type: AuditEventType,
        severity: AuditEventSeverity,
        user_id: int | None = None,
        user_email: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        resource_type: str = "unknown",
        resource_id: str | None = None,
        action: str = "unknown",
        details: dict[str, Any] | None = None,
        compliance_relevant: bool = False,
        gdpr_article: str | None = None,
    ):
        """Log a compliance audit event"""
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            severity=severity,
            timestamp=datetime.now(),
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details=details or {},
            compliance_relevant=compliance_relevant,
            gdpr_article=gdpr_article,
        )

        self._write_audit_event(event)

        # Log critical events to main logger as well
        if severity in [AuditEventSeverity.HIGH, AuditEventSeverity.CRITICAL]:
            logger.warning(f"🚨 CRITICAL AUDIT EVENT: {event_type.value} - {action}")

    # Convenience methods for common events

    def log_user_login(
        self, user_id: int, user_email: str, ip_address: str, user_agent: str
    ):
        """Log user login event"""
        self.log_event(
            event_type=AuditEventType.USER_LOGIN,
            severity=AuditEventSeverity.LOW,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="user_account",
            resource_id=str(user_id),
            action="login",
            details={"login_method": "standard"},
        )

    def log_user_logout(self, user_id: int, user_email: str, ip_address: str):
        """Log user logout event"""
        self.log_event(
            event_type=AuditEventType.USER_LOGOUT,
            severity=AuditEventSeverity.LOW,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            resource_type="user_account",
            resource_id=str(user_id),
            action="logout",
        )

    def log_data_access(
        self,
        user_id: int,
        user_email: str,
        resource_type: str,
        resource_id: str,
        ip_address: str,
        details: dict[str, Any] = None,
    ):
        """Log data access event"""
        self.log_event(
            event_type=AuditEventType.DATA_ACCESS,
            severity=AuditEventSeverity.LOW,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            resource_type=resource_type,
            resource_id=resource_id,
            action="access",
            details=details,
        )

    def log_data_modification(
        self,
        user_id: int,
        user_email: str,
        resource_type: str,
        resource_id: str,
        action: str,
        ip_address: str,
        details: dict[str, Any] = None,
    ):
        """Log data modification event"""
        self.log_event(
            event_type=AuditEventType.DATA_MODIFICATION,
            severity=AuditEventSeverity.MEDIUM,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details=details,
        )

    def log_data_deletion(
        self,
        user_id: int,
        user_email: str,
        resource_type: str,
        resource_id: str,
        ip_address: str,
        gdpr_compliant: bool = True,
        details: dict[str, Any] = None,
    ):
        """Log data deletion event"""
        self.log_event(
            event_type=AuditEventType.DATA_DELETION,
            severity=AuditEventSeverity.HIGH,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            resource_type=resource_type,
            resource_id=resource_id,
            action="deletion",
            details=details,
            compliance_relevant=True,
            gdpr_article="17" if gdpr_compliant else None,
        )

    def log_data_export(
        self,
        user_id: int,
        user_email: str,
        export_id: str,
        ip_address: str,
        details: dict[str, Any] = None,
    ):
        """Log data export event"""
        self.log_event(
            event_type=AuditEventType.DATA_EXPORT,
            severity=AuditEventSeverity.MEDIUM,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            resource_type="user_data",
            resource_id=str(user_id),
            action="export",
            details={"export_id": export_id, **(details or {})},
            compliance_relevant=True,
            gdpr_article="20",
        )

    def log_retention_cleanup(
        self,
        data_type: str,
        records_deleted: int,
        cutoff_date: str,
        details: dict[str, Any] = None,
    ):
        """Log data retention cleanup event"""
        self.log_event(
            event_type=AuditEventType.RETENTION_CLEANUP,
            severity=AuditEventSeverity.MEDIUM,
            resource_type=data_type,
            action="retention_cleanup",
            details={
                "records_deleted": records_deleted,
                "cutoff_date": cutoff_date,
                **(details or {}),
            },
            compliance_relevant=True,
            gdpr_article="5",
        )

    def log_security_event(
        self,
        event_type: str,
        severity: AuditEventSeverity,
        user_id: int | None,
        ip_address: str,
        details: dict[str, Any] = None,
    ):
        """Log security-related event"""
        self.log_event(
            event_type=AuditEventType.SECURITY_EVENT,
            severity=severity,
            user_id=user_id,
            ip_address=ip_address,
            resource_type="security",
            action=event_type,
            details=details,
        )


class AuditLogAnalyzer:
    """
    Analyze audit logs for compliance reporting and investigations
    """

    def __init__(self, audit_logger: ComplianceAuditLogger):
        self.audit_logger = audit_logger

    def get_compliance_events(self, days: int = 30) -> list[dict[str, Any]]:
        """Get all compliance-relevant events from the last N days"""
        cutoff_date = datetime.now() - timedelta(days=days)
        events = []

        # Read all log files from the period
        for log_file in self.audit_logger.log_dir.glob("audit_*.jsonl"):
            try:
                with open(log_file, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            event_data = json.loads(line)
                            event = AuditEvent.from_dict(event_data)

                            if (
                                event.timestamp >= cutoff_date
                                and event.compliance_relevant
                            ):
                                events.append(event.to_dict())

            except Exception as e:
                logger.error(f"Error reading audit log {log_file}: {e}")

        return events

    def get_user_activity_report(self, user_id: int, days: int = 30) -> dict[str, Any]:
        """Generate activity report for a specific user"""
        cutoff_date = datetime.now() - timedelta(days=days)
        user_events = []

        # Read all log files from the period
        for log_file in self.audit_logger.log_dir.glob("audit_*.jsonl"):
            try:
                with open(log_file, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            event_data = json.loads(line)
                            event = AuditEvent.from_dict(event_data)

                            if (
                                event.timestamp >= cutoff_date
                                and event.user_id == user_id
                            ):
                                user_events.append(event.to_dict())

            except Exception as e:
                logger.error(f"Error reading audit log {log_file}: {e}")

        # Analyze events
        event_types = {}
        for event in user_events:
            event_type = event["event_type"]
            event_types[event_type] = event_types.get(event_type, 0) + 1

        return {
            "user_id": user_id,
            "report_period_days": days,
            "total_events": len(user_events),
            "event_types": event_types,
            "events": user_events[-50:],  # Last 50 events
            "generated_at": datetime.now().isoformat(),
        }

    def get_gdpr_compliance_summary(self, days: int = 90) -> dict[str, Any]:
        """Generate GDPR compliance summary"""
        events = self.get_compliance_events(days)

        summary = {
            "report_period_days": days,
            "total_compliance_events": len(events),
            "gdpr_articles_referenced": {},
            "event_types": {},
            "severity_distribution": {},
            "generated_at": datetime.now().isoformat(),
        }

        for event in events:
            # Count GDPR articles
            gdpr_article = event.get("gdpr_article")
            if gdpr_article:
                summary["gdpr_articles_referenced"][gdpr_article] = (
                    summary["gdpr_articles_referenced"].get(gdpr_article, 0) + 1
                )

            # Count event types
            event_type = event["event_type"]
            summary["event_types"][event_type] = (
                summary["event_types"].get(event_type, 0) + 1
            )

            # Count severity levels
            severity = event["severity"]
            summary["severity_distribution"][severity] = (
                summary["severity_distribution"].get(severity, 0) + 1
            )

        return summary


# Global audit logger instance
audit_logger = ComplianceAuditLogger()


async def demo_audit_logging():
    """Demonstrate audit logging capabilities"""

    print("🛡️ Compliance Audit Logging Demo")
    print("=" * 50)

    # Initialize audit logger
    logger = ComplianceAuditLogger()

    print("\n📝 Logging sample compliance events...")

    # Log various types of events
    logger.log_user_login(
        user_id=123,
        user_email="user@example.com",
        ip_address="192.168.1.100",
        user_agent="Mozilla/5.0...",
    )

    logger.log_data_export(
        user_id=123,
        user_email="user@example.com",
        export_id="export_12345",
        ip_address="192.168.1.100",
        details={"format": "json", "include_sensitive": False},
    )

    logger.log_data_deletion(
        user_id=123,
        user_email="user@example.com",
        resource_type="user_account",
        resource_id="123",
        ip_address="192.168.1.100",
        gdpr_compliant=True,
        details={"deletion_reason": "user_request"},
    )

    logger.log_retention_cleanup(
        data_type="user_sessions",
        records_deleted=150,
        cutoff_date="2024-01-01T00:00:00",
        details={"cleanup_method": "automatic"},
    )

    print("✅ Sample events logged")

    # Initialize analyzer
    analyzer = AuditLogAnalyzer(logger)

    print("\n📊 Generating compliance summary...")
    summary = analyzer.get_gdpr_compliance_summary(days=1)

    print("\n📋 GDPR Compliance Summary:")
    print(json.dumps(summary, indent=2, default=str))

    print("\n✅ Audit Logging Demo Complete!")
    print("\n🚀 Key Features:")
    print("   ✅ Structured audit event logging")
    print("   ✅ GDPR article tracking")
    print("   ✅ Compliance event analysis")
    print("   ✅ User activity reporting")
    print("   ✅ Automated log rotation")

    print("\n📋 Next Steps:")
    print("   1. Integrate with FastAPI endpoints")
    print("   2. Add real-time monitoring")
    print("   3. Implement log retention policies")
    print("   4. Add compliance dashboard")


if __name__ == "__main__":
    asyncio.run(demo_audit_logging())
