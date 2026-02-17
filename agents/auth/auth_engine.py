"""
Authentication Engine for JustNews

Core business logic for user authentication, authorization, and session management.
Provides JWT-based authentication with role-based access control and GDPR compliance.
"""

import asyncio
from typing import Any

from agents.common.auth_models import (
    create_user_tables,
    get_auth_connection_pool,
    initialize_auth_connection_pool,
)
from common.observability import get_logger

logger = get_logger(__name__)


class AuthEngine:
    """
    Authentication engine providing core user management and security functionality.

    Handles user authentication, authorization, session management, and GDPR compliance
    features including data export, deletion, and consent management.
    """

    def __init__(self):
        """Initialize the authentication engine"""
        self._initialized = False
        self._health_status = "initializing"
        self._connection_pool = None

    async def initialize(self) -> bool:
        """
        Initialize the authentication engine and database connections.

        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            logger.info("🔐 Initializing Authentication Engine...")

            # Initialize database connection pool
            self._connection_pool = initialize_auth_connection_pool()

            # Ensure database tables exist
            create_user_tables()

            # Test database connection
            pool = get_auth_connection_pool()
            with pool.getconn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    if result[0] != 1:
                        raise Exception("Database connectivity test failed")

            self._initialized = True
            self._health_status = "healthy"
            logger.info("✅ Authentication Engine initialized successfully")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize Authentication Engine: {e}")
            self._health_status = f"error: {str(e)}"
            return False

    async def shutdown(self) -> None:
        """Shutdown the authentication engine and cleanup resources"""
        try:
            logger.info("🔐 Shutting down Authentication Engine...")

            # Close database connection pool
            if self._connection_pool:
                self._connection_pool.closeall()
                self._connection_pool = None

            self._initialized = False
            self._health_status = "shutdown"
            logger.info("✅ Authentication Engine shutdown complete")

        except Exception as e:
            logger.error(f"❌ Error during Authentication Engine shutdown: {e}")

    def is_initialized(self) -> bool:
        """Check if the authentication engine is properly initialized"""
        return self._initialized

    async def health_check(self) -> dict[str, Any]:
        """
        Perform comprehensive health check of authentication services.

        Returns:
            Dict containing health status and diagnostic information
        """
        health_info = {
            "service": "auth_engine",
            "status": self._health_status,
            "initialized": self._initialized,
            "timestamp": asyncio.get_event_loop().time(),
            "checks": {},
        }

        try:
            # Database connectivity check
            db_healthy = False
            db_error = None

            try:
                if self._connection_pool:
                    with self._connection_pool.getconn() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute("SELECT COUNT(*) FROM users")
                            result = cursor.fetchone()
                            db_healthy = True
                            health_info["checks"]["database"] = {
                                "status": "healthy",
                                "user_count": result[0] if result else 0,
                            }
                else:
                    db_error = "Connection pool not initialized"
            except Exception as e:
                db_error = str(e)

            if not db_healthy:
                health_info["checks"]["database"] = {
                    "status": "unhealthy",
                    "error": db_error,
                }
                health_info["status"] = "degraded"

            # Overall status determination
            if health_info["status"] == "healthy" and all(
                check.get("status") == "healthy"
                for check in health_info["checks"].values()
            ):
                health_info["status"] = "healthy"
            else:
                health_info["status"] = "degraded"

        except Exception as e:
            logger.error(f"Health check error: {e}")
            health_info["status"] = "error"
            health_info["error"] = str(e)

        return health_info

    def get_service_info(self) -> dict[str, Any]:
        """
        Get service information and capabilities.

        Returns:
            Dict containing service metadata and supported features
        """
        return {
            "service": "auth_engine",
            "version": "1.0.0",
            "description": "Authentication and authorization service for JustNews",
            "features": [
                "JWT-based authentication",
                "Role-based access control",
                "Session management",
                "Password reset",
                "GDPR compliance (data export/deletion)",
                "Consent management",
                "Data minimization",
            ],
            "endpoints": [
                "POST /auth/register",
                "POST /auth/login",
                "POST /auth/refresh",
                "POST /auth/logout",
                "GET /auth/me",
                "POST /auth/password-reset",
                "GET /auth/users (admin)",
                "POST /auth/data-export",
                "POST /auth/data-deletion",
                "GET /auth/consents",
                "GET /health",
            ],
            "database": {
                "type": "MariaDB",
                "tables": [
                    "users",
                    "refresh_tokens",
                    "password_reset_tokens",
                    "consent_records",
                ],
            },
        }


# Global auth engine instance
_auth_engine: AuthEngine | None = None


def get_auth_engine() -> AuthEngine:
    """Get the global authentication engine instance"""
    global _auth_engine
    if _auth_engine is None:
        _auth_engine = AuthEngine()
    return _auth_engine


async def initialize_auth_engine() -> bool:
    """
    Initialize the global authentication engine instance.

    Returns:
        bool: True if initialization successful
    """
    engine = get_auth_engine()
    return await engine.initialize()


async def shutdown_auth_engine() -> None:
    """Shutdown the global authentication engine instance"""
    global _auth_engine
    if _auth_engine:
        await _auth_engine.shutdown()
        _auth_engine = None
