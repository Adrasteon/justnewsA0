"""
User authentication and authorization models for JustNews
Provides JWT-based authentication with role-based access control
"""

import hashlib
import os
import secrets
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from enum import Enum

import jwt
from pydantic import BaseModel, EmailStr

from common.observability import get_logger
from database.utils.migrated_database_utils import create_database_service

# Authentication Database Configuration (separate from main app database)
AUTH_MARIADB_HOST = os.environ.get(
    "AUTH_MARIADB_HOST", os.environ.get("AUTH_POSTGRES_HOST", "localhost")
)
AUTH_MARIADB_DB = os.environ.get(
    "AUTH_MARIADB_DB", os.environ.get("AUTH_POSTGRES_DB", "justnews_auth")
)
AUTH_MARIADB_USER = os.environ.get(
    "AUTH_MARIADB_USER", os.environ.get("AUTH_POSTGRES_USER", "justnews_auth_user")
)
AUTH_MARIADB_PASSWORD = os.environ.get(
    "AUTH_MARIADB_PASSWORD",
    os.environ.get("AUTH_POSTGRES_PASSWORD", "auth_secure_password_2025"),
)

# Authentication connection pool configuration
AUTH_POOL_MIN_CONNECTIONS = int(os.environ.get("AUTH_DB_POOL_MIN_CONNECTIONS", "1"))
AUTH_POOL_MAX_CONNECTIONS = int(os.environ.get("AUTH_DB_POOL_MAX_CONNECTIONS", "5"))

# Authentication connection pool (separate from main app pool)
_auth_service = None

logger = get_logger(__name__)


def initialize_auth_db_service():
    """Initialize or return the migrated DB service to be used for auth storage."""
    global _auth_service
    if _auth_service is not None:
        return _auth_service

    _auth_service = create_database_service()
    logger.info("Authentication database service initialized via migrated DB service")
    return _auth_service


# Backwards-compatibility: legacy callers expect a connection pool API for
# authentication DBs (initialize_auth_connection_pool, get_auth_connection_pool)
# Historically these returned a pool with getconn()/closeall(). The migrated
# database service exposes mb_conn. Provide a tiny compatibility wrapper here.
_auth_connection_pool = None


class _AuthPoolCompat:
    def __init__(self, mb_conn):
        self._conn = mb_conn

    def getconn(self):
        """Return the underlying connection object for compatibility.

        Callers typically use `with pool.getconn() as conn:` or `conn = pool.getconn()`
        and then `with conn.cursor() as cursor:`. The returned connection implements
        cursor() so this is compatible with existing code.
        """
        return self._conn

    def closeall(self):
        """No-op: the migration uses a single connection managed by the service."""
        try:
            # Attempt a gentle close if underlying connection exposes close
            if hasattr(self._conn, "close"):
                self._conn.close()
        except Exception:
            pass


def initialize_auth_connection_pool() -> _AuthPoolCompat:
    """Initialize (or return) a compatibility connection pool for auth DB.

    This will initialise the migrated database service if required and return a
    pool-like object so older code paths continue to work.
    """
    global _auth_connection_pool
    if _auth_connection_pool is not None:
        return _auth_connection_pool

    service = initialize_auth_db_service()
    conn = getattr(service, "mb_conn", None)
    if conn is None:
        raise RuntimeError("Auth DB connection not available")
    _auth_connection_pool = _AuthPoolCompat(conn)
    return _auth_connection_pool


def get_auth_connection_pool() -> _AuthPoolCompat | None:
    """Return the compatibility connection pool instance (or None)."""
    return _auth_connection_pool


@contextmanager
def get_auth_db_cursor(commit: bool = False, dictionary: bool = True):
    """Yield (conn, cursor) using the migrated MariaDB connection for auth operations."""
    service = initialize_auth_db_service()
    conn = service.mb_conn
    cursor = conn.cursor(dictionary=dictionary)
    try:
        yield conn, cursor
        if commit:
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            cursor.close()
        except Exception:
            pass


