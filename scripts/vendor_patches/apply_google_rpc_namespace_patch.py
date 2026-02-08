#!/usr/bin/env python3
"""Vendor patch to remove pkg_resources dependency from google.rpc namespace."""

from __future__ import annotations

import argparse
import importlib.util
import sys
import textwrap
from pathlib import Path

PATCH_SNIPPET = textwrap.dedent(
    """
import pkgutil


# Use pkgutil-based namespace package handling to avoid the deprecated
# pkg_resources API. This keeps compatibility with downstream modules that rely
# on ``google.rpc`` being a namespace without pulling in setuptools helpers.
__path__ = pkgutil.extend_path(__path__, __name__)
"""
).strip()

ORIGINAL_SNIPPET = textwrap.dedent(
    """
try:
    import pkg_resources

    pkg_resources.declare_namespace(__name__)
except ImportError:
    import pkgutil

    __path__ = pkgutil.extend_path(__path__, __name__)
"""
).strip()


def locate_module() -> Path:
    spec = importlib.util.find_spec("google.rpc")
    if spec is None or spec.origin is None:
        raise RuntimeError("Could not locate google.rpc module")
    return Path(spec.origin)


def apply_patch(module_path: Path, dry_run: bool = False) -> bool:
    original = module_path.read_text(encoding="utf-8")
    if "pkg_resources.declare_namespace" not in original:
        return False

    if ORIGINAL_SNIPPET not in original:
        raise RuntimeError(
            f"google.rpc module at {module_path} does not match expected layout; aborting patch"
        )

    if dry_run:
        return True

    updated = original.replace(ORIGINAL_SNIPPET, PATCH_SNIPPET)
    module_path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report whether the patch would be applied",
    )
    args = parser.parse_args()

    module_path = locate_module()
    try:
        changed = apply_patch(module_path, dry_run=args.dry_run)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    action = "would patch" if args.dry_run else "patched"
    if changed:
        print(f"OK: {action} {module_path}")
    else:
        print(f"OK: no changes needed for {module_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
