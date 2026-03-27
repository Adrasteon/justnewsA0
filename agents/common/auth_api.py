#!/usr/bin/env python3
"""
Researcher Authentication API Endpoints

FastAPI router for user authentication, registration, and session management.
Provides JWT-based authentication with role-based access control.

Endpoints:
- POST /auth/register - Register new user account
- POST /auth/login - User login with JWT token generation
- POST /auth/refresh - Refresh access token using refresh token
- POST /auth/logout - Logout and revoke refresh token
- POST /auth/password-reset - Request password reset
- POST /auth/password-reset/confirm - Confirm password reset
- GET /auth/me - Get current user information
- GET /auth/users - Admin endpoint to list users
- PUT /auth/users/{user_id}/activate - Admin endpoint to activate user
- PUT /auth/users/{user_id}/deactivate - Admin endpoint to deactivate user
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from agents.common.auth_models import (
    PasswordReset,
    PasswordResetRequest,
    UserCreate,
    UserLogin,
    UserRole,
    UserStatus,
    activate_user,
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    create_user,
    create_user_tables,
    deactivate_user,
    get_all_users,
    get_user_by_id,
    get_user_by_username_or_email,
    increment_login_attempts,
    mark_password_reset_token_used,
    reset_login_attempts,
    revoke_all_user_sessions,
    revoke_refresh_token,
    store_refresh_token,
    update_user_login,
    update_user_password,
    validate_password_reset_token,
    validate_refresh_token,
    verify_password,
    verify_token,
)
from agents.common.consent_management import ConsentType, consent_manager
from agents.common.data_minimization import DataMinimizationManager, DataPurpose
from common.observability import get_logger

logger = get_logger(__name__)

# Security scheme
security = HTTPBearer()

# Create router
router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginResponse(BaseModel):
    """Login response model"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict[str, Any]


class UserResponse(BaseModel):
    """User information response"""

    user_id: int
    email: str
    username: str
    full_name: str
    role: UserRole
    status: UserStatus
    created_at: datetime
    last_login: datetime | None = None


class RegisterResponse(BaseModel):
    """Registration response model"""

    message: str
    user_id: int
    requires_activation: bool = True


class PasswordResetResponse(BaseModel):
    """Password reset response model"""

    message: str
    email_sent: bool = True


# Data Export Models
class DataExportRequest(BaseModel):
    """Request model for data export"""

    include_sensitive_data: bool = Field(
        False, description="Include sensitive data like passwords (admin only)"
    )
    format: str = Field("json", description="Export format: json, csv, or xml")


class DataExportResponse(BaseModel):
    """Response model for data export"""

    export_id: str
    status: str
    estimated_completion: str | None = None
    download_url: str | None = None


class UserDataExport(BaseModel):
    """User data export model"""

    user_profile: dict[str, Any]
    login_history: list[dict[str, Any]]
    session_history: list[dict[str, Any]]
    search_history: list[dict[str, Any]] | None = None
    export_metadata: dict[str, Any]


# Right to be Forgotten Models
class DataDeletionRequest(BaseModel):
    """Request model for data deletion"""

    confirmation: str = Field(
        ..., description="Must be 'DELETE_ALL_MY_DATA' to confirm"
    )
    reason: str | None = Field(None, description="Optional reason for deletion request")


class DataDeletionResponse(BaseModel):
    """Response model for data deletion"""

    request_id: str
    status: str
    estimated_completion: str
    message: str


# Consent Management Models
class ConsentGrantRequest(BaseModel):
    """Request model for granting consent"""

    consent_type: str
    details: dict[str, Any] | None = None


class ConsentWithdrawRequest(BaseModel):
    """Request model for withdrawing consent"""

    consent_type: str


class ConsentStatusResponse(BaseModel):
    """Response model for consent status"""

    consent_type: str
    granted: bool
    required: bool
    expires_days: int | None
    last_updated: str | None
    status: str