def auth_execute_query(
    query: str, params: tuple = None, fetch: bool = True
) -> list | None:
    """
    Execute an authentication database query with automatic connection management.

    Args:
        query: SQL query string
        params: Query parameters
        fetch: Whether to fetch results (for SELECT queries)

    Returns:
        List of results if fetch=True and it's a SELECT query, None otherwise
    """
    # Default to commit True for data-changing ops to preserve prior behavior
    commit = not query.strip().upper().startswith("SELECT")
    with get_auth_db_cursor(commit=commit) as (conn, cursor):
        cursor.execute(query, params or ())
        if fetch and query.strip().upper().startswith("SELECT"):
            return cursor.fetchall()
        # For inserts, attempt to return lastrowid for compatibility
        if commit and hasattr(cursor, "lastrowid"):
            return [{"lastrowid": cursor.lastrowid}]
        return None


def auth_execute_query_single(
    query: str, params: tuple = None, commit: bool = False
) -> dict | None:
    """
    Execute an authentication query and return a single result row.

    Args:
        query: SQL query string
        params: Query parameters
        commit: Whether to commit the transaction (important for INSERT/UPDATE/DELETE)

    Returns:
        Single result row as dict, or None if no results
    """
    with get_auth_db_cursor(commit=commit) as (conn, cursor):
        cursor.execute(query, params or ())
        # If query was an INSERT and commit requested, try to return lastrowid
        if commit and ("INSERT" in query.strip().upper()):
            last = getattr(cursor, "lastrowid", None)
            if last:
                return {"lastrowid": last}
        result = cursor.fetchone()
        return dict(result) if result else None


# JWT Configuration
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
)
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(
    os.environ.get("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")
)


class UserRole(str, Enum):
    """User role enumeration"""

    ADMIN = "admin"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


class UserStatus(str, Enum):
    """User account status"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"
    DELETED = "deleted"


class User(BaseModel):
    """User model"""

    user_id: int | None = None
    email: EmailStr
    username: str
    full_name: str
    role: UserRole = UserRole.RESEARCHER
    status: UserStatus = UserStatus.PENDING
    hashed_password: str
    salt: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_login: datetime | None = None
    login_attempts: int = 0
    locked_until: datetime | None = None


class UserCreate(BaseModel):
    """User creation model"""

    email: EmailStr
    username: str
    full_name: str
    password: str
    role: UserRole = UserRole.RESEARCHER


class UserLogin(BaseModel):
    """User login model"""

    username_or_email: str
    password: str


class Token(BaseModel):
    """Token model"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class TokenData(BaseModel):
    """Token data model"""

    user_id: int
    username: str
    email: str
    role: UserRole
    exp: datetime | None = None


class PasswordResetRequest(BaseModel):
    """Password reset request model"""

    email: EmailStr


class PasswordReset(BaseModel):
    """Password reset model"""

    token: str
    new_password: str


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash a password with salt"""
    if salt is None:
        salt = secrets.token_hex(16)

    # Use PBKDF2 with SHA-256
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000,  # 100,000 iterations
    ).hex()

    return hashed, salt


def verify_password(password: str, hashed_password: str, salt: str) -> bool:
    """Verify a password against its hash"""
    computed_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(computed_hash, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def verify_token(token: str, token_type: str = "access") -> TokenData | None:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != token_type:
            return None

        user_id: int = payload.get("user_id")
        username: str = payload.get("username")
        email: str = payload.get("email")
        role: str = payload.get("role")

        if user_id is None or username is None:
            return None

        return TokenData(
            user_id=user_id,
            username=username,
            email=email,
            role=UserRole(role),
            exp=datetime.fromtimestamp(payload.get("exp", 0)),
        )
    except jwt.PyJWTError:
        return None


def create_user_tables():
    """Create user authentication tables"""
    queries = [
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            username VARCHAR(100) UNIQUE NOT NULL,
            full_name VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL DEFAULT 'researcher',
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            hashed_password VARCHAR(255) NOT NULL,
            salt VARCHAR(32) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP NULL,
            login_attempts INTEGER DEFAULT 0,
            locked_until TIMESTAMP NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INTEGER,
            -- FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            refresh_token_hash VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            is_active BOOLEAN DEFAULT TRUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INTEGER,
            -- FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            token_hash VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT FALSE
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_user_sessions_refresh_token ON user_sessions(refresh_token_hash)
        """,
    ]

    for query in queries:
        auth_execute_query(query, fetch=False)


