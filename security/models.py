"""
JustNews Security Framework - Shared Models and Types

Contains shared Pydantic models, configuration classes, and type definitions
used across all security framework components.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class SecurityLevel(Enum):
    """Security severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class UserRole(Enum):
    """Standard user roles with hierarchical permissions"""

    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"


class ConsentPurpose(Enum):
    """GDPR consent purposes"""

    MARKETING = "marketing"
    ANALYTICS = "analytics"
    PERSONALIZATION = "personalization"
    NECESSARY = "necessary"


class AlertSeverity(Enum):
    """Security alert severity levels"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# User and Authentication Models
class User(BaseModel):
    """User model for authentication and authorization"""

    id: int
    username: str
    email: EmailStr
    roles: list[str] = Field(default_factory=list)
    is_active: bool = True
    is_verified: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: datetime | None = None
    failed_login_attempts: int = 0
    locked_until: datetime | None = None
    mfa_enabled: bool = False
    mfa_secret: str | None = None


class UserCreate(BaseModel):
    """User creation request model"""

    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=12)
    roles: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    """User update request model"""

    email: EmailStr | None = None
    roles: list[str] | None = None
    is_active: bool | None = None
    is_verified: bool | None = None


class LoginRequest(BaseModel):
    """Login request model"""

    username: str
    password: str
    mfa_code: str | None = None


class TokenPair(BaseModel):
    """JWT token pair response"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class PasswordResetRequest(BaseModel):
    """Password reset request model"""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation model"""

    token: str
    new_password: str = Field(..., min_length=12)


# Authorization Models
class Role(BaseModel):
    """Role definition with permissions"""

    name: str
    description: str
    permissions: list[str] = Field(default_factory=list)
    parent_roles: list[str] = Field(default_factory=list)


class PermissionCheck(BaseModel):
    """Permission check request"""

    user_id: int
    permission: str
    resource_id: str | None = None


# Encryption Models
class EncryptionKey(BaseModel):
    """Encryption key metadata"""

    id: str
    algorithm: str
    created_at: datetime
    expires_at: datetime | None = None
    is_active: bool = True


class EncryptedData(BaseModel):
    """Encrypted data container"""

    data: str  # Base64 encoded encrypted data
    key_id: str
    algorithm: str
    nonce: str | None = None


# Compliance Models
class ConsentRecord(BaseModel):
    """GDPR consent record"""

    id: str
    user_id: int
    purpose: str
    granted: bool
    granted_at: datetime
    expires_at: datetime | None = None
    ip_address: str | None = None
    user_agent: str | None = None


class AuditEvent(BaseModel):
    """Audit trail event"""

    id: str
    timestamp: datetime
    user_id: int | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    ip_address: str | None = None
    user_agent: str | None = None


class DataExport(BaseModel):
    """GDPR data export response"""

    user_id: int
    exported_at: datetime
    data: dict[str, Any]


# Monitoring Models
class SecurityEvent(BaseModel):
    """Security event for monitoring"""

    id: str
    timestamp: datetime
    event_type: str
    severity: SecurityLevel
    user_id: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    ip_address: str | None = None
    user_agent: str | None = None


class MonitoringRule(BaseModel):
    """Security monitoring rule"""

    id: str
    name: str
    description: str
    event_pattern: dict[str, Any]
    condition: str  # Python expression to evaluate
    severity: AlertSeverity
    enabled: bool = True


class SecurityAlert(BaseModel):
    """Security alert notification"""

    id: str
    timestamp: datetime
    rule_id: str
    severity: AlertSeverity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    resolved: bool = False
    resolved_at: datetime | None = None
    resolved_by: int | None = None


class SecurityMetrics(BaseModel):
    """Security metrics summary"""

    period_start: datetime
    period_end: datetime
    total_events: int
    events_by_severity: dict[str, int]
    alerts_generated: int
    alerts_resolved: int
    failed_auth_attempts: int
    successful_auth_attempts: int
    unique_users: int
    top_event_types: list[dict[str, Any]]


# Configuration Models
class SecurityConfig(BaseModel):
    """Security framework configuration"""

    # JWT settings
    jwt_secret: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    jwt_refresh_expiration_days: int = 7

    # Password security
    bcrypt_rounds: int = 12
    password_min_length: int = 12
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_digits: bool = True
    password_require_special: bool = True

    # Session management
    session_timeout_minutes: int = 30
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 30

    # Encryption
    encryption_key: str | None = None  # Auto-generated if not provided
    encryption_algorithm: str = "AES-256-GCM"
    key_rotation_days: int = 90

    # MFA
    mfa_enabled: bool = True
    mfa_issuer: str = "JustNews"

    # Compliance
    audit_retention_days: int = 2555  # 7 years for GDPR
    consent_retention_days: int = 2555
    enable_gdpr: bool = True
    enable_ccpa: bool = True

    # Monitoring
    enable_monitoring: bool = True
    alert_email_recipients: list[str] = Field(default_factory=list)
    max_events_per_hour: int = 1000
    enable_structured_logging: bool = True

    # Performance
    max_concurrent_requests: int = 100
    request_timeout_seconds: int = 30


class SecurityContext(BaseModel):
    """Security context for request processing"""

    user: User | None = None
    permissions: list[str] = Field(default_factory=list)
    session_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    request_id: str | None = None


# Exception Classes
class SecurityError(Exception):
    """Base security exception"""

    def __init__(self, message: str, code: str = "SECURITY_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class AuthenticationError(SecurityError):
    """Authentication-related security error"""

    def __init__(self, message: str):
        super().__init__(message, "AUTHENTICATION_ERROR")


class AuthorizationError(SecurityError):
    """Authorization-related security error"""

    def __init__(self, message: str):
        super().__init__(message, "AUTHORIZATION_ERROR")


class EncryptionError(SecurityError):
    """Encryption-related security error"""

    def __init__(self, message: str):
        super().__init__(message, "ENCRYPTION_ERROR")


class ComplianceError(SecurityError):
    """Compliance-related security error"""

    def __init__(self, message: str):
        super().__init__(message, "COMPLIANCE_ERROR")


class MonitoringError(SecurityError):
    """Monitoring-related security error"""

    def __init__(self, message: str):
        super().__init__(message, "MONITORING_ERROR")