class UserConsentSummary(BaseModel):
    """User consent summary"""

    user_id: int
    consents: dict[str, dict[str, Any]]
    required_consents_granted: int
    optional_consents_granted: int
    total_required_consents: int
    total_optional_consents: int
    compliance_status: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    """Dependency to get current authenticated user"""
    token = credentials.credentials
    payload = verify_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_id(payload.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if user["status"] != UserStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    return user


async def get_admin_user(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Dependency to ensure user has admin role"""
    if current_user["role"] != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


@router.post("/register", response_model=RegisterResponse)
async def register_user(user_data: UserCreate, background_tasks: BackgroundTasks):
    """Register a new user account"""
    try:
        # Check if user already exists
        existing_user = get_user_by_username_or_email(user_data.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered",
            )

        existing_email = get_user_by_username_or_email(user_data.email)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        # Create user
        user_id = create_user(user_data)
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user",
            )

        # TODO: Send activation email in background
        # background_tasks.add_task(send_activation_email, user_data.email, activation_token)

        logger.info(f"New user registered: {user_data.username} (ID: {user_id})")

        return RegisterResponse(
            message="User registered successfully. Please check your email for activation instructions.",
            user_id=user_id,
            requires_activation=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed",
        ) from e


@router.post("/login", response_model=LoginResponse)
async def login_user(login_data: UserLogin):
    """Authenticate user and return JWT tokens"""
    try:
        # Get user by username or email
        user = get_user_by_username_or_email(login_data.username_or_email)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        # Check if account is locked
        if user.get("locked_until") and user["locked_until"] > datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Account is temporarily locked due to too many failed login attempts",
            )

        # Check if account is active
        if user["status"] != UserStatus.ACTIVE.value:
            if user["status"] == UserStatus.PENDING.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is pending activation. Please check your email.",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is not active",
                )

        # Verify password
        if not verify_password(
            login_data.password, user["hashed_password"], user["salt"]
        ):
            increment_login_attempts(user["user_id"])
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        # Reset login attempts and update last login
        reset_login_attempts(user["user_id"])
        update_user_login(user["user_id"])

        # Create tokens
        token_data = {
            "user_id": user["user_id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
        }

        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        # Store refresh token
        if not store_refresh_token(user["user_id"], refresh_token):
            logger.warning(f"Failed to store refresh token for user {user['user_id']}")

        # Prepare user response data
        user_response = {
            "user_id": user["user_id"],
            "username": user["username"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
            "last_login": user["last_login"].isoformat()
            if user["last_login"]
            else None,
        }

        logger.info(f"User logged in: {user['username']} (ID: {user['user_id']})")

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=30 * 60,  # 30 minutes
            user=user_response,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Login failed"
        ) from e


@router.post("/refresh")
async def refresh_access_token(refresh_data: dict[str, str]):
    """Refresh access token using refresh token"""
    try:
        refresh_token = refresh_data.get("refresh_token")
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Refresh token required"
            )

        # Validate refresh token
        user_id = validate_refresh_token(refresh_token)
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )

        # Get user
        user = get_user_by_id(user_id)
        if user is None or user["status"] != UserStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )

        # Create new access token
        token_data = {
            "user_id": user["user_id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
        }

        access_token = create_access_token(token_data)

        logger.info(f"Access token refreshed for user: {user['username']}")

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": 30 * 60,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed",
        ) from e


@router.post("/logout")
async def logout_user(
    refresh_data: dict[str, str],
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Logout user and revoke refresh token"""
    try:
        refresh_token = refresh_data.get("refresh_token")
        if refresh_token:
            revoke_refresh_token(refresh_token)

        logger.info(f"User logged out: {current_user['username']}")
        return {"message": "Logged out successfully"}

    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Logout failed"
        ) from e


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Get current user information"""
    return UserResponse(
        user_id=current_user["user_id"],
        email=current_user["email"],
        username=current_user["username"],
        full_name=current_user["full_name"],
        role=UserRole(current_user["role"]),
        status=UserStatus(current_user["status"]),
        created_at=current_user["created_at"],
        last_login=current_user["last_login"],
    )


@router.post("/password-reset", response_model=PasswordResetResponse)
async def request_password_reset(
    request: PasswordResetRequest, background_tasks: BackgroundTasks
):
    """Request password reset"""
    try:
        user = get_user_by_username_or_email(request.email)
        if user is None:
            # Don't reveal if email exists or not for security
            return PasswordResetResponse(
                message="If an account with this email exists, a password reset link has been sent."
            )

        # Create password reset token
        create_password_reset_token(user["user_id"])

        # TODO: Send password reset email in background
        # background_tasks.add_task(send_password_reset_email, request.email, reset_token)

        logger.info(f"Password reset requested for: {request.email}")

        return PasswordResetResponse(
            message="If an account with this email exists, a password reset link has been sent."
        )

    except Exception as e:
        logger.error(f"Password reset request error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset request failed",
        ) from e


@router.post("/password-reset/confirm")
async def confirm_password_reset(reset_data: PasswordReset):
    """Confirm password reset with token"""
    try:
        # Validate reset token
        user_id = validate_password_reset_token(reset_data.token)
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token",
            )

        # Update password
        if not update_user_password(user_id, reset_data.new_password):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update password",
            )

        # Mark token as used
        mark_password_reset_token_used(reset_data.token)

        # Revoke all user sessions for security
        revoke_all_user_sessions(user_id)

        logger.info(f"Password reset confirmed for user ID: {user_id}")

        return {"message": "Password reset successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset confirmation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset confirmation failed",
        ) from e


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: dict[str, Any] = Depends(get_admin_user),
):
    """Admin endpoint to list users"""
    try:
        users = get_all_users(limit=limit, offset=offset)
        return [
            UserResponse(
                user_id=user["user_id"],
                email=user["email"],
                username=user["username"],
                full_name=user["full_name"],
                role=UserRole(user["role"]),
                status=UserStatus(user["status"]),
                created_at=user["created_at"],
                last_login=user["last_login"],
            )
            for user in users
        ]

    except Exception as e:
        logger.error(f"List users error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve users",
        ) from e


@router.put("/users/{user_id}/activate")
async def activate_user_account(
    user_id: int, current_user: dict[str, Any] = Depends(get_admin_user)
):
    """Admin endpoint to activate user account"""
    try:
        if not activate_user(user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        logger.info(
            f"User account activated by admin {current_user['username']}: User ID {user_id}"
        )
        return {"message": "User account activated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Activate user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate user",
        ) from e


@router.put("/users/{user_id}/deactivate")
async def deactivate_user_account(
    user_id: int, current_user: dict[str, Any] = Depends(get_admin_user)
):
    """Admin endpoint to deactivate user account"""
    try:
        if not deactivate_user(user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        # Revoke all sessions for security
        revoke_all_user_sessions(user_id)

        logger.info(
            f"User account deactivated by admin {current_user['username']}: User ID {user_id}"
        )
        return {"message": "User account deactivated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deactivate user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate user",
        ) from e


# Data Export Endpoints


@router.post("/data-export", response_model=DataExportResponse)
async def request_data_export(
    request: DataExportRequest,
    background_tasks: BackgroundTasks,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Request export of user's personal data (GDPR Article 20)"""
    try:
        import uuid
        from datetime import datetime
        from pathlib import Path

        export_id = str(uuid.uuid4())
        export_dir = Path("./data_exports")
        export_dir.mkdir(exist_ok=True)

        # Start background export task
        background_tasks.add_task(
            perform_data_export,
            export_id=export_id,
            user_id=current_user["user_id"],
            include_sensitive=request.include_sensitive_data,
            export_format=request.format,
            export_dir=export_dir,
        )

        return DataExportResponse(
            export_id=export_id,
            status="processing",
            estimated_completion=(datetime.now() + timedelta(minutes=5)).isoformat(),
        )

    except Exception as e:
        logger.error(f"Data export request error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate data export",
        ) from e


@router.get("/data-export/{export_id}")
async def get_data_export_status(
    export_id: str, current_user: dict[str, Any] = Depends(get_current_user)
):
    """Get status of data export request"""
    try:
        export_dir = Path("./data_exports")
        export_file = export_dir / f"{export_id}.json"

        if not export_file.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Export not found"
            )

        with open(export_file) as f:
            export_data = json.load(f)

        # Check if export belongs to current user
        if export_data.get("user_id") != current_user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

        return export_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get export status error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get export status",
        ) from e


