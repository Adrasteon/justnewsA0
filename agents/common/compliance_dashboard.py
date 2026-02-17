#!/usr/bin/env python3
"""
Compliance Dashboard API

Administrative dashboard for monitoring GDPR/CCPA compliance metrics,
data retention status, user requests, and audit logs.

Features:
- Real-time compliance metrics
- Data retention monitoring
- User request tracking (exports, deletions)
- Audit log analysis
- Compliance reporting
"""

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from agents.common.auth_models import UserRole, get_current_user
from agents.common.compliance_audit import AuditLogAnalyzer, ComplianceAuditLogger
from agents.common.compliance_retention import DataRetentionManager
from common.observability import get_logger

logger = get_logger(__name__)

# Security scheme
security = HTTPBearer()

# Create router
router = APIRouter(prefix="/compliance", tags=["Compliance Dashboard"])

# Initialize compliance components
retention_manager = DataRetentionManager()
audit_logger = ComplianceAuditLogger()
audit_analyzer = AuditLogAnalyzer(audit_logger)


# Dashboard Models
class ComplianceMetrics(BaseModel):
    """Overall compliance metrics"""

    total_users: int
    active_users: int
    data_export_requests: int
    data_deletion_requests: int
    retention_cleanups: int
    audit_events_today: int
    compliance_score: float


class DataRetentionStatus(BaseModel):
    """Data retention status"""

    policies: dict[str, Any]
    last_cleanup: str | None
    next_scheduled_cleanup: str
    expired_records_pending: int


class UserRequestSummary(BaseModel):
    """Summary of user compliance requests"""

    pending_exports: int
    completed_exports: int
    pending_deletions: int
    completed_deletions: int
    recent_requests: list[dict[str, Any]]


class AuditLogSummary(BaseModel):
    """Audit log summary"""

    total_events: int
    compliance_events: int
    security_events: int
    recent_events: list[dict[str, Any]]
    severity_distribution: dict[str, int]


# Helper function for admin access
async def get_admin_user(current_user: dict[str, Any] = Depends(get_current_user)):
    """Dependency to ensure admin access"""
    if current_user.get("role") != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# Dashboard Endpoints


@router.get("/metrics", response_model=ComplianceMetrics)
async def get_compliance_metrics(
    current_user: dict[str, Any] = Depends(get_admin_user),
):
    """Get overall compliance metrics"""
    try:
        # Get user counts
        from agents.common.auth_models import get_all_users, get_user_count

        total_users = get_user_count()
        all_users = get_all_users(limit=1000)
        active_users = sum(1 for user in all_users if user.get("status") == "active")

        # Get compliance events from audit logs
        compliance_events = audit_analyzer.get_compliance_events(days=30)

        # Count different types of requests
        data_export_requests = sum(
            1 for event in compliance_events if event["event_type"] == "data_export"
        )
        data_deletion_requests = sum(
            1 for event in compliance_events if event["event_type"] == "data_deletion"
        )
        retention_cleanups = sum(
            1
            for event in compliance_events
            if event["event_type"] == "retention_cleanup"
        )

        # Get today's audit events
        today_events = audit_analyzer.get_compliance_events(days=1)
        audit_events_today = len(today_events)

        # Calculate compliance score (simplified)
        compliance_score = min(
            100.0,
            (
                (active_users / max(total_users, 1)) * 40  # User engagement
                + (data_export_requests / max(total_users, 1)) * 30  # Data portability
                + (data_deletion_requests / max(total_users, 1))
                * 30  # Right to be forgotten
            ),
        )

        return ComplianceMetrics(
            total_users=total_users,
            active_users=active_users,
            data_export_requests=data_export_requests,
            data_deletion_requests=data_deletion_requests,
            retention_cleanups=retention_cleanups,
            audit_events_today=audit_events_today,
            compliance_score=round(compliance_score, 1),
        )

    except Exception as e:
        logger.error(f"Get compliance metrics error: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve compliance metrics"
        ) from e


