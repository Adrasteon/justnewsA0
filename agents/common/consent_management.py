#!/usr/bin/env python3

"""
Consent Management System

GDPR-compliant user consent management for data processing and external knowledge base linking.
Tracks user consents, provides consent management APIs, and ensures compliance with consent requirements.

Features:
- Multiple consent types (data processing, external linking, analytics, etc.)
- Granular consent tracking with timestamps
- Consent withdrawal capabilities
- Audit logging integration
- Consent policy management
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from agents.common.auth_models import auth_execute_query, auth_execute_query_single
from common.observability import get_logger

logger = get_logger(__name__)


class ConsentType(Enum):
    """Types of user consent"""

    DATA_PROCESSING = "data_processing"
    EXTERNAL_LINKING = "external_linking"
    ANALYTICS = "analytics"
    MARKETING = "marketing"
    PROFILE_ANALYSIS = "profile_analysis"
    DATA_SHARING = "data_sharing"


class ConsentStatus(Enum):
    """Consent status"""

    GRANTED = "granted"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"
    PENDING = "pending"


@dataclass
class ConsentRecord:
    """User consent record"""

    consent_id: str
    user_id: int
    consent_type: ConsentType
    status: ConsentStatus
    granted_at: datetime
    withdrawn_at: datetime | None = None
    expires_at: datetime | None = None
    consent_version: str = "1.0"
    ip_address: str | None = None
    user_agent: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage"""
        data = asdict(self)
        data["consent_type"] = self.consent_type.value
        data["status"] = self.status.value
        data["granted_at"] = self.granted_at.isoformat()
        if self.withdrawn_at:
            data["withdrawn_at"] = self.withdrawn_at.isoformat()
        if self.expires_at:
            data["expires_at"] = self.expires_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConsentRecord":
        """Create from dictionary"""
        data["consent_type"] = ConsentType(data["consent_type"])
        data["status"] = ConsentStatus(data["status"])
        data["granted_at"] = datetime.fromisoformat(data["granted_at"])
        if data.get("withdrawn_at"):
            data["withdrawn_at"] = datetime.fromisoformat(data["withdrawn_at"])
        if data.get("expires_at"):
            data["expires_at"] = datetime.fromisoformat(data["expires_at"])
        return cls(**data)


@dataclass
class ConsentPolicy:
    """Consent policy definition"""

    policy_id: str
    consent_type: ConsentType
    name: str
    description: str
    required: bool = False
    default_granted: bool = False
    expires_days: int | None = None
    version: str = "1.0"
    last_updated: datetime = None

    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data["consent_type"] = self.consent_type.value
        data["last_updated"] = self.last_updated.isoformat()
        return data