def get_user_by_username_or_email(username_or_email: str) -> dict | None:
    """Get user by username or email"""
    query = """
    SELECT user_id, email, username, full_name, role, status, hashed_password, salt,
           created_at, updated_at, last_login, login_attempts, locked_until
    FROM users
    WHERE username = %s OR email = %s
    """
    result = auth_execute_query_single(query, (username_or_email, username_or_email))
    return result


def get_user_by_id(user_id: int) -> dict | None:
    """Get user by ID"""
    query = """
    SELECT user_id, email, username, full_name, role, status, hashed_password, salt,
           created_at, updated_at, last_login, login_attempts, locked_until
    FROM users
    WHERE user_id = %s
    """
    result = auth_execute_query_single(query, (user_id,))
    return result


def create_user(user_data: UserCreate) -> int | None:
    """Create a new user"""
    hashed_password, salt = hash_password(user_data.password)

    query = """
    INSERT INTO users (email, username, full_name, role, status, hashed_password, salt)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    res = auth_execute_query_single(
        query,
        (
            user_data.email,
            user_data.username,
            user_data.full_name,
            user_data.role.value,
            UserStatus.PENDING.value,
            hashed_password,
            salt,
        ),
        commit=True,
    )

    if res and res.get("lastrowid"):
        return res.get("lastrowid")
    return None


def update_user_login(user_id: int):
    """Update user's last login time"""
    query = """
    UPDATE users
    SET last_login = CURRENT_TIMESTAMP,
        login_attempts = 0,
        locked_until = NULL,
        updated_at = CURRENT_TIMESTAMP
    WHERE user_id = %s
    """
    auth_execute_query(query, (user_id,), fetch=False)


def increment_login_attempts(user_id: int):
    """Increment login attempts and potentially lock account"""
    query = """
    UPDATE users
    SET login_attempts = login_attempts + 1,
        locked_until = CASE
            WHEN login_attempts >= 4 THEN CURRENT_TIMESTAMP + INTERVAL '30 minutes'
            ELSE NULL
        END,
        updated_at = CURRENT_TIMESTAMP
    WHERE user_id = %s
    """
    auth_execute_query(query, (user_id,), fetch=False)


def reset_login_attempts(user_id: int):
    """Reset login attempts"""
    query = """
    UPDATE users
    SET login_attempts = 0,
        locked_until = NULL,
        updated_at = CURRENT_TIMESTAMP
    WHERE user_id = %s
    """
    auth_execute_query(query, (user_id,), fetch=False)


def activate_user(user_id: int) -> bool:
    """Activate a user account"""
    query = """
    UPDATE users
    SET status = %s, updated_at = CURRENT_TIMESTAMP
    WHERE user_id = %s
    """
    auth_execute_query(query, (UserStatus.ACTIVE.value, user_id), fetch=False)
    return True


def deactivate_user(user_id: int) -> bool:
    """Deactivate a user account"""
    query = """
    UPDATE users
    SET status = %s, updated_at = CURRENT_TIMESTAMP
    WHERE user_id = %s
    """
    auth_execute_query(query, (UserStatus.INACTIVE.value, user_id), fetch=False)
    return True