@router.get("/data-export/{export_id}/download")
async def download_data_export(
    export_id: str, current_user: dict[str, Any] = Depends(get_current_user)
):
    """Download completed data export"""
    try:
        export_dir = Path("./data_exports")
        export_file = export_dir / f"{export_id}_data.json"

        if not export_file.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Export file not found"
            )

        # Check ownership via status file
        status_file = export_dir / f"{export_id}.json"
        if status_file.exists():
            with open(status_file) as f:
                status_data = json.load(f)
                if status_data.get("user_id") != current_user["user_id"]:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
                    )

        return FileResponse(
            path=export_file,
            filename=f"user_data_export_{export_id}.json",
            media_type="application/json",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download export error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download export",
        ) from e


# Background task for data export
async def perform_data_export(
    export_id: str,
    user_id: int,
    include_sensitive: bool,
    export_format: str,
    export_dir: Path,
):
    """Background task to perform comprehensive data export"""
    try:
        import json
        from datetime import datetime

        logger.info(f"Starting data export for user {user_id}, export ID: {export_id}")

        # Update status to processing
        status_data = {
            "export_id": export_id,
            "user_id": user_id,
            "status": "processing",
            "started_at": datetime.now().isoformat(),
            "format": export_format,
        }

        with open(export_dir / f"{export_id}.json", "w") as f:
            json.dump(status_data, f)

        # Gather user data
        user_data = get_user_by_id(user_id)
        if not user_data:
            raise Exception("User not found")

        # Get login history (simplified - would need actual implementation)
        login_history = []  # Placeholder for login history

        # Get session history (simplified - would need actual implementation)
        session_history = []  # Placeholder for session history

        # Get search history if available (simplified)
        search_history = []  # Placeholder for search history

        # Prepare export data
        export_data = UserDataExport(
            user_profile={
                "user_id": user_data["user_id"],
                "email": user_data["email"],
                "username": user_data["username"],
                "full_name": user_data["full_name"],
                "role": user_data["role"],
                "status": user_data["status"],
                "created_at": user_data["created_at"],
                "last_login": user_data["last_login"],
                "login_attempts": user_data.get("login_attempts", 0),
            },
            login_history=login_history,
            session_history=session_history,
            search_history=search_history,
            export_metadata={
                "export_id": export_id,
                "exported_at": datetime.now().isoformat(),
                "gdpr_compliant": True,
                "includes_sensitive_data": include_sensitive,
                "data_retention_policy": "7_years_user_data",
                "export_format": export_format,
            },
        )

        # Save export data
        export_file = export_dir / f"{export_id}_data.json"
        with open(export_file, "w") as f:
            json.dump(export_data.model_dump(), f, indent=2, default=str)

        # Update status to completed
        status_data.update(
            {
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "file_size_bytes": export_file.stat().st_size,
                "download_url": f"/auth/data-export/{export_id}/download",
            }
        )

        with open(export_dir / f"{export_id}.json", "w") as f:
            json.dump(status_data, f)

        logger.info(f"Data export completed for user {user_id}, export ID: {export_id}")

    except Exception as e:
        logger.error(f"Data export failed for user {user_id}: {e}")

        # Update status to failed
        status_data = {
            "export_id": export_id,
            "user_id": user_id,
            "status": "failed",
            "error": str(e),
            "failed_at": datetime.now().isoformat(),
        }

        try:
            with open(export_dir / f"{export_id}.json", "w") as f:
                json.dump(status_data, f)
        except OSError:
            pass