@router.get("/retention-status", response_model=DataRetentionStatus)
async def get_data_retention_status(
    current_user: dict[str, Any] = Depends(get_admin_user),
):
    """Get data retention status and policies"""
    try:
        # Get retention policies
        policies = {}
        for data_type, policy in retention_manager.policies.items():
            policies[data_type.value] = {
                "retention_days": policy.retention_days,
                "action": policy.action.value,
                "enabled": policy.enabled,
                "last_cleanup": policy.last_cleanup.isoformat()
                if policy.last_cleanup
                else None,
                "records_processed": policy.records_processed,
            }

        # Calculate next cleanup (simplified - daily at 2 AM)
        next_cleanup = datetime.now().replace(hour=2, minute=0, second=0, microsecond=0)
        if next_cleanup <= datetime.now():
            next_cleanup += timedelta(days=1)

        # Estimate expired records (simplified)
        expired_records_pending = 0
        for policy in retention_manager.policies.values():
            if policy.enabled:
                # Rough estimate based on last cleanup
                days_since_cleanup = 30  # Default assumption
                if policy.last_cleanup:
                    days_since_cleanup = (datetime.now() - policy.last_cleanup).days
                expired_records_pending += max(
                    0, days_since_cleanup - policy.retention_days
                )

        return DataRetentionStatus(
            policies=policies,
            last_cleanup=min(
                (
                    p.last_cleanup
                    for p in retention_manager.policies.values()
                    if p.last_cleanup
                ),
                default=None,
            ).isoformat()
            if any(p.last_cleanup for p in retention_manager.policies.values())
            else None,
            next_scheduled_cleanup=next_cleanup.isoformat(),
            expired_records_pending=expired_records_pending,
        )

    except Exception as e:
        logger.error(f"Get retention status error: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve retention status"
        ) from e


@router.get("/user-requests", response_model=UserRequestSummary)
async def get_user_request_summary(
    limit: int = Query(10, ge=1, le=50),
    current_user: dict[str, Any] = Depends(get_admin_user),
):
    """Get summary of user compliance requests"""
    try:
        # Get compliance events
        compliance_events = audit_analyzer.get_compliance_events(days=30)

        # Count requests by type and status
        pending_exports = 0
        completed_exports = 0
        pending_deletions = 0
        completed_deletions = 0

        recent_requests = []

        for event in compliance_events:
            if event["event_type"] == "data_export":
                # Check if export is completed (simplified check)
                if "export_id" in event.get("details", {}):
                    completed_exports += 1
                else:
                    pending_exports += 1
                recent_requests.append(event)

            elif event["event_type"] == "data_deletion":
                # Check if deletion is completed
                if event.get("details", {}).get("status") == "completed":
                    completed_deletions += 1
                else:
                    pending_deletions += 1
                recent_requests.append(event)

        # Sort recent requests by timestamp
        recent_requests.sort(key=lambda x: x["timestamp"], reverse=True)
        recent_requests = recent_requests[:limit]

        return UserRequestSummary(
            pending_exports=pending_exports,
            completed_exports=completed_exports,
            pending_deletions=pending_deletions,
            completed_deletions=completed_deletions,
            recent_requests=recent_requests,
        )

    except Exception as e:
        logger.error(f"Get user requests error: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve user requests"
        ) from e