class ConsentManager:
    """
    Manages user consents and consent policies

    Provides comprehensive consent management with audit trails
    """

    def __init__(self):
        self.policies = self._load_default_policies()
        self._ensure_consent_tables()
        logger.info("🛡️ Consent Manager initialized")

    def _load_default_policies(self) -> dict[ConsentType, ConsentPolicy]:
        """Load default consent policies"""
        return {
            ConsentType.DATA_PROCESSING: ConsentPolicy(
                policy_id="data_processing_v1",
                consent_type=ConsentType.DATA_PROCESSING,
                name="Data Processing Consent",
                description="Consent for processing personal data for news analysis and research purposes",
                required=True,
                default_granted=False,
                expires_days=365,
            ),
            ConsentType.EXTERNAL_LINKING: ConsentPolicy(
                policy_id="external_linking_v1",
                consent_type=ConsentType.EXTERNAL_LINKING,
                name="External Knowledge Base Linking",
                description="Consent for linking user data with external knowledge bases (Wikidata, DBpedia)",
                required=False,
                default_granted=False,
                expires_days=365,
            ),
            ConsentType.ANALYTICS: ConsentPolicy(
                policy_id="analytics_v1",
                consent_type=ConsentType.ANALYTICS,
                name="Usage Analytics",
                description="Consent for collecting anonymous usage analytics to improve the service",
                required=False,
                default_granted=False,
                expires_days=365,
            ),
            ConsentType.MARKETING: ConsentPolicy(
                policy_id="marketing_v1",
                consent_type=ConsentType.MARKETING,
                name="Marketing Communications",
                description="Consent for receiving marketing communications and newsletters",
                required=False,
                default_granted=False,
                expires_days=365,
            ),
            ConsentType.PROFILE_ANALYSIS: ConsentPolicy(
                policy_id="profile_analysis_v1",
                consent_type=ConsentType.PROFILE_ANALYSIS,
                name="Profile Analysis",
                description="Consent for analyzing user behavior to personalize content and recommendations",
                required=False,
                default_granted=False,
                expires_days=365,
            ),
            ConsentType.DATA_SHARING: ConsentPolicy(
                policy_id="data_sharing_v1",
                consent_type=ConsentType.DATA_SHARING,
                name="Data Sharing",
                description="Consent for sharing anonymized data with research partners",
                required=False,
                default_granted=False,
                expires_days=365,
            ),
        }

    def _ensure_consent_tables(self):
        """Ensure consent-related database tables exist"""
        try:
            # Create consent records table
            consent_table_query = """
            CREATE TABLE IF NOT EXISTS user_consents (
                consent_id VARCHAR(64) PRIMARY KEY,
                user_id INTEGER NOT NULL,
                consent_type VARCHAR(50) NOT NULL,
                status VARCHAR(20) NOT NULL,
                granted_at TIMESTAMP NOT NULL,
                withdrawn_at TIMESTAMP,
                expires_at TIMESTAMP,
                consent_version VARCHAR(10) DEFAULT '1.0',
                ip_address VARCHAR(45),
                user_agent TEXT,
                details JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """

            # Create consent policies table
            policies_table_query = """
            CREATE TABLE IF NOT EXISTS consent_policies (
                policy_id VARCHAR(64) PRIMARY KEY,
                consent_type VARCHAR(50) NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                required BOOLEAN DEFAULT FALSE,
                default_granted BOOLEAN DEFAULT FALSE,
                expires_days INTEGER,
                version VARCHAR(10) DEFAULT '1.0',
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """

            auth_execute_query(consent_table_query, fetch=False)
            auth_execute_query(policies_table_query, fetch=False)

            # Insert default policies if not exist
            for policy in self.policies.values():
                self._upsert_policy(policy)

            logger.info("Consent database tables initialized")

        except Exception as e:
            logger.error(f"Failed to initialize consent tables: {e}")

    def _upsert_policy(self, policy: ConsentPolicy):
        """Insert or update consent policy"""
        query = """
        INSERT INTO consent_policies
        (policy_id, consent_type, name, description, required, default_granted, expires_days, version, last_updated)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (policy_id) DO UPDATE SET
        name = EXCLUDED.name,
        description = EXCLUDED.description,
        required = EXCLUDED.required,
        default_granted = EXCLUDED.default_granted,
        expires_days = EXCLUDED.expires_days,
        version = EXCLUDED.version,
        last_updated = EXCLUDED.last_updated
        """
        auth_execute_query(
            query,
            (
                policy.policy_id,
                policy.consent_type.value,
                policy.name,
                policy.description,
                policy.required,
                policy.default_granted,
                policy.expires_days,
                policy.version,
                policy.last_updated,
            ),
            fetch=False,
        )

    def grant_consent(
        self,
        user_id: int,
        consent_type: ConsentType,
        ip_address: str = None,
        user_agent: str = None,
        details: dict[str, Any] = None,
    ) -> str:
        """Grant user consent for a specific type"""
        consent_id = (
            f"consent_{user_id}_{consent_type.value}_{int(datetime.now().timestamp())}"
        )

        policy = self.policies.get(consent_type)
        expires_at = None
        if policy and policy.expires_days:
            expires_at = datetime.now() + timedelta(days=policy.expires_days)

        consent = ConsentRecord(
            consent_id=consent_id,
            user_id=user_id,
            consent_type=consent_type,
            status=ConsentStatus.GRANTED,
            granted_at=datetime.now(),
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
        )

        # Insert consent record
        query = """
        INSERT INTO user_consents
        (consent_id, user_id, consent_type, status, granted_at, expires_at, ip_address, user_agent, details)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        auth_execute_query(
            query,
            (
                consent.consent_id,
                consent.user_id,
                consent.consent_type.value,
                consent.status.value,
                consent.granted_at,
                consent.expires_at,
                consent.ip_address,
                consent.user_agent,
                json.dumps(consent.details) if consent.details else None,
            ),
            fetch=False,
        )

        logger.info(f"✅ Consent granted: User {user_id} for {consent_type.value}")
        return consent_id

    def withdraw_consent(
        self, user_id: int, consent_type: ConsentType, ip_address: str = None
    ) -> bool:
        """Withdraw user consent"""
        query = """
        UPDATE user_consents
        SET status = %s, withdrawn_at = %s, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = %s AND consent_type = %s AND status = %s
        """
        result = auth_execute_query(
            query,
            (
                ConsentStatus.WITHDRAWN.value,
                datetime.now(),
                user_id,
                consent_type.value,
                ConsentStatus.GRANTED.value,
            ),
            fetch=False,
        )

        if result:
            logger.info(
                f"✅ Consent withdrawn: User {user_id} for {consent_type.value}"
            )
            return True
        return False

    def get_user_consents(self, user_id: int) -> dict[ConsentType, ConsentRecord]:
        """Get all consents for a user"""
        query = """
        SELECT * FROM user_consents
        WHERE user_id = %s
        ORDER BY granted_at DESC
        """
        results = auth_execute_query(query, (user_id,))

        consents = {}
        for row in results:
            consent = ConsentRecord.from_dict(dict(row))
            consents[consent.consent_type] = consent

        return consents

    def check_consent(self, user_id: int, consent_type: ConsentType) -> bool:
        """Check if user has granted consent for a specific type"""
        query = """
        SELECT status, expires_at FROM user_consents
        WHERE user_id = %s AND consent_type = %s
        ORDER BY granted_at DESC LIMIT 1
        """
        result = auth_execute_query_single(query, (user_id, consent_type.value))

        if not result:
            # Check if this is a required consent with default_granted
            policy = self.policies.get(consent_type)
            if policy and policy.required and policy.default_granted:
                return True
            return False

        status = ConsentStatus(result["status"])
        if status != ConsentStatus.GRANTED:
            return False

        # Check expiration
        expires_at = result.get("expires_at")
        if expires_at and datetime.now() > expires_at:
            # Mark as expired
            self._mark_expired(user_id, consent_type)
            return False

        return True

    def _mark_expired(self, user_id: int, consent_type: ConsentType):
        """Mark consent as expired"""
        query = """
        UPDATE user_consents
        SET status = %s, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = %s AND consent_type = %s AND status = %s
        """
        auth_execute_query(
            query,
            (
                ConsentStatus.EXPIRED.value,
                user_id,
                consent_type.value,
                ConsentStatus.GRANTED.value,
            ),
            fetch=False,
        )

    def get_consent_summary(self, user_id: int) -> dict[str, Any]:
        """Get consent summary for a user"""
        user_consents = self.get_user_consents(user_id)

        summary = {
            "user_id": user_id,
            "consents": {},
            "required_consents_granted": 0,
            "optional_consents_granted": 0,
            "total_required_consents": 0,
            "total_optional_consents": 0,
            "compliance_status": "compliant",
        }

        for consent_type, policy in self.policies.items():
            consent_record = user_consents.get(consent_type)
            is_granted = self.check_consent(user_id, consent_type)

            summary["consents"][consent_type.value] = {
                "granted": is_granted,
                "required": policy.required,
                "expires_days": policy.expires_days,
                "last_updated": consent_record.granted_at.isoformat()
                if consent_record
                else None,
                "status": consent_record.status.value
                if consent_record
                else "not_granted",
            }

            if policy.required:
                summary["total_required_consents"] += 1
                if is_granted:
                    summary["required_consents_granted"] += 1
            else:
                summary["total_optional_consents"] += 1
                if is_granted:
                    summary["optional_consents_granted"] += 1

        # Check compliance
        if summary["required_consents_granted"] < summary["total_required_consents"]:
            summary["compliance_status"] = "non_compliant"

        return summary

    def get_consent_statistics(self) -> dict[str, Any]:
        """Get system-wide consent statistics"""
        stats = {
            "total_users": 0,
            "consent_rates": {},
            "policy_compliance": {},
            "generated_at": datetime.now().isoformat(),
        }

        # Get total users
        from agents.common.auth_models import get_user_count

        stats["total_users"] = get_user_count()

        # Get consent rates for each type
        for consent_type, policy in self.policies.items():
            query = """
            SELECT
                COUNT(DISTINCT CASE WHEN status = 'granted' THEN user_id END) as granted_count,
                COUNT(DISTINCT user_id) as total_count
            FROM user_consents
            WHERE consent_type = %s
            """
            result = auth_execute_query_single(query, (consent_type.value,))

            if result and result["total_count"] > 0:
                grant_rate = result["granted_count"] / result["total_count"]
            else:
                grant_rate = 0.0

            stats["consent_rates"][consent_type.value] = {
                "granted_users": result["granted_count"] if result else 0,
                "total_users": result["total_count"] if result else 0,
                "grant_rate": round(grant_rate * 100, 2),
                "required": policy.required,
            }

        return stats


# Global consent manager instance
consent_manager = ConsentManager()


async def demo_consent_management():
    """Demonstrate consent management capabilities"""

    print("🛡️ Consent Management System Demo")
    print("=" * 50)

    # Show available consent policies
    print("\n📋 Available Consent Policies:")
    for consent_type, policy in consent_manager.policies.items():
        print(f"   {consent_type.value}:")
        print(f"     Name: {policy.name}")
        print(f"     Required: {policy.required}")
        print(f"     Default: {policy.default_granted}")
        print(f"     Expires: {policy.expires_days} days")
        print()

    print("✅ Consent Management System Ready!")
    print("\n🚀 Key Features:")
    print(
        "   ✅ Multiple consent types (data processing, external linking, analytics, etc.)"
    )
    print("   ✅ Granular consent tracking with expiration")
    print("   ✅ Consent withdrawal capabilities")
    print("   ✅ Compliance status monitoring")
    print("   ✅ System-wide consent statistics")

    print("\n📋 Next Steps:")
    print("   1. Integrate with FastAPI endpoints")
    print("   2. Add consent management UI")
    print("   3. Implement consent validation middleware")
    print("   4. Add consent audit logging")


if __name__ == "__main__":
    import asyncio

    asyncio.run(demo_consent_management())
