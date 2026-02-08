"""Development/Test Database Environment Fallback Helper.

WARNING: This module provides a TEMPORARY convenience layer that injects
hard-coded development database credentials when no secure configuration is
present. It MUST be removed or replaced with a proper secret / environment
management system before production deployment or merging to the main branch.

Behavior:
  * Sets a consistent set of database environment variables ONLY if they are
    currently unset in the process environment.
  * Provides multiple naming conventions used by different legacy components
    (DB_*, JUSTNEWS_DB_*) to avoid KeyErrors while refactoring.
  * Constructs a DATABASE_URL if one is not already defined.
  * Emits explicit WARNING level log entries enumerating which variables were
    injected. No action is taken if everything is already configured.
  * Can be disabled via the JUSTNEWS_DISABLE_TEST_DB_FALLBACK=1 environment var.

Default Credentials (development only):
  user: justnews
  password: justnews_password
  host: localhost
  port: 3306
  database: justnews

Usage:
  from common.dev_db_fallback import apply_test_db_env_fallback
  apply_test_db_env_fallback(logger)

Return:
  List[str]: Names of environment variables that were applied/created.

Security Notes:
  - Do NOT rely on this in CI that mimics production.
  - Ensure secrets rotation plan removes any accidental persistence.
  - Search for "apply_test_db_env_fallback" to locate usages during cleanup.
"""

from __future__ import annotations

import logging
import os

# Constants
_DISABLE_FLAG = "JUSTNEWS_DISABLE_TEST_DB_FALLBACK"

# Canonical development defaults (ONLY applied if missing)
_DEV_DEFAULTS = {
    "DB_HOST": "localhost",
    "DB_PORT": "3306",
    "DB_NAME": "justnews",
    "DB_USER": "justnews",
    "DB_PASSWORD": "justnews_password",
}

# Legacy / alternate variable name mapping – values resolved from _DEV_DEFAULTS
_LEGACY_MIRRORS = {
    "MARIADB_HOST": "DB_HOST",
    "MARIADB_DB": "DB_NAME",
    "MARIADB_USER": "DB_USER",
    "MARIADB_PASSWORD": "DB_PASSWORD",
    "JUSTNEWS_DB_HOST": "DB_HOST",
    "JUSTNEWS_DB_PORT": "DB_PORT",
    "JUSTNEWS_DB_NAME": "DB_NAME",
    "JUSTNEWS_DB_USER": "DB_USER",
    "JUSTNEWS_DB_PASSWORD": "DB_PASSWORD",
}


def _build_database_url(env: dict) -> str:
    """Construct a DATABASE_URL from component env values.

    Args:
        env: Environment dictionary (typically os.environ).

    Returns:
        A MariaDB connection URL.
    """
    user = env.get("DB_USER", _DEV_DEFAULTS["DB_USER"])  # pragma: no cover
    password = env.get("DB_PASSWORD", _DEV_DEFAULTS["DB_PASSWORD"])  # pragma: no cover
    host = env.get("DB_HOST", _DEV_DEFAULTS["DB_HOST"])  # pragma: no cover
    port = env.get("DB_PORT", _DEV_DEFAULTS["DB_PORT"])  # pragma: no cover
    name = env.get("DB_NAME", _DEV_DEFAULTS["DB_NAME"])  # pragma: no cover
    # Construct a MariaDB-compatible URL for local testing convenience.
    # Note: consumers of DATABASE_URL should support mysql:// or mysql+pymysql://
    return f"mysql://{user}:{password}@{host}:{port}/{name}"


def apply_test_db_env_fallback(logger: logging.Logger | None = None) -> list[str]:
    """Apply development DB environment defaults if not already configured.

    This function performs no destructive overwrites—only missing variables are
    populated. A warning banner is logged once if any values are applied.

    Args:
        logger: Optional logger instance. If omitted, a basic fallback logger is
            created (kept minimal to avoid side-effects).

    Returns:
        List of variable names that were set by this helper. Empty list if
        nothing was changed or the fallback was disabled.
    """
    if os.environ.get(_DISABLE_FLAG):  # Explicit opt-out
        return []

    applied: list[str] = []

    # Step 1: Primary DB_* defaults
    for k, v in _DEV_DEFAULTS.items():
        if not os.environ.get(k):  # only set if absent
            os.environ[k] = v  # pragma: no cover (env side-effect)
            applied.append(k)

    # Step 2: Legacy mirrors referencing primary keys
    for mirror, source in _LEGACY_MIRRORS.items():
        if not os.environ.get(mirror) and os.environ.get(source):
            os.environ[mirror] = os.environ[source]  # pragma: no cover
            applied.append(mirror)

    # Step 3: DATABASE_URL synthesis
    if not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = _build_database_url(os.environ)
        applied.append("DATABASE_URL")

    if applied:
        _logger = logger or logging.getLogger("dev_db_fallback")
        _logger.warning(
            "⚠️ USING TEMP HARD-CODED TEST DB VARS (REMOVE BEFORE PROD): %s",
            ",".join(applied),
        )
        _logger.warning(
            "This is a temporary unblocker for the crawler; replace with secure env management."
        )

    return applied


__all__ = ["apply_test_db_env_fallback"]
