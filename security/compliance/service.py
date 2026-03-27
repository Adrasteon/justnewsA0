"""
JustNews Compliance Service

Handles GDPR, CCPA compliance, audit trails, data protection, and regulatory requirements.
"""

import asyncio
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import aiofiles
from pydantic import BaseModel, Field

from ..models import ComplianceError, SecurityConfig

logger = logging.getLogger(__name__)


class ComplianceStandard(Enum):
    """Supported compliance standards"""

    GDPR = "gdpr"
    CCPA = "ccpa"
    HIPAA = "hipaa"
    SOX = "sox"


class DataProcessingPurpose(Enum):
    """Data processing purposes"""

    NEWS_ANALYSIS = "news_analysis"
    USER_PROFILES = "user_profiles"
    CONTENT_MODERATION = "content_moderation"
    ANALYTICS = "analytics"
    MARKETING = "marketing"
    LEGAL_COMPLIANCE = "legal_compliance"


class ConsentStatus(Enum):
    """Consent status"""

    GRANTED = "granted"
    DENIED = "denied"
    WITHDRAWN = "withdrawn"
    PENDING = "pending"


class AuditEvent(BaseModel):
    """Audit event for compliance logging"""

    id: str
    timestamp: datetime
    user_id: int | None = None
    action: str
    resource: str
    details: dict[str, Any] = Field(default_factory=dict)
    ip_address: str | None = None
    user_agent: str | None = None
    compliance_standard: str | None = None


class DataSubjectRequest(BaseModel):
    """Data subject access request (GDPR Article 15-22)"""

    id: str
    user_id: int
    request_type: str  # access, rectify, erase, restrict, portability, object
    status: str  # pending, in_progress, completed, rejected
    requested_at: datetime
    completed_at: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ConsentRecord(BaseModel):
    """User consent record"""

    id: str
    user_id: int
    purpose: str
    status: ConsentStatus
    granted_at: datetime | None = None
    withdrawn_at: datetime | None = None
    consent_text: str
    ip_address: str | None = None
    user_agent: str | None = None


class DataRetentionPolicy(BaseModel):
    """Data retention policy"""

    data_type: str
    retention_period_days: int
    deletion_method: str  # delete, anonymize, archive
    compliance_standard: str
    legal_basis: str
    description: str


@dataclass
class ComplianceConfig:
    """Compliance service configuration"""

    enabled_standards: list[str] = None  # ["gdpr", "ccpa"]
    audit_retention_days: int = 2555  # 7 years for GDPR
    consent_retention_days: int = 2555
    data_export_format: str = "json"
    automatic_cleanup: bool = True
    dpo_contact_email: str | None = None

    def __post_init__(self):
        if self.enabled_standards is None:
            self.enabled_standards = ["gdpr"]