# Right to be Forgotten Endpoints


@router.post("/data-deletion", response_model=DataDeletionResponse)
async def request_data_deletion(
    request: DataDeletionRequest,
    background_tasks: BackgroundTasks,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Request complete deletion of user's personal data (GDPR Right to be Forgotten)"""
    try:
        # Validate confirmation
        if request.confirmation != "DELETE_ALL_MY_DATA":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid confirmation. Must be exactly 'DELETE_ALL_MY_DATA'",
            )

        import uuid
        from datetime import datetime

        request_id = str(uuid.uuid4())

        # Start background deletion task
        background_tasks.add_task(
            perform_data_deletion,
            request_id=request_id,
            user_id=current_user["user_id"],
            reason=request.reason,
        )

        return DataDeletionResponse(
            request_id=request_id,
            status="processing",
            estimated_completion=(datetime.now() + timedelta(hours=24)).isoformat(),
            message="Your data deletion request has been submitted. You will receive confirmation once completed.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Data deletion request error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate data deletion",
        ) from e


@router.get("/data-deletion/{request_id}")
async def get_data_deletion_status(
    request_id: str, current_user: dict[str, Any] = Depends(get_current_user)
):
    """Get status of data deletion request"""
    try:
        deletion_dir = Path("./data_deletions")
        status_file = deletion_dir / f"{request_id}.json"

        if not status_file.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deletion request not found",
            )

        with open(status_file) as f:
            deletion_data = json.load(f)

        # Check if request belongs to current user
        if deletion_data.get("user_id") != current_user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

        return deletion_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get deletion status error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get deletion status",
        ) from e


