"""Deprecated staging bus placeholder.

The HITL service now integrates directly with the MCP Bus, so this module
remains only to avoid breaking imports for any downstream experiments that may
still reference it. All new code should import tooling from the MCP bus client
helpers inside `agents.hitl_service.app` instead.
"""
