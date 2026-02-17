"""
JustNews Security Framework

A comprehensive security framework providing authentication, authorization,
encryption, compliance monitoring, and security event tracking.
"""

from .authentication.service import AuthenticationError as AuthError
from .authentication.service import AuthenticationService
from .authorization.service import AuthorizationError as AuthzError
from .authorization.service import AuthorizationService
from .compliance.service import ComplianceError, ComplianceService
from .encryption.service import EncryptionError, EncryptionService
from .monitoring.service import SecurityMonitor
from .security_manager import (
    AuthenticationError,
    AuthorizationError,
    SecurityConfig,
    SecurityContext,
    SecurityError,
    SecurityManager,
)

__version__ = "1.0.0"
__all__ = [
    "SecurityManager",
    "SecurityConfig",
    "SecurityContext",
    "AuthenticationError",
    "AuthorizationError",
    "SecurityError",
    "AuthenticationService",
    "AuthError",
    "AuthorizationService",
    "AuthzError",
    "EncryptionService",
    "EncryptionError",
    "ComplianceService",
    "ComplianceError",
    "SecurityMonitor",
]
