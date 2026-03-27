"""
JustNews Authentication Service

Handles user authentication, session management, JWT tokens, and identity verification.
"""

import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import aiofiles
import bcrypt
import jwt
from cryptography.fernet import Fernet
from pydantic import BaseModel, Field, validator

from ..models import AuthenticationError, SecurityConfig

logger = logging.getLogger(__name__)


class UserCredentials(BaseModel):
    """User credentials for authentication"""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)

    @validator("username")
    def username_alphanumeric(cls, v):
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                "Username must be alphanumeric with optional underscores or hyphens"
            )
        return v


class LoginRequest(BaseModel):
    """Login request model"""

    username: str
    password: str
    mfa_code: str | None = None


class TokenPair(BaseModel):
    """JWT token pair"""

    access_token: str
    refresh_token: str
    expires_at: datetime


class MFASetup(BaseModel):
    """MFA setup information"""

    secret: str
    qr_code_url: str
    backup_codes: list[str]


class AuthenticationService:
    """
    Authentication service for user management and token handling

    Provides comprehensive authentication including password validation,
    JWT token management, MFA support, and session handling.
    """

    def __init__(self, config: SecurityConfig):
        self.config = config
        self._user_store: dict[str, dict[str, Any]] = {}  # username -> user data
        self._refresh_tokens: dict[str, dict[str, Any]] = {}  # token -> metadata
        self._mfa_secrets: dict[int, str] = {}  # user_id -> MFA secret
        self._encryption = Fernet(self._get_encryption_key())

    def _get_encryption_key(self) -> bytes:
        """Get encryption key for sensitive data"""
        if self.config.encryption_key:
            return self.config.encryption_key.encode()
        # Generate a key if not provided (not recommended for production)
        return Fernet.generate_key()

    async def initialize(self) -> None:
        """Initialize authentication service"""
        # Load user data from storage if available
        await self._load_user_data()
        logger.info("AuthenticationService initialized")

    async def shutdown(self) -> None:
        """Shutdown authentication service"""
        await self._save_user_data()
        logger.info("AuthenticationService shutdown")

    async def authenticate(self, username: str, password: str) -> dict[str, Any]:
        """
        Authenticate user with username and password

        Args:
            username: User username
            password: User password

        Returns:
            User data dictionary

        Raises:
            AuthenticationError: If authentication fails
        """
        # Get user data
        user_data = self._user_store.get(username.lower())
        if not user_data:
            raise AuthenticationError("Invalid username or password")

        # Check if account is active
        if not user_data.get("is_active", True):
            raise AuthenticationError("Account is disabled")

        # Check if account is locked
        if user_data.get("locked_until"):
            locked_until = datetime.fromisoformat(user_data["locked_until"])
            if locked_until > datetime.now(UTC):
                raise AuthenticationError("Account is temporarily locked")

        # Verify password
        hashed_password = user_data["password_hash"]
        if not bcrypt.checkpw(password.encode(), hashed_password.encode()):
            # Increment failed login attempts
            user_data["login_attempts"] = user_data.get("login_attempts", 0) + 1

            # Lock account if too many attempts
            if user_data["login_attempts"] >= self.config.max_login_attempts:
                lock_duration = timedelta(minutes=30)  # 30 minute lockout
                user_data["locked_until"] = (
                    datetime.now(UTC) + lock_duration
                ).isoformat()

            await self._save_user_data()
            raise AuthenticationError("Invalid username or password")

        # Reset login attempts on successful authentication
        user_data["login_attempts"] = 0
        user_data["locked_until"] = None
        await self._save_user_data()

        return user_data

    async def generate_tokens(self, user_id: int, roles: list[str]) -> dict[str, str]:
        """
        Generate JWT access and refresh tokens

        Args:
            user_id: User ID
            roles: User roles

        Returns:
            Dict with access_token and refresh_token
        """
        now = datetime.now(UTC)
        session_id = secrets.token_urlsafe(32)

        # Access token payload
        access_payload = {
            "sub": str(user_id),
            "roles": roles,
            "session_id": session_id,
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int(
                (now + timedelta(hours=self.config.jwt_expiration_hours)).timestamp()
            ),
        }

        # Refresh token payload
        refresh_payload = {
            "sub": str(user_id),
            "session_id": session_id,
            "type": "refresh",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=30)).timestamp()),  # 30 days
        }

        # Generate tokens
        access_token = jwt.encode(
            access_payload, self.config.jwt_secret, algorithm=self.config.jwt_algorithm
        )

        refresh_token = jwt.encode(
            refresh_payload, self.config.jwt_secret, algorithm=self.config.jwt_algorithm
        )

        # Store refresh token metadata
        self._refresh_tokens[refresh_token] = {
            "user_id": user_id,
            "session_id": session_id,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=30)).isoformat(),
        }

        return {"access_token": access_token, "refresh_token": refresh_token}

    async def validate_token(self, token: str) -> dict[str, Any]:
        """
        Validate JWT token

        Args:
            token: JWT token to validate

        Returns:
            Decoded token payload

        Raises:
            AuthenticationError: If token is invalid
        """
        try:
            # Decode token
            payload = jwt.decode(
                token, self.config.jwt_secret, algorithms=[self.config.jwt_algorithm]
            )

            # Check token type
            if payload.get("type") not in ["access", "refresh"]:
                raise AuthenticationError("Invalid token type")

            # For refresh tokens, check if still valid in our store
            if payload["type"] == "refresh":
                if token not in self._refresh_tokens:
                    raise AuthenticationError("Refresh token revoked")

                token_data = self._refresh_tokens[token]
                if datetime.fromisoformat(token_data["expires_at"]) < datetime.now(UTC):
                    del self._refresh_tokens[token]
                    raise AuthenticationError("Refresh token expired")

            return payload

        except jwt.ExpiredSignatureError as exc:
            # Chain specific JWT exception for clearer tracebacks
            raise AuthenticationError("Token expired") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthenticationError("Invalid token") from exc
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            raise AuthenticationError("Token validation failed") from e

    async def refresh_access_token(self, refresh_token: str) -> dict[str, str]:
        """
        Generate new access token using refresh token

        Args:
            refresh_token: Valid refresh token

        Returns:
            New token pair

        Raises:
            AuthenticationError: If refresh token is invalid
        """
        # Validate refresh token
        payload = await self.validate_token(refresh_token)

        if payload["type"] != "refresh":
            raise AuthenticationError("Invalid token type for refresh")

        # Get user data
        user_id = int(payload["sub"])
        user_data = await self.get_user_info(user_id)

        # Generate new tokens
        return await self.generate_tokens(user_id, user_data["roles"])

    async def revoke_token(self, token: str) -> None:
        """
        Revoke a refresh token

        Args:
            token: Token to revoke
        """
        if token in self._refresh_tokens:
            del self._refresh_tokens[token]

    async def revoke_all_user_tokens(self, user_id: int) -> None:
        """
        Revoke all refresh tokens for a user

        Args:
            user_id: User ID
        """
        tokens_to_remove = []
        for token, data in self._refresh_tokens.items():
            if data["user_id"] == user_id:
                tokens_to_remove.append(token)

        for token in tokens_to_remove:
            del self._refresh_tokens[token]

    async def create_user(
        self, username: str, email: str, password: str, roles: list[str] | None = None
    ) -> int:
        """
        Create new user account

        Args:
            username: Unique username
            email: User email
            password: User password
            roles: Optional user roles

        Returns:
            New user ID

        Raises:
            AuthenticationError: If user already exists
        """
        # Check if user exists
        if username.lower() in self._user_store:
            raise AuthenticationError("Username already exists")

        # Hash password
        password_hash = bcrypt.hashpw(
            password.encode(), bcrypt.gensalt(self.config.bcrypt_rounds)
        ).decode()

        # Generate user ID
        user_id = (
            max([u.get("id", 0) for u in self._user_store.values()], default=0) + 1
        )

        # Create user data
        user_data = {
            "id": user_id,
            "username": username,
            "email": email,
            "password_hash": password_hash,
            "roles": roles or ["user"],
            "is_active": True,
            "created_at": datetime.now(UTC).isoformat(),
            "last_login": None,
            "mfa_enabled": False,
            "login_attempts": 0,
            "locked_until": None,
        }

        self._user_store[username.lower()] = user_data
        await self._save_user_data()

        logger.info(f"Created user {username} with ID {user_id}")
        return user_id

    async def update_user(self, user_id: int, updates: dict[str, Any]) -> None:
        """
        Update user information

        Args:
            user_id: User ID
            updates: Fields to update
        """
        user_data = None
        username = None

        for uname, data in self._user_store.items():
            if data["id"] == user_id:
                user_data = data
                username = uname
                break

        if not user_data:
            raise AuthenticationError("User not found")

        # Update fields
        for key, value in updates.items():
            if key == "password":
                # Hash new password
                user_data["password_hash"] = bcrypt.hashpw(
                    value.encode(), bcrypt.gensalt(self.config.bcrypt_rounds)
                ).decode()
            elif key == "username":
                # Check if new username is available
                if value.lower() != username and value.lower() in self._user_store:
                    raise AuthenticationError("Username already exists")
                # Move user data to new username key
                del self._user_store[username]
                self._user_store[value.lower()] = user_data
                username = value.lower()
            else:
                user_data[key] = value

        await self._save_user_data()

    async def delete_user(self, user_id: int) -> None:
        """
        Delete user account

        Args:
            user_id: User ID to delete
        """
        username = None
        for uname, data in self._user_store.items():
            if data["id"] == user_id:
                username = uname
                break

        if username:
            del self._user_store[username]
            await self._save_user_data()
            await self.revoke_all_user_tokens(user_id)
            logger.info(f"Deleted user {username} (ID: {user_id})")

    async def get_user_info(self, user_id: int) -> dict[str, Any]:
        """
        Get user information

        Args:
            user_id: User ID

        Returns:
            User data dictionary
        """
        for user_data in self._user_store.values():
            if user_data["id"] == user_id:
                # Return copy without sensitive data
                return {
                    "id": user_data["id"],
                    "username": user_data["username"],
                    "email": user_data["email"],
                    "roles": user_data["roles"],
                    "is_active": user_data["is_active"],
                    "created_at": user_data["created_at"],
                    "last_login": user_data["last_login"],
                    "mfa_enabled": user_data["mfa_enabled"],
                }

        raise AuthenticationError("User not found")

    async def update_last_login(self, user_id: int) -> None:
        """
        Update user's last login timestamp

        Args:
            user_id: User ID
        """
        for user_data in self._user_store.values():
            if user_data["id"] == user_id:
                user_data["last_login"] = datetime.now(UTC).isoformat()
                await self._save_user_data()
                break

    async def setup_mfa(self, user_id: int) -> MFASetup:
        """
        Setup MFA for user

        Args:
            user_id: User ID

        Returns:
            MFA setup information
        """
        import base64
        import io

        import pyotp
        import qrcode

        # Generate MFA secret
        secret = pyotp.random_base32()
        self._mfa_secrets[user_id] = secret

        # Generate QR code
        totp = pyotp.TOTP(secret)
        user_data = await self.get_user_info(user_id)

        provisioning_uri = totp.provisioning_uri(
            name=user_data["email"], issuer_name="JustNews"
        )

        # Generate QR code image
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        qr_code_data = base64.b64encode(buffer.getvalue()).decode()

        # Generate backup codes
        backup_codes = [secrets.token_hex(4) for _ in range(10)]

        return MFASetup(
            secret=secret,
            qr_code_url=f"data:image/png;base64,{qr_code_data}",
            backup_codes=backup_codes,
        )

    async def verify_mfa(self, user_id: int, code: str) -> bool:
        """
        Verify MFA code

        Args:
            user_id: User ID
            code: MFA code to verify

        Returns:
            True if code is valid
        """
        import pyotp

        secret = self._mfa_secrets.get(user_id)
        if not secret:
            return False

        totp = pyotp.TOTP(secret)
        return totp.verify(code)

    async def enable_mfa(self, user_id: int) -> None:
        """
        Enable MFA for user

        Args:
            user_id: User ID
        """
        for user_data in self._user_store.values():
            if user_data["id"] == user_id:
                user_data["mfa_enabled"] = True
                await self._save_user_data()
                break

    async def disable_mfa(self, user_id: int) -> None:
        """
        Disable MFA for user

        Args:
            user_id: User ID
        """
        for user_data in self._user_store.values():
            if user_data["id"] == user_id:
                user_data["mfa_enabled"] = False
                if user_id in self._mfa_secrets:
                    del self._mfa_secrets[user_id]
                await self._save_user_data()
                break

    async def get_status(self) -> dict[str, Any]:
        """
        Get authentication service status

        Returns:
            Status information
        """
        return {
            "status": "healthy",
            "total_users": len(self._user_store),
            "active_sessions": len(self._refresh_tokens),
            "mfa_enabled_users": sum(
                1 for u in self._user_store.values() if u.get("mfa_enabled", False)
            ),
        }

    async def _load_user_data(self) -> None:
        """Load user data from persistent storage"""
        try:
            async with aiofiles.open("data/users.json") as f:
                data = json.loads(await f.read())
                self._user_store = data.get("users", {})
                self._mfa_secrets = data.get("mfa_secrets", {})
                logger.info(f"Loaded {len(self._user_store)} users from storage")
        except FileNotFoundError:
            logger.info("No user data file found, starting with empty store")
        except Exception as e:
            logger.error(f"Failed to load user data: {e}")

    async def _save_user_data(self) -> None:
        """Save user data to persistent storage"""
        try:
            data = {"users": self._user_store, "mfa_secrets": self._mfa_secrets}
            async with aiofiles.open("data/users.json", "w") as f:
                await f.write(json.dumps(data, indent=2))
        except Exception as e:
            logger.error(f"Failed to save user data: {e}")