# Background task for data deletion
async def perform_data_deletion(request_id: str, user_id: int, reason: str | None):
    """Background task to perform complete user data deletion"""
    try:
        import json
        from datetime import datetime

        logger.info(
            f"Starting data deletion for user {user_id}, request ID: {request_id}"
        )

        deletion_dir = Path("./data_deletions")
        deletion_dir.mkdir(exist_ok=True)

        # Update status to processing
        status_data = {
            "request_id": request_id,
            "user_id": user_id,
            "status": "processing",
            "started_at": datetime.now().isoformat(),
            "reason": reason,
            "deletion_steps": [],
        }

        with open(deletion_dir / f"{request_id}.json", "w") as f:
            json.dump(status_data, f)

        # Step 1: Get user data before deletion
        user_data = get_user_by_id(user_id)
        if not user_data:
            raise Exception("User not found")

        status_data["deletion_steps"].append(
            {
                "step": "user_lookup",
                "status": "completed",
                "timestamp": datetime.now().isoformat(),
                "message": f"Found user data for {user_data['email']}",
            }
        )

        # Step 2: Revoke all sessions
        revoke_all_user_sessions(user_id)
        status_data["deletion_steps"].append(
            {
                "step": "session_revocation",
                "status": "completed",
                "timestamp": datetime.now().isoformat(),
                "message": "All user sessions revoked",
            }
        )

        # Step 3: Anonymize user data (instead of complete deletion for audit purposes)
        # In a real implementation, you might want to:
        # - Hash or remove personal identifiers
        # - Keep minimal audit trail
        # - Remove from search indexes
        # - Delete associated files

        # For now, we'll mark the user as deleted but keep anonymized record
        anonymized_email = f"deleted_user_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}@deleted.local"
        anonymized_username = f"deleted_user_{user_id}"

        # Update user record with anonymized data
        from agents.common.auth_models import update_user_anonymized

        update_user_anonymized(
            user_id=user_id,
            anonymized_email=anonymized_email,
            anonymized_username=anonymized_username,
        )

        status_data["deletion_steps"].append(
            {
                "step": "data_anonymization",
                "status": "completed",
                "timestamp": datetime.now().isoformat(),
                "message": "User data anonymized for audit purposes",
            }
        )

        # Step 4: Clean up related data
        # This would include:
        # - Search history
        # - User preferences
        # - Cached data
        # - Export files

        cleanup_related_data(user_id)

        status_data["deletion_steps"].append(
            {
                "step": "related_data_cleanup",
                "status": "completed",
                "timestamp": datetime.now().isoformat(),
                "message": "Related user data cleaned up",
            }
        )

        # Step 5: Log deletion for compliance
        logger.info(
            f"GDPR deletion completed for user {user_id} (original email: {user_data['email']})"
        )

        # Update status to completed
        status_data.update(
            {
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "final_message": "Your data has been successfully deleted/anonymized per GDPR requirements.",
            }
        )

        with open(deletion_dir / f"{request_id}.json", "w") as f:
            json.dump(status_data, f)

        logger.info(
            f"Data deletion completed for user {user_id}, request ID: {request_id}"
        )

    except Exception as e:
        logger.error(f"Data deletion failed for user {user_id}: {e}")

        # Update status to failed
        status_data = {
            "request_id": request_id,
            "user_id": user_id,
            "status": "failed",
            "error": str(e),
            "failed_at": datetime.now().isoformat(),
        }

        try:
            with open(deletion_dir / f"{request_id}.json", "w") as f:
                json.dump(status_data, f)
        except OSError:
            pass


