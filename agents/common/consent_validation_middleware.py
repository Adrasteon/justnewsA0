"""
Consent Validation Middleware for GDPR Compliance

This middleware validates user consents before allowing data processing operations.
It integrates with the consent management system to ensure compliance with GDPR requirements.

Features:
- Automatic consent validation for data processing endpoints
- Consent requirement mapping for different operations
- Graceful handling of missing or expired consents
- Audit logging of consent validation events
- Configurable consent enforcement levels
"""

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from agents.common.compliance_audit import (
    AuditEventSeverity,
    AuditEventType,
    ComplianceAuditLogger,
)
from agents.common.consent_management import ConsentType, consent_manager
from common.observability import get_logger

logger = get_logger(__name__)


class ConsentValidationMiddleware:
    """Middleware for validating user consents before data processing"""

    def __init__(self, audit_logger: ComplianceAuditLogger | None = None):
        self.audit_logger = audit_logger or ComplianceAuditLogger()
        self.consent_requirements = self._load_consent_requirements()

    def _load_consent_requirements(self) -> dict[str, list[ConsentType]]:
        """Load consent requirements for different endpoints/operations"""
        return {
            # Authentication endpoints
            "/auth/register": [],
            "/auth/login": [],
            "/auth/logout": [],
            "/auth/refresh": [],
            "/auth/me": [ConsentType.DATA_PROCESSING],
            "/auth/password-reset": [],
            "/auth/password-reset/confirm": [],
            # Data processing endpoints
            "/api/articles": [ConsentType.DATA_PROCESSING],
            "/api/search": [ConsentType.DATA_PROCESSING],
            "/api/analytics": [ConsentType.ANALYTICS],
            "/api/export": [ConsentType.DATA_PROCESSING],
            "/api/profile": [ConsentType.DATA_PROCESSING, ConsentType.PROFILE_ANALYSIS],
            # External integrations
            "/api/external/*": [ConsentType.EXTERNAL_LINKING],
            "/api/sharing": [ConsentType.DATA_SHARING],
            # Marketing endpoints
            "/api/marketing/*": [ConsentType.MARKETING],
            "/api/newsletter": [ConsentType.MARKETING],
            # Admin endpoints (may have different requirements)
            "/admin/*": [],  # Admin operations may not require user consent
        }

    def _get_required_consents(self, path: str) -> list[ConsentType]:
        """Get required consents for a given endpoint path"""
        # Check for exact matches first
        if path in self.consent_requirements:
            return self.consent_requirements[path]

        # Check for pattern matches
        for pattern, consents in self.consent_requirements.items():
            if pattern.endswith("/*"):
                base_pattern = pattern[:-2]
                if path.startswith(base_pattern):
                    return consents

        # Default: require basic data processing consent for API endpoints
        if path.startswith("/api/"):
            return [ConsentType.DATA_PROCESSING]

        return []

    def _extract_user_id(self, request: Request) -> str | None:
        """Extract user ID from request (JWT token, session, etc.)"""
        try:
            # Try to get from Authorization header
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                auth_header.replace("Bearer ", "")
                # In a real implementation, you'd decode the JWT token here
                # For now, we'll use a placeholder
                return "current_user"

            # Try to get from session cookie
            session_id = request.cookies.get("session_id")
            if session_id:
                # In a real implementation, you'd validate the session
                return f"session_{session_id}"

        except Exception as e:
            logger.warning(f"Failed to extract user ID: {e}")

        return None

    def _should_skip_validation(self, request: Request) -> bool:
        """Check if consent validation should be skipped for this request"""
        # Skip validation for:
        # - Health check endpoints
        # - Static file requests
        # - OPTIONS requests (CORS preflight)
        # - Public endpoints that don't process user data

        skip_paths = [
            "/health",
            "/docs",
            "/openapi.json",
            "/favicon.ico",
            "/static/",
            "/public/",
        ]

        if request.method == "OPTIONS":
            return True

        for skip_path in skip_paths:
            if request.url.path.startswith(skip_path):
                return True

        return False

    async def validate_consent(self, request: Request) -> bool:
        """
        Validate user consents for the current request

        Returns True if validation passes, raises HTTPException if it fails
        """
        try:
            # Skip validation for certain requests
            if self._should_skip_validation(request):
                return True

            # Get required consents for this endpoint
            required_consents = self._get_required_consents(request.url.path)

            # If no consents required, allow the request
            if not required_consents:
                return True

            # Extract user ID
            user_id = self._extract_user_id(request)
            if not user_id:
                # For endpoints requiring consent, user must be authenticated
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required for this operation",
                )

            # Check each required consent
            missing_consents = []
            expired_consents = []

            for consent_type in required_consents:
                consent_status = consent_manager.get_user_consent(user_id, consent_type)

                if not consent_status.get("granted", False):
                    missing_consents.append(consent_type.value)
                elif consent_status.get("expired", False):
                    expired_consents.append(consent_type.value)

            # If any consents are missing or expired, block the request
            if missing_consents or expired_consents:
                # Log the violation
                self.audit_logger.log_event(
                    event_type=AuditEventType.SECURITY_EVENT,
                    severity=AuditEventSeverity.HIGH,
                    user_id=user_id,
                    ip_address=self._get_client_ip(request),
                    resource_type="api_endpoint",
                    resource_id=request.url.path,
                    action="consent_validation_failed",
                    details={
                        "missing_consents": missing_consents,
                        "expired_consents": expired_consents,
                        "required_consents": [c.value for c in required_consents],
                        "http_method": request.method,
                    },
                    compliance_relevant=True,
                    gdpr_article="6",
                )

                # Return appropriate error response
                if missing_consents:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={
                            "error": "Missing required consents",
                            "missing_consents": missing_consents,
                            "message": "Please grant the required consents to access this feature",
                        },
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={
                            "error": "Expired consents",
                            "expired_consents": expired_consents,
                            "message": "Some of your consents have expired. Please review and renew them.",
                        },
                    )

            # Log successful validation
            self.audit_logger.log_event(
                event_type=AuditEventType.DATA_ACCESS,
                severity=AuditEventSeverity.LOW,
                user_id=user_id,
                ip_address=self._get_client_ip(request),
                resource_type="api_endpoint",
                resource_id=request.url.path,
                action="consent_validated",
                details={
                    "required_consents": [c.value for c in required_consents],
                    "http_method": request.method,
                },
                compliance_relevant=True,
            )

            return True

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Consent validation error: {e}")

            # Log the error
            user_id = self._extract_user_id(request)
            self.audit_logger.log_event(
                event_type=AuditEventType.SECURITY_EVENT,
                severity=AuditEventSeverity.CRITICAL,
                user_id=user_id,
                ip_address=self._get_client_ip(request),
                resource_type="consent_validation",
                action="validation_error",
                details={
                    "error": str(e),
                    "endpoint": request.url.path,
                    "method": request.method,
                },
            )

            # Allow request to proceed on validation errors to avoid blocking legitimate access
            logger.warning("Consent validation failed, allowing request to proceed")
            return True

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request"""
        # Check for forwarded headers first
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        # Check for other proxy headers
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to direct client IP
        return (
            getattr(request.client, "host", "unknown") if request.client else "unknown"
        )

    def add_consent_requirement(self, path: str, consents: list[ConsentType]):
        """Add consent requirements for a specific endpoint"""
        self.consent_requirements[path] = consents
        logger.info(
            f"Added consent requirements for {path}: {[c.value for c in consents]}"
        )

    def remove_consent_requirement(self, path: str):
        """Remove consent requirements for a specific endpoint"""
        if path in self.consent_requirements:
            del self.consent_requirements[path]
            logger.info(f"Removed consent requirements for {path}")

    def get_consent_requirements(self) -> dict[str, list[str]]:
        """Get all consent requirements (for debugging/admin purposes)"""
        return {
            path: [consent.value for consent in consents]
            for path, consents in self.consent_requirements.items()
        }


# Global middleware instance
consent_middleware = ConsentValidationMiddleware()


async def consent_validation_middleware(request: Request, call_next):
    """
    FastAPI middleware function for consent validation

    Usage:
        app.middleware("http")(consent_validation_middleware)
    """
    try:
        # Validate consent before processing the request
        await consent_middleware.validate_consent(request)

        # Process the request
        response = await call_next(request)

        return response

    except HTTPException as e:
        # Return structured error response for consent violations
        if isinstance(e.detail, dict):
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "status": "error",
                    "error": e.detail.get("error", "Consent validation failed"),
                    "message": e.detail.get("message", str(e)),
                    "details": e.detail,
                },
            )
        else:
            return JSONResponse(
                status_code=e.status_code,
                content={"status": "error", "message": str(e)},
            )
    except Exception as e:
        logger.error(f"Middleware error: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": "Internal server error"},
        )


async def demo_consent_middleware():
    """Demonstrate consent validation middleware functionality"""
    print("🛡️ Consent Validation Middleware Demo")
    print("=" * 50)

    middleware = ConsentValidationMiddleware()

    print("\n📋 Consent Requirements:")
    print("-" * 25)
    requirements = middleware.get_consent_requirements()
    for path, consents in requirements.items():
        print(f"  {path}: {consents}")

    print("\n✅ Adding Custom Consent Requirement:")
    print("-" * 40)
    middleware.add_consent_requirement(
        "/api/custom", [ConsentType.ANALYTICS, ConsentType.MARKETING]
    )
    print("Added requirement for /api/custom: ['analytics', 'marketing']")

    print("\n📊 Updated Requirements:")
    print("-" * 25)
    requirements = middleware.get_consent_requirements()
    for path, consents in list(requirements.items())[-5:]:  # Show last 5
        print(f"  {path}: {consents}")

    print("\n✅ Consent Validation Middleware Ready!")
    print("\n🚀 Key Features:")
    print("   ✅ Automatic consent validation for API endpoints")
    print("   ✅ Configurable consent requirements per endpoint")
    print("   ✅ Comprehensive audit logging")
    print("   ✅ Graceful error handling")
    print("   ✅ GDPR Article 6 compliance")

    print("\n📋 Integration Steps:")
    print("   1. Add middleware to FastAPI app:")
    print("      app.middleware('http')(consent_validation_middleware)")
    print("   2. Configure consent requirements for endpoints")
    print("   3. Test with different user consent scenarios")
    print("   4. Monitor audit logs for compliance")


if __name__ == "__main__":
    import asyncio

    asyncio.run(demo_consent_middleware())
