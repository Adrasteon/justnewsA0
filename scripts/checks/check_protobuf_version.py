#!/usr/bin/env python3
"""Check installed protobuf version meets minimum requirement.

Usage:
  python scripts/check_protobuf_version.py

This tool examines the installed `protobuf` package version and exits with code 1 if it is older than the minimum required version.
"""

from __future__ import annotations

import sys

try:
    from importlib import metadata as importlib_metadata
except ImportError:  # pragma: no cover - older Python fallback
    import importlib_metadata  # type: ignore

MIN_PROTOBUF = (4, 24, 0)


def parse_version(ver: str):
    parts = [int(x) for x in ver.split(".") if x.isdigit()]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def main():
    try:
        import google.protobuf as pb  # type: ignore
    except Exception as exc:
        pb = None
        import_error = exc
    else:
        import_error = None

    v = None
    if pb is not None:
        v = getattr(pb, "__version__", None) or getattr(pb, "version", None)

    if not v:
        try:
            v = importlib_metadata.version("protobuf")
        except importlib_metadata.PackageNotFoundError:
            if import_error is not None:
                print(
                    "ERROR: protobuf not installed or could not be imported:",
                    import_error,
                )
            else:
                print(
                    "ERROR: protobuf package metadata not found; ensure protobuf >= 4.24.0 is installed in the active environment."
                )
            sys.exit(1)

    ver_tuple = parse_version(v)
    print("protobuf detected version:", v)
    if ver_tuple < MIN_PROTOBUF:
        print(
            f"ERROR: protobuf version older than recommended: >={MIN_PROTOBUF[0]}.{MIN_PROTOBUF[1]}.{MIN_PROTOBUF[2]}"
        )
        print("Please update conda / pip environment to upgrade to protobuf >= 4.24.0")
        sys.exit(1)
    print("protobuf meets minimum version requirement.")


if __name__ == "__main__":
    main()