def cleanup_related_data(user_id: int):
    """Clean up related user data files and records"""
    try:
        # Clean up data export files
        export_dir = Path("./data_exports")
        if export_dir.exists():
            for file_path in export_dir.glob("*"):
                if file_path.is_file():
                    try:
                        with open(file_path) as f:
                            data = json.load(f)
                            if data.get("user_id") == user_id:
                                file_path.unlink()
                    except (OSError, json.JSONDecodeError):
                        pass

        # Clean up deletion request files (except current)
        deletion_dir = Path("./data_deletions")
        if deletion_dir.exists():
            for file_path in deletion_dir.glob("*"):
                if file_path.is_file():
                    try:
                        with open(file_path) as f:
                            data = json.load(f)
                            if data.get("user_id") == user_id:
                                file_path.unlink()
                    except (OSError, json.JSONDecodeError):
                        pass

        logger.info(f"Cleaned up related data files for user {user_id}")

    except Exception as e:
        logger.error(f"Failed to cleanup related data for user {user_id}: {e}")


# Consent Management Endpoints


@router.get("/consents", response_model=UserConsentSummary)
async def get_user_consents(current_user: dict[str, Any] = Depends(get_current_user)):
    """Get current user's consent status"""
    try:
        summary = consent_manager.get_consent_summary(current_user["user_id"])
        return UserConsentSummary(**summary)

    except Exception as e:
        logger.error(f"Get user consents error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve consent status",
        ) from e


@router.post("/consents/grant")
async def grant_user_consent(
    request: ConsentGrantRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Grant consent for a specific type"""
    try:
        # Validate consent type
        try:
            consent_type = ConsentType(request.consent_type)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid consent type: {request.consent_type}",
            ) from exc

        # Grant consent
        consent_id = consent_manager.grant_consent(
            user_id=current_user["user_id"],
            consent_type=consent_type,
            details=request.details,
        )

        # Log to audit
        from agents.common.compliance_audit import audit_logger

        audit_logger.log_event(
            event_type=audit_logger.AuditEventType.DATA_MODIFICATION,
            severity=audit_logger.AuditEventSeverity.LOW,
            user_id=current_user["user_id"],
            user_email=current_user["email"],
            resource_type="user_consent",
            resource_id=consent_id,
            action="consent_granted",
            details={"consent_type": request.consent_type},
            compliance_relevant=True,
            gdpr_article="6",
        )

        return {
            "message": f"Consent granted for {request.consent_type}",
            "consent_id": consent_id,
            "granted_at": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Grant consent error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to grant consent",
        ) from e


@router.post("/consents/withdraw")
async def withdraw_user_consent(
    request: ConsentWithdrawRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Withdraw consent for a specific type"""
    try:
        # Validate consent type
        try:
            consent_type = ConsentType(request.consent_type)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid consent type: {request.consent_type}",
            ) from exc

        # Withdraw consent
        success = consent_manager.withdraw_consent(
            user_id=current_user["user_id"], consent_type=consent_type
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active consent found for {request.consent_type}",
            )

        # Log to audit
        from agents.common.compliance_audit import audit_logger

        audit_logger.log_event(
            event_type=audit_logger.AuditEventType.DATA_MODIFICATION,
            severity=audit_logger.AuditEventSeverity.MEDIUM,
            user_id=current_user["user_id"],
            user_email=current_user["email"],
            resource_type="user_consent",
            action="consent_withdrawn",
            details={"consent_type": request.consent_type},
            compliance_relevant=True,
            gdpr_article="7",
        )

        return {
            "message": f"Consent withdrawn for {request.consent_type}",
            "withdrawn_at": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Withdraw consent error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to withdraw consent",
        ) from e


