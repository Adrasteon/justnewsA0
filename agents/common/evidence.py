"""Evidence snapshot helper for paywalled pages.

This module provides a simple file-based evidence snapshot and a helper to
enqueue a human-review request by calling the MCP Bus /call endpoint for the
`chief_editor` agent. It is intentionally small and dependency-free.
"""

import json
import os
from datetime import UTC, datetime

import requests

EVIDENCE_DIR = os.environ.get("EVIDENCE_DIR", "./evidence")
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")


def snapshot_paywalled_page(url: str, html: str, metadata: dict) -> str:
    """Save raw HTML and a JSON manifest. Return the manifest path.

    Manifest contains: url, html_file, metadata, captured_at
    """
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    html_filename = f"evidence_{now}.html"
    manifest_filename = f"evidence_{now}.json"
    html_path = os.path.join(EVIDENCE_DIR, html_filename)
    manifest_path = os.path.join(EVIDENCE_DIR, manifest_filename)

    # Save HTML
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html or "")

    manifest = {
        "url": url,
        "html_file": html_filename,
        "metadata": metadata,
        "captured_at": datetime.now(UTC).isoformat(),
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    return manifest_path


def enqueue_human_review(
    evidence_manifest_path: str, reviewer: str = "chief_editor"
) -> dict:
    """Call the MCP Bus /call endpoint to request human review from chief_editor.

    The payload uses a dedicated tool 'review_evidence' and passes the manifest path.
    """
    payload = {
        "agent": reviewer,
        "tool": "review_evidence",
        "args": [],
        "kwargs": {
            "evidence_manifest": evidence_manifest_path,
            "reason": "paywalled_snapshot",
        },
    }
    try:
        resp = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=(2, 10))
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}
