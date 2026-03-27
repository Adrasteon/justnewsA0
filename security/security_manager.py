"""
JustNews Security Framework - Core Security Manager

Provides centralized security orchestration for authentication, authorization,
encryption, compliance monitoring, and security event tracking.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from .authentication.service import AuthenticationService
from .authorization.service import AuthorizationService
from .compliance.service import ComplianceService
from .encryption.service import EncryptionService
from .models import (
    AuthenticationError,
    SecurityConfig,
    SecurityContext,
)
from .monitoring.service import SecurityMonitor

logger = logging.getLogger(__name__)


class SecurityManager:
    # Duplicate class documentation and initializer removed (keeps a single, canonical __init__)
    """
    Central security orchestrator for JustNews

    Coordinates all security operations including authentication, authorization,
    encryption, compliance monitoring, and security event tracking.
    """

    def __init__(self, config: SecurityConfig):
        self.config = config
        self._initialized = False

        # Initialize security services
        self.auth_service = AuthenticationService(config)
        self.authz_service = AuthorizationService(config)
        self.encrypt_service = EncryptionService(config)
        self.compliance_service = ComplianceService(config)
        self.monitor_service = SecurityMonitor(config)

        # Active sessions cache
        self._active_sessions: dict[str, SecurityContext] = {}
        self._session_cleanup_task: asyncio.Task | None = None

        logger.info("SecurityManager initialized")

    async def initialize(self) -> None:
        """Initialize all security services"""
        if self._initialized:
            return

        try:
            # Initialize all services
            await asyncio.gather(
                self.auth_service.initialize(),
                self.authz_service.initialize(),
                self.encrypt_service.initialize(),
                self.compliance_service.initialize(),
                self.monitor_service.initialize(),
            )

            # Start session cleanup task
            self._session_cleanup_task = asyncio.create_task(
                self._cleanup_expired_sessions()
            )

            self._initialized = True
            logger.info("SecurityManager fully initialized")

        except Exception as e:
            logger.error(f"Failed to initialize SecurityManager: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown all security services"""
        if not self._initialized:
            return

        try:
            # Cancel cleanup task
            if self._session_cleanup_task:
                self._session_cleanup_task.cancel()
                try:
                    await self._session_cleanup_task
                except asyncio.CancelledError:
                    pass

            # Shutdown all services
            await asyncio.gather(
                self.auth_service.shutdown(),
                self.authz_service.shutdown(),
                self.encrypt_service.shutdown(),
                self.compliance_service.shutdown(),
                self.monitor_service.shutdown(),
                return_exceptions=True,
            )

            self._initialized = False
            logger.info("SecurityManager shutdown complete")

        except Exception as e:
            logger.error(f"Error during SecurityManager shutdown: {e}")

    @asynccontextmanager
    async def security_context(self, user_id: int, operation: str):
        """Context manager for security operations"""
        context = await self._create_security_context(user_id, operation)

        try:
            yield context
        except Exception as e:
            await self.monitor_service.log_security_event(
                event_type="operation_failed",
                user_id=user_id,
                details={"operation": operation, "error": str(e)},
                severity="warning",
            )
            raise
        finally:
            # Log operation completion
            await self.monitor_service.log_security_event(
                event_type="operation_completed",
                user_id=user_id,
                details={"operation": operation},
            )

    async def authenticate_user(
        self,
        username: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """
        Authenticate user and return tokens

        Args:
            username: User username
            password: User password
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Dict containing access_token, refresh_token, and user info

        Raises:
            AuthenticationError: If authentication fails
        """
        try:
            # Authenticate user
            user_data = await self.auth_service.authenticate(username, password)

            # Check if account is locked
            if user_data.get("locked_until"):
                locked_until = datetime.fromisoformat(user_data["locked_until"])
                if locked_until > datetime.now(UTC):
                    await self.monitor_service.log_security_event(
                        "authentication_blocked",
                        user_data["id"],
                        {"reason": "account_locked", "ip_address": ip_address},
                    )
                    raise AuthenticationError("Account is temporarily locked")

            # Create security context
            context = SecurityContext(
                user_id=user_data["id"],
                username=user_data["username"],
                roles=user_data["roles"],
                permissions=[],  # Will be populated by authz service
                session_id=self._generate_session_id(),
                ip_address=ip_address,
                user_agent=user_agent,
            )

            # Get user permissions
            context.permissions = await self.authz_service.get_user_permissions(
                user_data["id"]
            )

            # Generate tokens
            tokens = await self.auth_service.generate_tokens(
                user_data["id"], user_data["roles"]
            )

            # Store active session
            self._active_sessions[context.session_id] = context

            # Log successful authentication
            await self.monitor_service.log_security_event(
                "authentication_success",
                user_data["id"],
                {"ip_address": ip_address, "user_agent": user_agent},
            )

            # Update last login
            await self.auth_service.update_last_login(user_data["id"])

            return {
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
                "token_type": "bearer",
                "expires_in": self.config.jwt_expiration_hours * 3600,
                "user": {
                    "id": user_data["id"],
                    "username": user_data["username"],
                    "email": user_data["email"],
                    "roles": user_data["roles"],
                    "mfa_enabled": user_data.get("mfa_enabled", False),
                },
            }

        except Exception as e:
            # Log failed authentication
            await self.monitor_service.log_security_event(
                "authentication_failure",
                None,  # No user ID for failed auth
                {"username": username, "ip_address": ip_address, "error": str(e)},
            )
            raise

    async def validate_token(self, token: str) -> SecurityContext:
        """
        Validate JWT token and return security context

        Args:
            token: JWT access token

        Returns:
            SecurityContext for the authenticated user

        Raises:
            AuthenticationError: If token is invalid
        """
        try:
            # Validate token
            payload = await self.auth_service.validate_token(token)

            session_id = payload.get("session_id")
            if not session_id or session_id not in self._active_sessions:
                raise AuthenticationError("Invalid session")

            context = self._active_sessions[session_id]

            # Check if session expired
            if self._is_session_expired(context):
                del self._active_sessions[session_id]
                raise AuthenticationError("Session expired")

            return context

        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            # Chain the source exception for clarity
            raise AuthenticationError("Invalid token") from e

    async def check_permission(
        self, user_id: int, permission: str, resource: str | None = None
    ) -> bool:
        """
        Check if user has specific permission

        Args:
            user_id: User ID
            permission: Permission to check
            resource: Optional resource identifier

        Returns:
            True if user has permission, False otherwise
        """
        try:
            allowed = await self.authz_service.check_permission(
                user_id, permission, resource
            )

            # Log permission check
            await self.monitor_service.log_security_event(
                "permission_check",
                user_id,
                {"permission": permission, "resource": resource, "allowed": allowed},
            )

            return allowed

        except Exception as e:
            logger.error(f"Permission check failed: {e}")
            return False

    async def encrypt_data(self, data: str | bytes, key_id: str | None = None) -> str:
        """
        Encrypt sensitive data

        Args:
            data: Data to encrypt
            key_id: Optional key identifier

        Returns:
            Encrypted data as base64 string
        """
        try:
            encrypted = await self.encrypt_service.encrypt_data(data, key_id)

            # Log encryption operation (without sensitive data)
            await self.monitor_service.log_security_event(
                "data_encryption",
                None,
                {"key_id": key_id, "data_size": len(str(data)) if data else 0},
            )

            return encrypted

        except Exception as e:
            logger.error(f"Data encryption failed: {e}")
            raise

    async def decrypt_data(
        self, encrypted_data: str, key_id: str | None = None
    ) -> str | bytes:
        """
        Decrypt sensitive data

        Args:
            encrypted_data: Encrypted data as base64 string
            key_id: Optional key identifier

        Returns:
            Decrypted data
        """
        try:
            decrypted = await self.encrypt_service.decrypt_data(encrypted_data, key_id)

            # Log decryption operation
            await self.monitor_service.log_security_event(
                "data_decryption",
                None,
                {"key_id": key_id, "data_size": len(encrypted_data)},
            )

            return decrypted

        except Exception as e:
            logger.error(f"Data decryption failed: {e}")
            raise

    async def log_compliance_event(
        self, event_type: str, user_id: int | None, data: dict[str, Any]
    ) -> None:
        """
        Log compliance-related event

        Args:
            event_type: Type of compliance event
            user_id: Optional user ID
            data: Event data
        """
        await self.compliance_service.log_event(event_type, user_id, data)

        # Also log to security monitor
        await self.monitor_service.log_security_event(
            f"compliance_{event_type}", user_id, data
        )

    async def get_security_status(self) -> dict[str, Any]:
        """
        Get current security status

        Returns:
            Dict containing security metrics and status
        """
        try:
            # Get status from all services
            auth_status = await self.auth_service.get_status()
            authz_status = await self.authz_service.get_status()
            encrypt_status = await self.encrypt_service.get_status()
            compliance_status = await self.compliance_service.get_status()
            monitor_status = await self.monitor_service.get_status()

            # Aggregate status
            overall_status = "healthy"
            issues = []

            for _service_name, status in [
                ("authentication", auth_status),
                ("authorization", authz_status),
                ("encryption", encrypt_status),
                ("compliance", compliance_status),
                ("monitoring", monitor_status),
            ]:
                if status.get("status") != "healthy":
                    overall_status = "degraded"
                    issues.extend(status.get("issues", []))

            return {
                "overall_status": overall_status,
                "services": {
                    "authentication": auth_status,
                    "authorization": authz_status,
                    "encryption": encrypt_status,
                    "compliance": compliance_status,
                    "monitoring": monitor_status,
                },
                "active_sessions": len(self._active_sessions),
                "issues": issues,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get security status: {e}")
            return {
                "overall_status": "error",
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def _create_security_context(
        self, user_id: int, operation: str
    ) -> SecurityContext:
        """Create security context for operation"""
        # Get user info
        user_info = await self.auth_service.get_user_info(user_id)

        # Get permissions
        permissions = await self.authz_service.get_user_permissions(user_id)

        return SecurityContext(
            user_id=user_id,
            username=user_info["username"],
            roles=user_info["roles"],
            permissions=permissions,
            session_id=self._generate_session_id(),
            timestamp=datetime.now(UTC),
        )

    def _generate_session_id(self) -> str:
        """Generate unique session ID"""
        import secrets

        return secrets.token_urlsafe(32)

    def _is_session_expired(self, context: SecurityContext) -> bool:
        """Check if session is expired"""
        expiration = context.timestamp + timedelta(
            minutes=self.config.session_timeout_minutes
        )
        return datetime.now(UTC) > expiration

    async def _cleanup_expired_sessions(self) -> None:
        """Background task to cleanup expired sessions"""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes

                expired_sessions = []
                now = datetime.now(UTC)

                for session_id, context in self._active_sessions.items():
                    expiration = context.timestamp + timedelta(
                        minutes=self.config.session_timeout_minutes
                    )
                    if now > expiration:
                        expired_sessions.append(session_id)

                for session_id in expired_sessions:
                    del self._active_sessions[session_id]

                if expired_sessions:
                    logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Session cleanup error: {e}")