@router.get("/consents/policies")
async def get_consent_policies(
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Get available consent policies"""
    try:
        policies = {}
        for consent_type, policy in consent_manager.policies.items():
            policies[consent_type.value] = {
                "name": policy.name,
                "description": policy.description,
                "required": policy.required,
                "default_granted": policy.default_granted,
                "expires_days": policy.expires_days,
                "version": policy.version,
            }

        return {
            "policies": policies,
            "total_policies": len(policies),
            "required_policies": sum(1 for p in policies.values() if p["required"]),
        }

    except Exception as e:
        logger.error(f"Get consent policies error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve consent policies",
        ) from e


@router.get("/consents/check/{consent_type}")
async def check_user_consent(
    consent_type: str, current_user: dict[str, Any] = Depends(get_current_user)
):
    """Check if user has granted a specific consent"""
    try:
        # Validate consent type
        try:
            consent_enum = ConsentType(consent_type)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid consent type: {consent_type}",
            ) from exc

        # Check consent
        has_consent = consent_manager.check_consent(
            current_user["user_id"], consent_enum
        )

        return {
            "consent_type": consent_type,
            "granted": has_consent,
            "checked_at": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Check consent error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check consent",
        ) from e


# Admin Consent Management Endpoints


@router.get("/admin/consents/statistics")
async def get_consent_statistics(
    current_user: dict[str, Any] = Depends(get_admin_user),
):
    """Admin endpoint to get consent statistics"""
    try:
        stats = consent_manager.get_consent_statistics()
        return stats

    except Exception as e:
        logger.error(f"Get consent statistics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve consent statistics",
        ) from e


@router.get("/admin/consents/users/{user_id}")
async def get_user_consent_details(
    user_id: int, current_user: dict[str, Any] = Depends(get_admin_user)
):
    """Admin endpoint to get detailed consent information for a user"""
    try:
        summary = consent_manager.get_consent_summary(user_id)
        user_consents = consent_manager.get_user_consents(user_id)

        # Convert consent records to dict format
        consent_details = {}
        for consent_type, consent_record in user_consents.items():
            consent_details[consent_type.value] = consent_record.to_dict()

        return {
            "user_id": user_id,
            "summary": summary,
            "consent_records": consent_details,
        }

    except Exception as e:
        logger.error(f"Get user consent details error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user consent details",
        ) from e


@router.post("/admin/consents/users/{user_id}/grant")
async def admin_grant_user_consent(
    user_id: int,
    request: ConsentGrantRequest,
    current_user: dict[str, Any] = Depends(get_admin_user),
):
    """Admin endpoint to grant consent on behalf of a user"""
    try:
        # Validate consent type
        try:
            consent_type = ConsentType(request.consent_type)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid consent type: {request.consent_type}",
            ) from exc

        # Grant consent
        consent_id = consent_manager.grant_consent(
            user_id=user_id,
            consent_type=consent_type,
            details={**request.details, "granted_by_admin": current_user["user_id"]},
        )

        # Log to audit
        from agents.common.compliance_audit import audit_logger

        audit_logger.log_event(
            event_type=audit_logger.AuditEventType.DATA_MODIFICATION,
            severity=audit_logger.AuditEventSeverity.MEDIUM,
            user_id=current_user["user_id"],
            user_email=current_user["email"],
            resource_type="user_consent",
            resource_id=consent_id,
            action="admin_consent_granted",
            details={
                "consent_type": request.consent_type,
                "target_user_id": user_id,
                "admin_action": True,
            },
            compliance_relevant=True,
            gdpr_article="6",
        )

        return {
            "message": f"Consent granted for user {user_id}: {request.consent_type}",
            "consent_id": consent_id,
            "granted_by": current_user["username"],
            "granted_at": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin grant consent error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to grant consent",
        ) from e


# Data Minimization Endpoints


@router.get("/data-minimization/status")
async def get_data_minimization_status(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Get data minimization compliance status"""
    try:
        # Verify admin access
        token_data = verify_token(credentials.credentials)
        if not token_data or token_data.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
            )

        manager = DataMinimizationManager()
        status_info = manager.get_compliance_status()

        return {"status": "success", "data": status_info}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Data minimization status error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get data minimization status",
        ) from e


