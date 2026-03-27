#!/usr/bin/env python3
"""
Chroma Bootstrap Utility
------------------------
Small operator helper to bootstrap Chroma server tenant/collection in a best-effort, idempotent manner.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/chroma_bootstrap.py --host HOST --port PORT --tenant TENANT --collection COLLECTION

This script attempts to (in order):
  1. Validate the host/port is a Chroma instance (and not the MCP Bus)
  2. Create a tenant if required
  3. Ensure the named collection exists; create it if it doesn't

For production deployments, this script should be run by an operator with adequate permissions
to manage Chroma tenants/collections. This script performs best-effort HTTP calls and logs important
diagnostics on failures.
"""

from __future__ import annotations

import argparse
import os
import sys
from pprint import pprint

from database.utils.chromadb_utils import (
    create_tenant,
    discover_chroma_endpoints,
    ensure_collection_exists_using_http,
    get_root_info,
    validate_chroma_is_canonical,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("CHROMADB_HOST", "localhost"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("CHROMADB_PORT", 3307))
    )
    parser.add_argument(
        "--tenant", default=os.environ.get("CHROMADB_TENANT", "default_tenant")
    )
    parser.add_argument(
        "--collection", default=os.environ.get("CHROMADB_COLLECTION", "articles")
    )
    parser.add_argument(
        "--require-canonical",
        action="store_true",
        help="Enforce canonical host/port via env CHROMADB_CANONICAL_HOST/PORT (fatal if mismatch)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    host = args.host
    port = args.port
    tenant = args.tenant
    collection = args.collection

    print(
        f"🔧 Bootstrapping ChromaDB at {host}:{port} (tenant={tenant}, collection={collection})"
    )

    print("Root info:")
    pprint(get_root_info(host, port))

    print("\nEndpoints discovered:")
    endpoints = discover_chroma_endpoints(host, port)
    pprint(endpoints)

    if args.require_canonical:
        canonical_host = os.environ.get("CHROMADB_CANONICAL_HOST")
        canonical_port = os.environ.get("CHROMADB_CANONICAL_PORT")
        if not canonical_host or not canonical_port:
            print(
                "ERROR: CHROMADB_CANONICAL_HOST/PORT must be set when --require-canonical is used"
            )
            sys.exit(2)
        try:
            validate_chroma_is_canonical(
                host, port, canonical_host, int(canonical_port), raise_on_fail=True
            )
            print("OK: canonical host/port validated")
        except Exception as e:
            print(f"ERROR: canonical validation failed: {e}")
            sys.exit(2)

    # Attempt to create tenant (best-effort)
    created_tenant = create_tenant(host, port, tenant=tenant)
    print("\nTenant create OK?", created_tenant)

    # Attempt to ensure collection exists
    created_collection = ensure_collection_exists_using_http(host, port, collection)
    print("Collection create OK?", created_collection)

    # Success when at least collection exists or create is not necessary
    if not created_collection:
        print(
            "\nWARNING: Could not create or confirm collection existence — check Chroma server logs."
        )
        sys.exit(1)

    print("\nBootstrap completed; collection available.")
    sys.exit(0)


if __name__ == "__main__":
    main()
