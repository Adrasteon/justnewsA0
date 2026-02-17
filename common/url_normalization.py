"""Utilities for canonicalising article URLs and computing stable hashes.

Stage B requires deterministic URL normalisation and hashing so that the
ingestion pipeline can deduplicate articles aggressively across multiple
sources.  The helpers in this module centralise those rules so both the
crawler and ingestion code paths rely on a single implementation.

Normalisation rules (``strict`` mode by default):
* Prefer canonical URL when supplied
* Lowercase scheme and hostname
* Remove default ports (80/443)
* Strip common tracking query parameters (utm_*, fbclid, gclid, etc.)
* Drop fragments
* Collapse duplicate slashes and remove trailing slash (except root)
* Preserve query parameter order for remaining keys (stable input is
  important for hashing)

Hashing is configurable via the ``ARTICLE_URL_HASH_ALGO`` environment
variable and falls back to ``sha256``.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterable
from urllib.parse import ParseResult, parse_qsl, urlencode, urlparse, urlunparse

# Tracking parameters routinely appended by publishers or email campaigns.
_TRACKING_PARAM_PREFIXES = ("utm_", "spm", "icid")
_TRACKING_PARAM_KEYS = {
    "fbclid",
    "gclid",
    "mc_eid",
    "mc_cid",
    "mkt_tok",
    "cmpid",
}


def _strip_tracking_params(pairs: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    cleaned: list[tuple[str, str]] = []
    for key, value in pairs:
        lower = key.lower()
        if lower.startswith(_TRACKING_PARAM_PREFIXES):
            continue
        if lower in _TRACKING_PARAM_KEYS:
            continue
        cleaned.append((key, value))
    return cleaned


def _normalise_netloc(parsed: ParseResult) -> str:
    host = (parsed.hostname or "").lower()
    port: int | None = parsed.port

    if not host:
        return ""

    if (parsed.scheme == "http" and port == 80) or (
        parsed.scheme == "https" and port == 443
    ):
        port = None

    return host if port is None else f"{host}:{port}"


def _collapse_slashes(path: str) -> str:
    # Avoid turning `//` at start of network-path references into `/`
    if not path or path == "/":
        return path
    collapsed = re.sub(r"/{2,}", "/", path)
    return collapsed


def normalize_article_url(
    url: str, canonical_url: str | None = None, *, mode: str | None = None
) -> str:
    """Return a normalised URL suitable for hashing and dedupe checks.

    Args:
        url: Original URL provided by the crawler.
        canonical_url: Canonical URL extracted from metadata (if any).
        mode: Optional override for normalisation strength. Supported values:
            - ``strict`` (default): applies all heuristics.
            - ``lenient``: keeps query string intact but still lowercases host.
            - ``none``: returns canonical/url untouched (useful for debugging).
    """

    mode = (mode or os.environ.get("ARTICLE_URL_NORMALIZATION", "strict")).lower()

    candidate = canonical_url or url
    if not candidate:
        return ""

    if mode == "none":
        return candidate

    parsed = urlparse(candidate)
    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    netloc = _normalise_netloc(parsed)

    path = _collapse_slashes(parsed.path or "/")
    if path != "/":
        path = path.rstrip("/") or "/"

    params = parsed.params

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if mode == "strict":
        query_pairs = _strip_tracking_params(query_pairs)

    query = urlencode(query_pairs, doseq=True)

    fragment = ""  # Always drop fragments for dedupe purposes

    rebuilt = urlunparse((scheme, netloc, path, params, query, fragment))
    return rebuilt


def hash_article_url(url: str, *, algorithm: str | None = None) -> str:
    """Compute a stable hash for an article URL.

    Args:
        url: URL to hash. Call :func:`normalize_article_url` first.
        algorithm: Optional hashlib algorithm name; defaults to environment or sha256.
    """

    if not url:
        return ""

    algo = (algorithm or os.environ.get("ARTICLE_URL_HASH_ALGO", "sha256")).lower()
    try:
        digest = hashlib.new(algo)
    except (
        ValueError
    ) as exc:  # pragma: no cover - invalid algorithm configured by operator
        raise ValueError(f"Unsupported hash algorithm '{algo}'") from exc

    digest.update(url.encode("utf-8", errors="ignore"))
    return digest.hexdigest()