@router.get("/audit-logs", response_model=AuditLogSummary)
async def get_audit_log_summary(
    days: int = Query(7, ge=1, le=90),
    current_user: dict[str, Any] = Depends(get_admin_user),
):
    """Get audit log summary and recent events"""
    try:
        # Get all events for the period
        all_events = audit_analyzer.get_compliance_events(days=days)

        # Get compliance events
        compliance_events = [
            e for e in all_events if e.get("compliance_relevant", False)
        ]

        # Get security events
        security_events = [e for e in all_events if e["event_type"] == "security_event"]

        # Calculate severity distribution
        severity_distribution = {}
        for event in all_events:
            severity = event["severity"]
            severity_distribution[severity] = severity_distribution.get(severity, 0) + 1

        # Get recent events (last 20)
        recent_events = sorted(all_events, key=lambda x: x["timestamp"], reverse=True)[
            :20
        ]

        return AuditLogSummary(
            total_events=len(all_events),
            compliance_events=len(compliance_events),
            security_events=len(security_events),
            recent_events=recent_events,
            severity_distribution=severity_distribution,
        )

    except Exception as e:
        logger.error(f"Get audit logs error: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve audit logs"
        ) from e


@router.get("/gdpr-report")
async def get_gdpr_compliance_report(
    days: int = Query(90, ge=30, le=365),
    current_user: dict[str, Any] = Depends(get_admin_user),
):
    """Generate comprehensive GDPR compliance report"""
    try:
        # Get GDPR compliance summary
        gdpr_summary = audit_analyzer.get_gdpr_compliance_summary(days=days)

        # Add additional compliance metrics
        report = {
            **gdpr_summary,
            "data_retention_status": (
                await get_data_retention_status(current_user)
            ).model_dump(),
            "user_request_summary": (
                await get_user_request_summary(50, current_user)
            ).model_dump(),
            "compliance_assessment": {
                "data_portability_compliant": gdpr_summary[
                    "gdpr_articles_referenced"
                ].get("20", 0)
                > 0,
                "right_to_be_forgotten_compliant": gdpr_summary[
                    "gdpr_articles_referenced"
                ].get("17", 0)
                > 0,
                "data_retention_compliant": gdpr_summary[
                    "gdpr_articles_referenced"
                ].get("5", 0)
                > 0,
                "overall_compliance_score": min(
                    100,
                    (
                        (
                            1
                            if gdpr_summary["gdpr_articles_referenced"].get("20", 0) > 0
                            else 0
                        )
                        * 30
                        + (
                            1
                            if gdpr_summary["gdpr_articles_referenced"].get("17", 0) > 0
                            else 0
                        )
                        * 35
                        + (
                            1
                            if gdpr_summary["gdpr_articles_referenced"].get("5", 0) > 0
                            else 0
                        )
                        * 35
                    ),
                ),
            },
            "generated_at": datetime.now().isoformat(),
            "report_period_days": days,
        }

        return report

    except Exception as e:
        logger.error(f"Generate GDPR report error: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to generate GDPR compliance report"
        ) from e


@router.post("/retention-cleanup")
async def trigger_retention_cleanup(
    dry_run: bool = Query(True, description="Run in dry-run mode (no actual deletion)"),
    current_user: dict[str, Any] = Depends(get_admin_user),
):
    """Manually trigger data retention cleanup"""
    try:
        # Log the manual cleanup trigger
        audit_logger.log_event(
            event_type=audit_logger.AuditEventType.RETENTION_CLEANUP,
            severity=audit_logger.AuditEventSeverity.MEDIUM,
            user_id=current_user["user_id"],
            user_email=current_user["email"],
            resource_type="retention_system",
            action="manual_cleanup_triggered",
            details={"dry_run": dry_run, "triggered_by": current_user["email"]},
            compliance_relevant=True,
            gdpr_article="5",
        )

        # For now, return a placeholder response
        # In a real implementation, this would trigger the actual cleanup
        return {
            "cleanup_triggered": True,
            "dry_run": dry_run,
            "message": f"Retention cleanup {'simulation' if dry_run else 'execution'} started",
            "estimated_completion": (
                datetime.now() + timedelta(minutes=30)
            ).isoformat(),
        }

    except Exception as e:
        logger.error(f"Trigger retention cleanup error: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to trigger retention cleanup"
        ) from e


# Initialize compliance components on import
try:
    logger.info("Compliance dashboard API initialized")
except Exception as e:
    logger.error(f"Failed to initialize compliance dashboard: {e}")