def store_refresh_token(user_id: int, refresh_token: str) -> bool:
    """Store refresh token in database"""
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    expires_at = datetime.now(UTC) + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    query = """
    INSERT INTO user_sessions (user_id, refresh_token_hash, expires_at)
    VALUES (%s, %s, %s)
    """
    try:
        auth_execute_query(query, (user_id, token_hash, expires_at), fetch=False)
        return True
    except Exception:
        return False


def validate_refresh_token(refresh_token: str) -> int | None:
    """Validate refresh token and return user_id if valid"""
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

    query = """
    SELECT user_id FROM user_sessions
    WHERE refresh_token_hash = %s AND is_active = TRUE AND expires_at > CURRENT_TIMESTAMP
    """
    result = auth_execute_query_single(query, (token_hash,))
    return result.get("user_id") if result else None


def revoke_refresh_token(refresh_token: str) -> bool:
    """Revoke a refresh token"""
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

    query = """
    UPDATE user_sessions
    SET is_active = FALSE
    WHERE refresh_token_hash = %s
    """
    auth_execute_query(query, (token_hash,), fetch=False)
    return True


def revoke_all_user_sessions(user_id: int) -> bool:
    """Revoke all refresh tokens for a user"""
    query = """
    UPDATE user_sessions
    SET is_active = FALSE
    WHERE user_id = %s
    """
    auth_execute_query(query, (user_id,), fetch=False)
    return True


def create_password_reset_token(user_id: int) -> str:
    """Create a password reset token"""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = datetime.now(UTC) + timedelta(hours=1)

    query = """
    INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
    VALUES (%s, %s, %s)
    """
    auth_execute_query(query, (user_id, token_hash, expires_at), fetch=False)
    return token


def validate_password_reset_token(token: str) -> int | None:
    """Validate password reset token and return user_id if valid"""
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    query = """
    SELECT user_id FROM password_reset_tokens
    WHERE token_hash = %s AND used = FALSE AND expires_at > CURRENT_TIMESTAMP
    """
    result = auth_execute_query_single(query, (token_hash,))
    return result.get("user_id") if result else None


def mark_password_reset_token_used(token: str) -> bool:
    """Mark password reset token as used"""
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    query = """
    UPDATE password_reset_tokens
    SET used = TRUE
    WHERE token_hash = %s
    """
    auth_execute_query(query, (token_hash,), fetch=False)
    return True


def update_user_password(user_id: int, new_password: str) -> bool:
    """Update user password"""
    hashed_password, salt = hash_password(new_password)

    query = """
    UPDATE users
    SET hashed_password = %s, salt = %s, updated_at = CURRENT_TIMESTAMP
    WHERE user_id = %s
    """
    auth_execute_query(query, (hashed_password, salt, user_id), fetch=False)
    return True


def get_all_users(limit: int = 100, offset: int = 0) -> list[dict]:
    """Get all users with pagination"""
    query = """
    SELECT user_id, email, username, full_name, role, status, created_at, updated_at, last_login
    FROM users
    ORDER BY created_at DESC
    LIMIT %s OFFSET %s
    """
    results = auth_execute_query(query, (limit, offset))
    return [dict(row) for row in results] if results else []


def get_user_count() -> int:
    """Get total user count"""
    query = "SELECT COUNT(*) as count FROM users"
    result = auth_execute_query_single(query)
    return result.get("count", 0) if result else 0


def update_user_anonymized(
    user_id: int, anonymized_email: str, anonymized_username: str
) -> bool:
    """Anonymize user data for GDPR compliance (Right to be Forgotten)"""
    query = """
    UPDATE users
    SET email = %s,
        username = %s,
        full_name = 'Deleted User',
        hashed_password = NULL,
        salt = NULL,
        status = %s,
        updated_at = CURRENT_TIMESTAMP
    WHERE user_id = %s
    """
    auth_execute_query(
        query,
        (anonymized_email, anonymized_username, UserStatus.DELETED.value, user_id),
        fetch=False,
    )
    return True
