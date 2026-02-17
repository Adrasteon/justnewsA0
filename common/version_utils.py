"""
JustNews Version Utilities
Centralized version management for all agents and components
"""

import os
import sys
from typing import Any

# Add project root to path for imports
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from justnews import VERSION_INFO, __version__
except ImportError:
    # Fallback for when justnews package is not available
    __version__ = "0.8.0"
    VERSION_INFO = {
        "version": __version__,
        "status": "beta",
        "release_date": "2025-09-25",
        "description": "Beta release candidate with unified startup system and enterprise GPU orchestration",
    }


def get_version() -> str:
    """Get the current JustNews version"""
    return __version__


def get_version_info() -> dict[str, Any]:
    """Get detailed version information"""
    return VERSION_INFO.copy()


def get_agent_version_info(agent_name: str = None) -> dict[str, Any]:
    """Get version info formatted for agent API responses"""
    info = get_version_info()
    if agent_name:
        info["agent"] = agent_name
    return info


# Convenience constants for backward compatibility
VERSION = __version__
STATUS = VERSION_INFO["status"]
RELEASE_DATE = VERSION_INFO["release_date"]
DESCRIPTION = VERSION_INFO["description"]
