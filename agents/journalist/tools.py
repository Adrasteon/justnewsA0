"""
Helper utilities for the Journalist agent.

Keep helpers small — heavy lifting is done by the crawler bridge and shared
common utilities.
"""

from __future__ import annotations


def health_check() -> dict[str, object]:
    return {"status": "ok", "component": "journalist"}