class ComplianceService:
    """
    Compliance service for regulatory requirements

    Handles GDPR, CCPA compliance, audit trails, data subject rights,
    consent management, and regulatory reporting.
    """

    def __init__(self, config: SecurityConfig):
        self.config = config
        self.compliance_config = ComplianceConfig()
        self._audit_events: list[AuditEvent] = []
        self._consent_records: dict[
            int, list[ConsentRecord]
        ] = {}  # user_id -> consents
        self._data_requests: list[DataSubjectRequest] = []
        self._retention_policies = self._get_default_retention_policies()

    def _get_default_retention_policies(self) -> dict[str, DataRetentionPolicy]:
        """Get default data retention policies"""
        return {
            "user_profile": DataRetentionPolicy(
                data_type="user_profile",
                retention_period_days=2555,  # 7 years
                deletion_method="delete",
                compliance_standard="gdpr",
                legal_basis="contract",
                description="User profile and account data",
            ),
            "user_content": DataRetentionPolicy(
                data_type="user_content",
                retention_period_days=365,  # 1 year
                deletion_method="anonymize",
                compliance_standard="gdpr",
                legal_basis="legitimate_interest",
                description="User-generated content and interactions",
            ),
            "analytics": DataRetentionPolicy(
                data_type="analytics",
                retention_period_days=730,  # 2 years
                deletion_method="aggregate",
                compliance_standard="gdpr",
                legal_basis="legitimate_interest",
                description="Analytics and usage data",
            ),
            "audit_logs": DataRetentionPolicy(
                data_type="audit_logs",
                retention_period_days=2555,  # 7 years
                deletion_method="archive",
                compliance_standard="gdpr",
                legal_basis="legal_obligation",
                description="Security and audit logs",
            ),
            "consent_records": DataRetentionPolicy(
                data_type="consent_records",
                retention_period_days=2555,  # 7 years
                deletion_method="delete",
                compliance_standard="gdpr",
                legal_basis="legal_obligation",
                description="Consent and preference records",
            ),
        }

    async def initialize(self) -> None:
        """Initialize compliance service"""
        await self._load_compliance_data()
        await self._schedule_cleanup_tasks()
        logger.info("ComplianceService initialized")

    async def shutdown(self) -> None:
        """Shutdown compliance service"""
        await self._save_compliance_data()
        logger.info("ComplianceService shutdown")

    async def log_event(
        self, event_type: str, user_id: int | None, details: dict[str, Any]
    ) -> None:
        """
        Log compliance audit event

        Args:
            event_type: Type of event (e.g., "data_access", "consent_granted")
            user_id: Optional user ID
            details: Event details
        """
        try:
            audit_event = AuditEvent(
                id=f"audit_{datetime.now(UTC).timestamp()}_{secrets.token_hex(4)}",
                timestamp=datetime.now(UTC),
                user_id=user_id,
                action=event_type,
                resource=details.get("resource", "unknown"),
                details=details,
                ip_address=details.get("ip_address"),
                user_agent=details.get("user_agent"),
                compliance_standard=self._determine_compliance_standard(event_type),
            )

            self._audit_events.append(audit_event)

            # Keep only recent events in memory
            if len(self._audit_events) > 10000:
                self._audit_events = self._audit_events[-5000:]

            logger.info(f"Logged compliance event: {event_type} for user {user_id}")

        except Exception as e:
            logger.error(f"Failed to log compliance event: {e}")

    async def record_consent(
        self,
        user_id: int,
        purpose: str,
        consent_text: str,
        status: ConsentStatus = ConsentStatus.GRANTED,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> str:
        """
        Record user consent

        Args:
            user_id: User ID
            purpose: Consent purpose
            consent_text: Consent text shown to user
            status: Consent status
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Consent record ID
        """
        try:
            consent_id = (
                f"consent_{datetime.now(UTC).timestamp()}_{secrets.token_hex(4)}"
            )

            consent = ConsentRecord(
                id=consent_id,
                user_id=user_id,
                purpose=purpose,
                status=status,
                consent_text=consent_text,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            if status == ConsentStatus.GRANTED:
                consent.granted_at = datetime.now(UTC)
            elif status == ConsentStatus.WITHDRAWN:
                consent.withdrawn_at = datetime.now(UTC)

            if user_id not in self._consent_records:
                self._consent_records[user_id] = []

            self._consent_records[user_id].append(consent)

            # Log consent event
            await self.log_event(
                "consent_recorded",
                user_id,
                {
                    "consent_id": consent_id,
                    "purpose": purpose,
                    "status": status.value,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                },
            )

            logger.info(
                f"Recorded consent for user {user_id}: {purpose} - {status.value}"
            )
            return consent_id

        except Exception as e:
            logger.error(f"Failed to record consent: {e}")
            raise ComplianceError(f"Consent recording failed: {str(e)}") from e

    async def check_consent(self, user_id: int, purpose: str) -> ConsentStatus:
        """
        Check user consent status for a purpose

        Args:
            user_id: User ID
            purpose: Consent purpose

        Returns:
            Current consent status
        """
        if user_id not in self._consent_records:
            return ConsentStatus.PENDING

        consents = self._consent_records[user_id]
        relevant_consents = [c for c in consents if c.purpose == purpose]

        if not relevant_consents:
            return ConsentStatus.PENDING

        # Get most recent consent
        latest_consent = max(
            relevant_consents, key=lambda c: c.granted_at or datetime.min
        )

        # Check if consent is still valid
        if latest_consent.status == ConsentStatus.WITHDRAWN:
            return ConsentStatus.WITHDRAWN

        return latest_consent.status

    async def submit_data_request(
        self, user_id: int, request_type: str, details: dict[str, Any] = None
    ) -> str:
        """
        Submit data subject access request

        Args:
            user_id: User ID making the request
            request_type: Type of request (access, rectify, erase, restrict, portability, object)
            details: Additional request details

        Returns:
            Request ID
        """
        try:
            request_id = f"dsr_{datetime.now(UTC).timestamp()}_{secrets.token_hex(4)}"

            request = DataSubjectRequest(
                id=request_id,
                user_id=user_id,
                request_type=request_type,
                status="pending",
                requested_at=datetime.now(UTC),
                details=details or {},
            )

            self._data_requests.append(request)

            # Log data request event
            await self.log_event(
                "data_subject_request",
                user_id,
                {
                    "request_id": request_id,
                    "request_type": request_type,
                    "details": details,
                },
            )

            logger.info(
                f"Submitted data request {request_id} for user {user_id}: {request_type}"
            )
            return request_id

        except Exception as e:
            logger.error(f"Failed to submit data request: {e}")
            raise ComplianceError(f"Data request submission failed: {str(e)}") from e

    async def process_data_request(
        self, request_id: str, action: str, result: dict[str, Any] = None
    ) -> None:
        """
        Process data subject request

        Args:
            request_id: Request ID
            action: Action taken (approve, reject, complete)
            result: Processing result
        """
        try:
            request = None
            for req in self._data_requests:
                if req.id == request_id:
                    request = req
                    break

            if not request:
                raise ComplianceError(f"Data request {request_id} not found")

            if action == "approve":
                request.status = "in_progress"
            elif action == "complete":
                request.status = "completed"
                request.completed_at = datetime.now(UTC)
            elif action == "reject":
                request.status = "rejected"
                request.completed_at = datetime.now(UTC)

            # Log processing event
            await self.log_event(
                "data_request_processed",
                request.user_id,
                {"request_id": request_id, "action": action, "result": result},
            )

            await self._save_compliance_data()
            logger.info(f"Processed data request {request_id}: {action}")

        except Exception as e:
            logger.error(f"Failed to process data request: {e}")
            raise ComplianceError(f"Data request processing failed: {str(e)}") from e

    async def export_user_data(self, user_id: int) -> dict[str, Any]:
        """
        Export all user data for GDPR Article 15 compliance

        Args:
            user_id: User ID

        Returns:
            Complete user data export
        """
        try:
            # This would integrate with other services to gather all user data
            # For now, return compliance-related data
            export_data = {
                "user_id": user_id,
                "export_timestamp": datetime.now(UTC).isoformat(),
                "consent_records": [
                    {
                        "id": c.id,
                        "purpose": c.purpose,
                        "status": c.status.value,
                        "granted_at": c.granted_at.isoformat()
                        if c.granted_at
                        else None,
                        "withdrawn_at": c.withdrawn_at.isoformat()
                        if c.withdrawn_at
                        else None,
                        "consent_text": c.consent_text,
                    }
                    for c in self._consent_records.get(user_id, [])
                ],
                "audit_events": [
                    {
                        "id": e.id,
                        "timestamp": e.timestamp.isoformat(),
                        "action": e.action,
                        "resource": e.resource,
                        "details": e.details,
                    }
                    for e in self._audit_events
                    if e.user_id == user_id
                ],
                "data_requests": [
                    {
                        "id": r.id,
                        "request_type": r.request_type,
                        "status": r.status,
                        "requested_at": r.requested_at.isoformat(),
                        "completed_at": r.completed_at.isoformat()
                        if r.completed_at
                        else None,
                        "details": r.details,
                    }
                    for r in self._data_requests
                    if r.user_id == user_id
                ],
            }

            # Log data export
            await self.log_event(
                "data_export",
                user_id,
                {"export_format": self.compliance_config.data_export_format},
            )

            logger.info(f"Exported data for user {user_id}")
            return export_data

        except Exception as e:
            logger.error(f"Failed to export user data: {e}")
            raise ComplianceError(f"Data export failed: {str(e)}") from e

    async def delete_user_data(self, user_id: int) -> None:
        """
        Delete all user data for GDPR Article 17 compliance

        Args:
            user_id: User ID
        """
        try:
            # Remove consent records
            if user_id in self._consent_records:
                del self._consent_records[user_id]

            # Remove data requests
            self._data_requests = [
                r for r in self._data_requests if r.user_id != user_id
            ]

            # Note: Audit events are retained for compliance reasons
            # They would be anonymized or archived according to retention policy

            # Log data deletion
            await self.log_event(
                "data_deletion", user_id, {"deletion_type": "right_to_be_forgotten"}
            )

            await self._save_compliance_data()
            logger.info(f"Deleted data for user {user_id}")

        except Exception as e:
            logger.error(f"Failed to delete user data: {e}")
            raise ComplianceError(f"Data deletion failed: {str(e)}") from e

    async def get_compliance_report(
        self,
        standard: str = "gdpr",
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Generate compliance report

        Args:
            standard: Compliance standard (gdpr, ccpa)
            date_from: Report start date
            date_to: Report end date

        Returns:
            Compliance report data
        """
        try:
            if date_from is None:
                date_from = datetime.now(UTC) - timedelta(days=30)
            if date_to is None:
                date_to = datetime.now(UTC)

            # Filter events by date and standard
            relevant_events = [
                e
                for e in self._audit_events
                if (
                    date_from <= e.timestamp <= date_to
                    and (e.compliance_standard == standard or not e.compliance_standard)
                )
            ]

            # Generate report
            report = {
                "standard": standard,
                "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
                "summary": {
                    "total_events": len(relevant_events),
                    "data_requests": len(
                        [
                            e
                            for e in relevant_events
                            if e.action == "data_subject_request"
                        ]
                    ),
                    "consent_changes": len(
                        [e for e in relevant_events if "consent" in e.action]
                    ),
                    "data_exports": len(
                        [e for e in relevant_events if e.action == "data_export"]
                    ),
                    "data_deletions": len(
                        [e for e in relevant_events if e.action == "data_deletion"]
                    ),
                },
                "events": [
                    {
                        "id": e.id,
                        "timestamp": e.timestamp.isoformat(),
                        "user_id": e.user_id,
                        "action": e.action,
                        "resource": e.resource,
                        "details": e.details,
                    }
                    for e in relevant_events[-1000:]  # Last 1000 events
                ],
            }

            logger.info(f"Generated {standard} compliance report")
            return report

        except Exception as e:
            logger.error(f"Failed to generate compliance report: {e}")
            raise ComplianceError(f"Report generation failed: {str(e)}") from e

    async def get_status(self) -> dict[str, Any]:
        """
        Get compliance service status

        Returns:
            Status information
        """
        pending_requests = len(
            [r for r in self._data_requests if r.status == "pending"]
        )
        active_consents = sum(
            len(consents) for consents in self._consent_records.values()
        )

        return {
            "status": "healthy",
            "enabled_standards": self.compliance_config.enabled_standards,
            "audit_events": len(self._audit_events),
            "pending_data_requests": pending_requests,
            "active_consents": active_consents,
            "retention_policies": len(self._retention_policies),
        }

    def _determine_compliance_standard(self, event_type: str) -> str | None:
        """Determine which compliance standard applies to an event"""
        gdpr_events = [
            "data_access",
            "data_rectification",
            "data_erasure",
            "data_restriction",
            "data_portability",
            "consent_granted",
            "consent_withdrawn",
            "data_export",
            "data_deletion",
            "data_subject_request",
        ]

        ccpa_events = [
            "data_sale_opt_out",
            "data_deletion_request",
            "data_portability_request",
        ]

        if event_type in gdpr_events:
            return "gdpr"
        elif event_type in ccpa_events:
            return "ccpa"

        return None

    async def _schedule_cleanup_tasks(self) -> None:
        """Schedule automatic cleanup tasks"""
        if not self.compliance_config.automatic_cleanup:
            return

        # Cleanup old audit events
        asyncio.create_task(self._cleanup_old_events())

        # Cleanup expired consents
        asyncio.create_task(self._cleanup_expired_consents())

    async def _cleanup_old_events(self) -> None:
        """Cleanup old audit events based on retention policy"""
        while True:
            try:
                await asyncio.sleep(86400)  # Run daily

                cutoff_date = datetime.now(UTC) - timedelta(
                    days=self.compliance_config.audit_retention_days
                )

                old_count = len(self._audit_events)
                self._audit_events = [
                    e for e in self._audit_events if e.timestamp > cutoff_date
                ]

                removed_count = old_count - len(self._audit_events)
                if removed_count > 0:
                    logger.info(f"Cleaned up {removed_count} old audit events")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Audit cleanup error: {e}")

    async def _cleanup_expired_consents(self) -> None:
        """Cleanup expired consent records"""
        while True:
            try:
                await asyncio.sleep(86400)  # Run daily

                cutoff_date = datetime.now(UTC) - timedelta(
                    days=self.compliance_config.consent_retention_days
                )

                for user_id in list(self._consent_records.keys()):
                    consents = self._consent_records[user_id]
                    active_consents = [
                        c
                        for c in consents
                        if (c.granted_at and c.granted_at > cutoff_date)
                        or (c.withdrawn_at and c.withdrawn_at > cutoff_date)
                    ]

                    if not active_consents:
                        del self._consent_records[user_id]
                    else:
                        self._consent_records[user_id] = active_consents

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consent cleanup error: {e}")

    async def _load_compliance_data(self) -> None:
        """Load compliance data from storage"""
        try:
            # Load audit events
            async with aiofiles.open("data/compliance_audit.json") as f:
                audit_data = json.loads(await f.read())
                self._audit_events = [
                    AuditEvent(**event) for event in audit_data.get("events", [])
                ]

            # Load consent records
            async with aiofiles.open("data/compliance_consent.json") as f:
                consent_data = json.loads(await f.read())
                self._consent_records = {}
                for user_id_str, consents in consent_data.get("consents", {}).items():
                    user_id = int(user_id_str)
                    self._consent_records[user_id] = [
                        ConsentRecord(**consent) for consent in consents
                    ]

            # Load data requests
            async with aiofiles.open("data/compliance_requests.json") as f:
                request_data = json.loads(await f.read())
                self._data_requests = [
                    DataSubjectRequest(**request)
                    for request in request_data.get("requests", [])
                ]

            logger.info("Loaded compliance data from storage")

        except FileNotFoundError:
            logger.info("No compliance data files found, starting fresh")
        except Exception as e:
            logger.error(f"Failed to load compliance data: {e}")

    async def _save_compliance_data(self) -> None:
        """Save compliance data to storage"""
        try:
            # Save audit events
            audit_data = {
                "events": [
                    {
                        "id": e.id,
                        "timestamp": e.timestamp.isoformat(),
                        "user_id": e.user_id,
                        "action": e.action,
                        "resource": e.resource,
                        "details": e.details,
                        "ip_address": e.ip_address,
                        "user_agent": e.user_agent,
                        "compliance_standard": e.compliance_standard,
                    }
                    for e in self._audit_events[-5000:]  # Keep last 5000 events
                ]
            }

            async with aiofiles.open("data/compliance_audit.json", "w") as f:
                await f.write(json.dumps(audit_data, indent=2))

            # Save consent records
            consent_data = {
                "consents": {
                    str(user_id): [
                        {
                            "id": c.id,
                            "user_id": c.user_id,
                            "purpose": c.purpose,
                            "status": c.status.value,
                            "granted_at": c.granted_at.isoformat()
                            if c.granted_at
                            else None,
                            "withdrawn_at": c.withdrawn_at.isoformat()
                            if c.withdrawn_at
                            else None,
                            "consent_text": c.consent_text,
                            "ip_address": c.ip_address,
                            "user_agent": c.user_agent,
                        }
                        for c in consents
                    ]
                    for user_id, consents in self._consent_records.items()
                }
            }

            async with aiofiles.open("data/compliance_consent.json", "w") as f:
                await f.write(json.dumps(consent_data, indent=2))

            # Save data requests
            request_data = {
                "requests": [
                    {
                        "id": r.id,
                        "user_id": r.user_id,
                        "request_type": r.request_type,
                        "status": r.status,
                        "requested_at": r.requested_at.isoformat(),
                        "completed_at": r.completed_at.isoformat()
                        if r.completed_at
                        else None,
                        "details": r.details,
                    }
                    for r in self._data_requests
                ]
            }

            async with aiofiles.open("data/compliance_requests.json", "w") as f:
                await f.write(json.dumps(request_data, indent=2))

        except Exception as e:
            logger.error(f"Failed to save compliance data: {e}")
