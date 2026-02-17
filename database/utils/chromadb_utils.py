"""
ChromaDB Utility Helpers
Provides health checks, endpoint discovery and optional auto-provisioning helpers
"""

from __future__ import annotations

from typing import Any

import requests

from common.observability import get_logger

logger = get_logger(__name__)


def _base_url(host: str, port: int) -> str:
    if host.startswith("http"):
        return f"{host}:{port}" if ":" not in host.split("//")[-1] else host
    return f"http://{host}:{port}"


COMMON_ENDPOINTS = [
    "/",
    "/health",
    "/api/health",
    "/v1/health",
    "/api/v1/health",
    "/collections",
    "/api/collections",
    "/v1/collections",
    "/api/v1/collections",
    "/api/v2/auth/identity",
    "/api/v1/tenants",
    "/api/tenants",
    "/tenants",
]


def discover_chroma_endpoints(host: str, port: int) -> dict[str, Any]:
    base = _base_url(host, port)
    results = {}
    for e in COMMON_ENDPOINTS:
        url = base.rstrip("/") + e
        try:
            r = requests.get(url, timeout=2)
            results[e] = {"status_code": r.status_code, "reason": r.reason, "ok": r.ok}
        except requests.exceptions.RequestException as ex:
            results[e] = {"error": str(ex)}
    return results


def can_create_tenants(host: str, port: int) -> bool:
    # Basic heuristic: if /api/v1/tenants allows POST
    base = _base_url(host, port)
    urls = [
        base.rstrip("/") + "/api/v1/tenants",
        base.rstrip("/") + "/api/tenants",
        base.rstrip("/") + "/v1/tenants",
    ]
    for u in urls:
        try:
            r = requests.options(u, timeout=2)
            if r.status_code in (200, 204, 201):
                return True
        except Exception:
            pass
    return False


def create_tenant(host: str, port: int, tenant: str = "default_tenant") -> bool:
    base = _base_url(host, port)
    candidate_urls = [
        base.rstrip("/") + "/api/v1/tenants",
        base.rstrip("/") + "/api/tenants",
        base.rstrip("/") + "/v1/tenants",
    ]
    payload = {"tenant": tenant}
    for u in candidate_urls:
        try:
            r = requests.post(u, json=payload, timeout=3)
            if r.status_code in (200, 201, 204):
                logger.info(f"Created tenant {tenant} via {u}")
                return True
            else:
                logger.debug(
                    f"Create tenant {tenant} at {u} returned {r.status_code}: {r.text}"
                )
        except Exception as ex:
            logger.debug(f"Tenant create attempt at {u} failed: {ex}")
    return False


def ensure_collection_exists_using_http(
    host: str, port: int, collection_name: str = "articles"
) -> bool:
    """Attempt to create collection via direct HTTP API (best-effort)."""
    base = _base_url(host, port)
    candidate_urls = [
        base.rstrip("/") + "/api/v1/collections",
        base.rstrip("/") + "/api/collections",
        base.rstrip("/") + "/v1/collections",
    ]
    body = {"name": collection_name, "metadata": {"description": "Articles collection"}}
    for u in candidate_urls:
        try:
            r = requests.post(u, json=body, timeout=3)
            if r.status_code in (200, 201, 204):
                logger.info(f"Created collection {collection_name} via {u}")
                return True
            else:
                logger.debug(f"Create collection returned {r.status_code}: {r.text}")
        except Exception as ex:
            logger.debug(f"Attempted to create collection at {u} and failed: {ex}")
            # Provide a bit more info for operators using our scripts
            logger.debug(
                "Hint: you can run scripts/chroma_diagnose.py to discover available endpoints and scripts/chroma_bootstrap.py to attempt provisioning."
            )
    return False


def get_root_info(host: str, port: int) -> dict[str, Any]:
    base = _base_url(host, port)
    try:
        r = requests.get(base, timeout=2)
        return {"status_code": r.status_code, "text": r.text[:2048]}
    except Exception as ex:
        return {"error": str(ex)}


class ChromaCanonicalValidationError(Exception):
    """Raised when the Chroma server does not meet canonical requirements."""


def validate_chroma_is_canonical(
    host: str,
    port: int,
    canonical_host: str | None = None,
    canonical_port: int | None = None,
    raise_on_fail: bool = False,
) -> dict[str, Any]:
    """Validate that a given chroma host/port identifies a Chroma server and matches canonical.

    Returns a dict with keys: ok (bool), reason (str), root_info (dict)
    """
    root_info = get_root_info(host, port)
    root_text = str(root_info.get("text", "")) if isinstance(root_info, dict) else ""

    # If canonical values are provided, validate equality first. Fail early if mismatched.
    if canonical_host and canonical_port:
        if str(host) != str(canonical_host) or int(port) != int(canonical_port):
            result = {
                "ok": False,
                "reason": "Host/port mismatch vs canonical",
                "root_info": root_info,
            }
            if raise_on_fail:
                raise ChromaCanonicalValidationError(result["reason"])
            return result

    # Quick heuristic to detect MCP Bus vs Chroma: MCP Bus returns 'MCP Bus Agent'
    if "MCP Bus Agent" in root_text:
        result = {
            "ok": False,
            "reason": "Endpoint appears to be MCP Bus",
            "root_info": root_info,
        }
        if raise_on_fail:
            raise ChromaCanonicalValidationError(result["reason"])
        return result

    # If canonical values are provided, validate equality
    if canonical_host and canonical_port:
        if str(host) != str(canonical_host) or int(port) != int(canonical_port):
            result = {
                "ok": False,
                "reason": "Host/port mismatch vs canonical",
                "root_info": root_info,
            }
            if raise_on_fail:
                raise ChromaCanonicalValidationError(result["reason"])
            return result

    # Finally, check for a Chroma-friendly endpoint (e.g., /api/v2/auth/identity or /health) via discovery
    endpoints = discover_chroma_endpoints(host, port)
    # If at least one known path looks OK, consider this a chroma server
    for _path, info in endpoints.items():
        if isinstance(info, dict) and info.get("ok"):
            return {
                "ok": True,
                "reason": "Canonical Chroma detected",
                "root_info": root_info,
            }

    result = {
        "ok": False,
        "reason": "No Chroma endpoints discovered",
        "root_info": root_info,
    }
    if raise_on_fail:
        raise ChromaCanonicalValidationError(result["reason"])
    return result
