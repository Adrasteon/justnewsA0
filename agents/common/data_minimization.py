"""
Data Minimization Module for GDPR Compliance

This module implements data minimization principles by:
- Defining data collection policies
- Filtering unnecessary data collection
- Tracking data usage purposes
- Implementing automatic data cleanup
- Providing audit trails for data minimization actions
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from agents.common.compliance_audit import (
    AuditEventSeverity,
    AuditEventType,
    ComplianceAuditLogger,
)
from common.observability import get_logger


class DataPurpose(Enum):
    """Legal purposes for data processing under GDPR"""

    CONTRACT_FULFILLMENT = "contract_fulfillment"
    LEGAL_OBLIGATION = "legal_obligation"
    LEGITIMATE_INTEREST = "legitimate_interest"
    CONSENT = "consent"
    VITAL_INTERESTS = "vital_interests"
    PUBLIC_TASK = "public_task"


class DataCategory(Enum):
    """Categories of personal data"""

    IDENTIFIERS = "identifiers"  # Name, email, phone, etc.
    FINANCIAL = "financial"  # Payment info, transaction history
    HEALTH = "health"  # Medical data, health records
    LOCATION = "location"  # GPS data, IP addresses
    COMMUNICATIONS = "communications"  # Messages, call logs
    BEHAVIORAL = "behavioral"  # Usage patterns, preferences
    SENSITIVE = "sensitive"  # Racial/ethnic origin, religion, etc.


@dataclass
class DataCollectionPolicy:
    """Policy defining what data can be collected and for what purposes"""

    purpose: DataPurpose
    categories: list[DataCategory]
    retention_period_days: int
    required_fields: list[str]
    optional_fields: list[str]
    justification: str
    legal_basis: str
    created_at: datetime
    updated_at: datetime

    def is_expired(self) -> bool:
        """Check if the policy has expired"""
        return datetime.now() > (
            self.created_at + timedelta(days=self.retention_period_days)
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        data["purpose"] = self.purpose.value
        data["categories"] = [cat.value for cat in self.categories]
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data


class DataMinimizationManager:
    """Manages data minimization policies and enforcement"""

    def __init__(self, audit_logger: ComplianceAuditLogger | None = None):
        self.audit_logger = audit_logger or ComplianceAuditLogger()
        self.policies: dict[str, DataCollectionPolicy] = {}
        self.data_usage_tracker: dict[str, set[str]] = {}  # user_id -> set of purposes
        self.logger = get_logger(__name__)

        # Load existing policies
        self._load_policies()

    def _load_policies(self):
        """Load data collection policies from storage"""
        try:
            policy_file = Path("config/data_minimization_policies.json")
            if policy_file.exists():
                with open(policy_file) as f:
                    data = json.load(f)
                    for policy_data in data.get("policies", []):
                        policy = self._deserialize_policy(policy_data)
                        self.policies[policy_data["purpose"]] = policy
                self.logger.info(
                    f"Loaded {len(self.policies)} data minimization policies"
                )
            else:
                self._create_default_policies()
        except Exception as e:
            self.logger.error(f"Failed to load policies: {e}")
            self._create_default_policies()

    def _create_default_policies(self):
        """Create default data minimization policies"""
        default_policies = [
            DataCollectionPolicy(
                purpose=DataPurpose.CONTRACT_FULFILLMENT,
                categories=[DataCategory.IDENTIFIERS, DataCategory.FINANCIAL],
                retention_period_days=2555,  # 7 years for financial data
                required_fields=["email", "name"],
                optional_fields=["phone", "address"],
                justification="Required for service delivery and billing",
                legal_basis="Article 6(1)(b) GDPR - Contract fulfillment",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
            DataCollectionPolicy(
                purpose=DataPurpose.LEGITIMATE_INTEREST,
                categories=[DataCategory.BEHAVIORAL, DataCategory.COMMUNICATIONS],
                retention_period_days=365,
                required_fields=[],
                optional_fields=["usage_patterns", "preferences"],
                justification="Improve service quality and user experience",
                legal_basis="Article 6(1)(f) GDPR - Legitimate interests",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
            DataCollectionPolicy(
                purpose=DataPurpose.CONSENT,
                categories=[DataCategory.IDENTIFIERS, DataCategory.COMMUNICATIONS],
                retention_period_days=365,
                required_fields=[],
                optional_fields=["email", "phone"],
                justification="Marketing communications with user consent",
                legal_basis="Article 6(1)(a) GDPR - Consent",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]

        for policy in default_policies:
            self.policies[policy.purpose.value] = policy

        self._save_policies()
        self.logger.info("Created default data minimization policies")

    def _deserialize_policy(self, data: dict[str, Any]) -> DataCollectionPolicy:
        """Deserialize policy from dictionary"""
        return DataCollectionPolicy(
            purpose=DataPurpose(data["purpose"]),
            categories=[DataCategory(cat) for cat in data["categories"]],
            retention_period_days=data["retention_period_days"],
            required_fields=data["required_fields"],
            optional_fields=data["optional_fields"],
            justification=data["justification"],
            legal_basis=data["legal_basis"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )

    def _save_policies(self):
        """Save policies to storage"""
        try:
            policy_file = Path("config/data_minimization_policies.json")
            policy_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "policies": [policy.to_dict() for policy in self.policies.values()],
                "last_updated": datetime.now().isoformat(),
            }

            with open(policy_file, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            self.logger.error(f"Failed to save policies: {e}")

    def validate_data_collection(
        self, purpose: str, data_fields: list[str], user_id: str
    ) -> dict[str, Any]:
        """
        Validate if data collection is allowed under minimization principles

        Args:
            purpose: The purpose for data collection
            data_fields: List of data fields being collected
            user_id: User identifier

        Returns:
            Validation result with allowed/denied fields
        """
        if purpose not in self.policies:
            self.audit_logger.log_event(
                event_type=AuditEventType.SECURITY_EVENT,
                severity=AuditEventSeverity.HIGH,
                user_id=user_id,
                resource_type="data_minimization",
                action="violation",
                details={
                    "violation_type": "unknown_purpose",
                    "purpose": purpose,
                    "data_fields": data_fields,
                },
                compliance_relevant=True,
            )
            return {
                "allowed": False,
                "reason": f"Unknown data collection purpose: {purpose}",
                "allowed_fields": [],
                "denied_fields": data_fields,
            }

        policy = self.policies[purpose]

        # Check if policy is expired
        if policy.is_expired():
            return {
                "allowed": False,
                "reason": f"Data collection policy expired for purpose: {purpose}",
                "allowed_fields": [],
                "denied_fields": data_fields,
            }

        # Separate required and optional fields
        allowed_fields = []
        denied_fields = []

        for field in data_fields:
            if field in policy.required_fields or field in policy.optional_fields:
                allowed_fields.append(field)
            else:
                denied_fields.append(field)

        # Track data usage
        if user_id not in self.data_usage_tracker:
            self.data_usage_tracker[user_id] = set()
        self.data_usage_tracker[user_id].add(purpose)

        # Log validation result
        self.audit_logger.log_event(
            event_type=AuditEventType.DATA_ACCESS,
            severity=AuditEventSeverity.LOW,
            user_id=user_id,
            resource_type="data_collection",
            resource_id=purpose,
            action="validation",
            details={
                "purpose": purpose,
                "total_fields": len(data_fields),
                "allowed_fields": len(allowed_fields),
                "denied_fields": len(denied_fields),
                "policy_categories": [cat.value for cat in policy.categories],
            },
            compliance_relevant=True,
        )

        return {
            "allowed": len(allowed_fields) > 0,
            "reason": "Data collection validated"
            if allowed_fields
            else "No allowed fields found",
            "allowed_fields": allowed_fields,
            "denied_fields": denied_fields,
            "policy": policy.to_dict(),
        }

    def minimize_data_payload(
        self, data: dict[str, Any], purpose: str, user_id: str
    ) -> dict[str, Any]:
        """
        Minimize data payload by removing unnecessary fields

        Args:
            data: Original data payload
            purpose: Data collection purpose
            user_id: User identifier

        Returns:
            Minimized data payload
        """
        if purpose not in self.policies:
            self.logger.warning(f"Unknown purpose for data minimization: {purpose}")
            return {}

        policy = self.policies[purpose]
        minimized_data = {}

        # Include only allowed fields
        allowed_fields = set(policy.required_fields + policy.optional_fields)

        for key, value in data.items():
            if key in allowed_fields:
                minimized_data[key] = value

        # Log minimization action
        original_size = len(data)
        minimized_size = len(minimized_data)

        self.audit_logger.log_event(
            event_type=AuditEventType.DATA_MODIFICATION,
            severity=AuditEventSeverity.LOW,
            user_id=user_id,
            resource_type="data_payload",
            resource_id=purpose,
            action="minimize",
            details={
                "purpose": purpose,
                "original_fields": original_size,
                "minimized_fields": minimized_size,
                "fields_removed": original_size - minimized_size,
                "removed_fields": list(set(data.keys()) - set(minimized_data.keys())),
            },
            compliance_relevant=True,
        )

        return minimized_data

    def cleanup_expired_data(self, user_id: str) -> dict[str, Any]:
        """
        Clean up expired data for a user

        Args:
            user_id: User identifier

        Returns:
            Cleanup summary
        """
        if user_id not in self.data_usage_tracker:
            return {"cleaned_purposes": [], "message": "No data usage tracking found"}

        expired_purposes = []
        active_purposes = []

        for purpose in self.data_usage_tracker[user_id]:
            if purpose in self.policies:
                policy = self.policies[purpose]
                if policy.is_expired():
                    expired_purposes.append(purpose)
                else:
                    active_purposes.append(purpose)

        # Update tracking
        self.data_usage_tracker[user_id] = set(active_purposes)

        # Log cleanup
        self.audit_logger.log_event(
            event_type=AuditEventType.RETENTION_CLEANUP,
            severity=AuditEventSeverity.MEDIUM,
            user_id=user_id,
            resource_type="user_data",
            resource_id=user_id,
            action="cleanup",
            details={
                "expired_purposes": expired_purposes,
                "remaining_purposes": active_purposes,
                "cleanup_timestamp": datetime.now().isoformat(),
            },
            compliance_relevant=True,
            gdpr_article="5",
        )

        return {
            "cleaned_purposes": expired_purposes,
            "remaining_purposes": active_purposes,
            "message": f"Cleaned {len(expired_purposes)} expired data purposes",
        }

    def get_data_usage_summary(self, user_id: str) -> dict[str, Any]:
        """Get data usage summary for a user"""
        if user_id not in self.data_usage_tracker:
            return {"purposes": [], "policies": []}

        purposes = list(self.data_usage_tracker[user_id])
        policies = []

        for purpose in purposes:
            if purpose in self.policies:
                policies.append(self.policies[purpose].to_dict())

        return {
            "user_id": user_id,
            "purposes": purposes,
            "policies": policies,
            "total_policies": len(policies),
        }

    def add_policy(self, policy: DataCollectionPolicy) -> bool:
        """Add a new data collection policy"""
        try:
            self.policies[policy.purpose.value] = policy
            self._save_policies()

            self.audit_logger.log_event(
                event_type=AuditEventType.PERMISSION_CHANGE,
                severity=AuditEventSeverity.MEDIUM,
                resource_type="data_policy",
                resource_id=policy.purpose.value,
                action="add_policy",
                details={
                    "purpose": policy.purpose.value,
                    "categories": [cat.value for cat in policy.categories],
                    "retention_days": policy.retention_period_days,
                },
                compliance_relevant=True,
            )

            return True
        except Exception as e:
            self.logger.error(f"Failed to add policy: {e}")
            return False

    def get_compliance_status(self) -> dict[str, Any]:
        """Get overall data minimization compliance status"""
        total_policies = len(self.policies)
        expired_policies = sum(1 for p in self.policies.values() if p.is_expired())
        active_users = len(self.data_usage_tracker)

        return {
            "total_policies": total_policies,
            "expired_policies": expired_policies,
            "active_policies": total_policies - expired_policies,
            "active_users": active_users,
            "compliance_rate": (total_policies - expired_policies) / total_policies
            if total_policies > 0
            else 0,
            "last_updated": datetime.now().isoformat(),
        }


async def demo_data_minimization():
    """Demonstrate data minimization functionality"""
    print("🔒 Data Minimization System Demo")
    print("=" * 50)

    manager = DataMinimizationManager()

    # Test data validation
    test_data = {
        "email": "user@example.com",
        "name": "John Doe",
        "phone": "+1234567890",
        "address": "123 Main St",
        "social_security": "123-45-6789",  # Should be denied
        "usage_patterns": ["read_news", "search"],
        "preferences": {"theme": "dark"},
    }

    print("\n📋 Testing Data Collection Validation:")
    print("-" * 40)

    # Test contract fulfillment
    result = manager.validate_data_collection(
        "contract_fulfillment", list(test_data.keys()), "user123"
    )

    print("Contract Fulfillment Validation:")
    print(f"  Allowed: {result['allowed']}")
    print(f"  Allowed Fields: {result['allowed_fields']}")
    print(f"  Denied Fields: {result['denied_fields']}")

    # Test data minimization
    print("\n📦 Testing Data Minimization:")
    print("-" * 30)

    minimized = manager.minimize_data_payload(
        test_data, "contract_fulfillment", "user123"
    )
    print(f"Original data fields: {len(test_data)}")
    print(f"Minimized data fields: {len(minimized)}")
    print(f"Minimized data: {minimized}")

    # Test cleanup
    print("\n🧹 Testing Data Cleanup:")
    print("-" * 25)

    cleanup_result = manager.cleanup_expired_data("user123")
    print(f"Cleanup result: {cleanup_result}")

    # Get compliance status
    print("\n📊 Compliance Status:")
    print("-" * 20)

    status = manager.get_compliance_status()
    print(f"Total Policies: {status['total_policies']}")
    print(f"Active Policies: {status['active_policies']}")
    print(f"Expired Policies: {status['expired_policies']}")
    print(".1%")

    print("\n✅ Data Minimization System Ready!")
    print("\n🚀 Key Features:")
    print("   ✅ Data collection validation")
    print("   ✅ Automatic data minimization")
    print("   ✅ Expired data cleanup")
    print("   ✅ Compliance monitoring")
    print("   ✅ Audit trail integration")

    print("\n📋 Next Steps:")
    print("   1. Integrate with FastAPI middleware")
    print("   2. Add data minimization UI")
    print("   3. Implement automated cleanup jobs")
    print("   4. Add data usage analytics")


if __name__ == "__main__":
    import asyncio

    asyncio.run(demo_data_minimization())
