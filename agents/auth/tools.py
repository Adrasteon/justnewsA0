"""
Authentication Tools for JustNews

Wrapper functions for authentication operations that can be called by other agents
and services in the JustNews system.
"""

import os
from typing import Any

import requests

from agents.common.auth_models import UserStatus, get_user_by_id, verify_token
from common.observability import get_logger

logger = get_logger(__name__)

# Authentication service configuration
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://localhost:8009")
AUTH_SERVICE_TIMEOUT = int(os.environ.get("AUTH_SERVICE_TIMEOUT", "30"))


def authenticate_user(username_or_email: str, password: str) -> dict[str, Any] | None:
    """
    Authenticate a user with username/email and password.

    Args:
        username_or_email: User's username or email address
        password: User's password

    Returns:
        Dict containing authentication tokens and user info, or None if authentication fails
    """
    try:
        payload = {"username_or_email": username_or_email, "password": password}

        response = requests.post(
            f"{AUTH_SERVICE_URL}/auth/login", json=payload, timeout=AUTH_SERVICE_TIMEOUT
        )

        if response.status_code == 200:
            data = response.json()
            logger.info(f"User authenticated: {username_or_email}")
            return data
        else:
            logger.warning(
                f"Authentication failed for user: {username_or_email} - {response.status_code}"
            )
            return None

    except Exception as e:
        logger.error(f"Authentication request failed: {e}")
        return None


def validate_access_token(token: str) -> dict[str, Any] | None:
    """
    Validate an access token and return user information.

    Args:
        token: JWT access token

    Returns:
        Dict containing user information, or None if token is invalid
    """
    try:
        # First try local validation (faster)
        payload = verify_token(token)
        if payload and payload.get("user_id"):
            user = get_user_by_id(payload["user_id"])
            if user and user["status"] == UserStatus.ACTIVE.value:
                return {
                    "user_id": user["user_id"],
                    "username": user["username"],
                    "email": user["email"],
                    "role": user["role"],
                    "status": user["status"],
                }

        # Fallback to service validation
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{AUTH_SERVICE_URL}/auth/me", headers=headers, timeout=AUTH_SERVICE_TIMEOUT
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "user_id": data["user_id"],
                "username": data["username"],
                "email": data["email"],
                "role": data["role"],
                "status": data["status"],
            }
        else:
            logger.warning(f"Token validation failed - {response.status_code}")
            return None

    except Exception as e:
        logger.error(f"Token validation error: {e}")
        return None


def refresh_user_token(refresh_token: str) -> dict[str, Any] | None:
    """
    Refresh an access token using a refresh token.

    Args:
        refresh_token: Valid refresh token

    Returns:
        Dict containing new access token, or None if refresh fails
    """
    try:
        payload = {"refresh_token": refresh_token}

        response = requests.post(
            f"{AUTH_SERVICE_URL}/auth/refresh",
            json=payload,
            timeout=AUTH_SERVICE_TIMEOUT,
        )

        if response.status_code == 200:
            data = response.json()
            logger.info("Token refreshed successfully")
            return data
        else:
            logger.warning(f"Token refresh failed - {response.status_code}")
            return None

    except Exception as e:
        logger.error(f"Token refresh request failed: {e}")
        return None


def check_user_permission(user_id: int, required_role: str) -> bool:
    """
    Check if a user has the required role/permission.

    Args:
        user_id: User ID to check
        required_role: Required role (e.g., "admin", "user")

    Returns:
        True if user has required permission, False otherwise
    """
    try:
        user = get_user_by_id(user_id)
        if not user:
            return False

        if user["status"] != UserStatus.ACTIVE.value:
            return False

        # Check role hierarchy
        role_hierarchy = {"user": 1, "moderator": 2, "admin": 3}

        user_level = role_hierarchy.get(user["role"], 0)
        required_level = role_hierarchy.get(required_role, 999)

        return user_level >= required_level

    except Exception as e:
        logger.error(f"Permission check error: {e}")
        return False


def get_user_profile(user_id: int) -> dict[str, Any] | None:
    """
    Get user profile information.

    Args:
        user_id: User ID to retrieve

    Returns:
        Dict containing user profile data, or None if user not found
    """
    try:
        user = get_user_by_id(user_id)
        if user and user["status"] == UserStatus.ACTIVE.value:
            return {
                "user_id": user["user_id"],
                "username": user["username"],
                "email": user["email"],
                "full_name": user["full_name"],
                "role": user["role"],
                "status": user["status"],
                "created_at": user["created_at"],
                "last_login": user["last_login"],
            }
        return None

    except Exception as e:
        logger.error(f"Get user profile error: {e}")
        return None


def check_auth_service_health() -> dict[str, Any]:
    """
    Check the health status of the authentication service.

    Returns:
        Dict containing health status information
    """
    try:
        response = requests.get(f"{AUTH_SERVICE_URL}/health", timeout=10)

        if response.status_code == 200:
            return {
                "status": "healthy",
                "service": "auth",
                "response_time": response.elapsed.total_seconds(),
                "details": response.json(),
            }
        else:
            return {
                "status": "unhealthy",
                "service": "auth",
                "error": f"HTTP {response.status_code}",
                "details": response.text,
            }

    except Exception as e:
        return {"status": "error", "service": "auth", "error": str(e)}


def create_user_account(user_data: dict[str, Any]) -> int | None:
    """
    Create a new user account.

    Args:
        user_data: Dict containing user registration data

    Returns:
        User ID if creation successful, None otherwise
    """
    try:
        response = requests.post(
            f"{AUTH_SERVICE_URL}/auth/register",
            json=user_data,
            timeout=AUTH_SERVICE_TIMEOUT,
        )

        if response.status_code == 200:
            data = response.json()
            user_id = data.get("user_id")
            logger.info(
                f"User account created: {user_data.get('username')} (ID: {user_id})"
            )
            return user_id
        else:
            logger.warning(
                f"User creation failed - {response.status_code}: {response.text}"
            )
            return None

    except Exception as e:
        logger.error(f"User creation request failed: {e}")
        return None


def initiate_password_reset(email: str) -> bool:
    """
    Initiate password reset for a user.

    Args:
        email: User's email address

    Returns:
        True if reset request sent successfully, False otherwise
    """
    try:
        payload = {"email": email}

        response = requests.post(
            f"{AUTH_SERVICE_URL}/auth/password-reset",
            json=payload,
            timeout=AUTH_SERVICE_TIMEOUT,
        )

        success = response.status_code == 200
        if success:
            logger.info(f"Password reset initiated for: {email}")
        else:
            logger.warning(
                f"Password reset failed for {email} - {response.status_code}"
            )

        return success

    except Exception as e:
        logger.error(f"Password reset request failed: {e}")
        return False


def logout_user_session(refresh_token: str, access_token: str) -> bool:
    """
    Logout a user session by revoking tokens.

    Args:
        refresh_token: User's refresh token
        access_token: User's access token

    Returns:
        True if logout successful, False otherwise
    """
    try:
        payload = {"refresh_token": refresh_token}
        headers = {"Authorization": f"Bearer {access_token}"}

        response = requests.post(
            f"{AUTH_SERVICE_URL}/auth/logout",
            json=payload,
            headers=headers,
            timeout=AUTH_SERVICE_TIMEOUT,
        )

        success = response.status_code == 200
        if success:
            logger.info("User session logged out successfully")
        else:
            logger.warning(f"User logout failed - {response.status_code}")

        return success

    except Exception as e:
        logger.error(f"User logout request failed: {e}")
        return False