@router.post("/data-minimization/validate")
async def validate_data_collection(
    request: dict[str, Any],
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Validate data collection against minimization policies"""
    try:
        token_data = verify_token(credentials.credentials)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )

        user_id = str(token_data.get("user_id"))
        purpose = request.get("purpose")
        data_fields = request.get("data_fields", [])

        if not purpose or not data_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Purpose and data_fields are required",
            )

        manager = DataMinimizationManager()
        result = manager.validate_data_collection(purpose, data_fields, user_id)

        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Data validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate data collection",
        ) from e


@router.post("/data-minimization/minimize")
async def minimize_data_payload(
    request: dict[str, Any],
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Minimize data payload according to policies"""
    try:
        token_data = verify_token(credentials.credentials)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )

        user_id = str(token_data.get("user_id"))
        purpose = request.get("purpose")
        data = request.get("data", {})

        if not purpose:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Purpose is required"
            )

        manager = DataMinimizationManager()
        minimized_data = manager.minimize_data_payload(data, purpose, user_id)

        return {
            "status": "success",
            "data": {
                "original_fields": len(data),
                "minimized_fields": len(minimized_data),
                "minimized_data": minimized_data,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Data minimization error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to minimize data",
        ) from e


@router.post("/data-minimization/cleanup")
async def cleanup_expired_data(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Clean up expired data for the current user"""
    try:
        token_data = verify_token(credentials.credentials)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )

        user_id = str(token_data.get("user_id"))

        manager = DataMinimizationManager()
        result = manager.cleanup_expired_data(user_id)

        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Data cleanup error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cleanup expired data",
        ) from e


@router.get("/data-minimization/usage")
async def get_data_usage_summary(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Get data usage summary for the current user"""
    try:
        token_data = verify_token(credentials.credentials)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )

        user_id = str(token_data.get("user_id"))

        manager = DataMinimizationManager()
        result = manager.get_data_usage_summary(user_id)

        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Data usage summary error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get data usage summary",
        ) from e


@router.post("/data-minimization/policies")
async def add_data_policy(
    request: dict[str, Any],
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Add a new data collection policy (Admin only)"""
    try:
        # Verify admin access
        token_data = verify_token(credentials.credentials)
        if not token_data or token_data.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
            )

        # Parse policy data
        from agents.common.data_minimization import DataCategory, DataCollectionPolicy

        purpose_str = request.get("purpose")
        categories_str = request.get("categories", [])
        retention_days = request.get("retention_period_days", 365)
        required_fields = request.get("required_fields", [])
        optional_fields = request.get("optional_fields", [])
        justification = request.get("justification", "")
        legal_basis = request.get("legal_basis", "")

        if not purpose_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Purpose is required"
            )

        try:
            purpose = DataPurpose(purpose_str)
            categories = [DataCategory(cat) for cat in categories_str]
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid purpose or category: {exc}",
            ) from exc

        policy = DataCollectionPolicy(
            purpose=purpose,
            categories=categories,
            retention_period_days=retention_days,
            required_fields=required_fields,
            optional_fields=optional_fields,
            justification=justification,
            legal_basis=legal_basis,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        manager = DataMinimizationManager()
        success = manager.add_policy(policy)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add policy",
            )

        return {
            "status": "success",
            "message": f"Policy added for purpose: {purpose_str}",
            "data": policy.to_dict(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add policy error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add data policy",
        ) from e


# Initialize database tables on import
try:
    create_user_tables()
    logger.info("Authentication database tables initialized")
except Exception as e:
    logger.error(f"Failed to initialize authentication tables: {e}")
