"""Compatibility wrapper for refactored database utilities.

This module re-exports the public API from ``database.utils.database_utils``
so that legacy import paths used in the Stage B refactor continue to work.
"""

from database.utils.database_utils import *  # noqa: F401,F403
