"""Authentication helpers for agent integrations.

The Stage B refactor removed the original ``agents.common.auth`` module,
which several call sites and tests still import. This lightweight
compatibility layer restores the public API needed by those consumers while
keeping the logic deliberately simple.
"""

from __future__ import annotations

import os
from collections.abc import Iterable


def _load_allowed_keys() -> Iterable[str]:
    """Retrieve API keys from the environment.

    Keys can be provided as a comma-separated list via ``JUSTNEWS_API_KEYS``.
    The helper gracefully handles missing configuration so that tests can
    patch ``validate_api_key`` without needing to seed environment variables.
    """

    raw_keys = os.environ.get("JUSTNEWS_API_KEYS", "")
    return [key.strip() for key in raw_keys.split(",") if key.strip()]


def validate_api_key(api_key: str) -> bool:
    """Validate that ``api_key`` matches an allowed key.

    The function performs a constant-time comparison to limit timing side
    channels while maintaining backwards compatibility with the previous API.
    """

    if not api_key:
        return False

    allowed_keys = _load_allowed_keys()
    if not allowed_keys:
        return False

    import hmac

    for allowed in allowed_keys:
        if hmac.compare_digest(api_key, allowed):
            return True
    return False
