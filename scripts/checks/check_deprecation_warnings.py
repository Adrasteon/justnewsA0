#!/usr/bin/env python3
"""Check for DeprecationWarning (PyType_Spec/tp_new) triggered during imports.

This script attempts to import common third-party modules that may trigger the
old `PyType_Spec` / `tp_new` deprecation when C extensions are built against an
outdated upb API. If any such deprecation warnings are raised during import,
this script will exit with a non-zero status and print the warnings.
"""

from __future__ import annotations

import sys
import warnings

# Modules to import and check. We include the ones that commonly appear
# during test runs and are likely to import the 'google._upb' extensions.
IMPORTS_TO_CHECK = [
    "google._upb._message",
    "google.protobuf",
    "transformers",
    "sentence_transformers",
    "chromadb",
]

# The deprecation message substring we are specifically trying to catch.
DEPRECATION_SUBSTR = "PyType_Spec"  # part of the message text


def main() -> int:
    recorded = []
    for module in IMPORTS_TO_CHECK:
        with warnings.catch_warnings(record=True) as warns:
            warnings.simplefilter("always")
            try:
                __import__(module)
            except Exception:
                # Some modules may not be installed — skip them
                continue
            for w in warns:
                # Only consider DeprecationWarning type with the relevant message
                if (
                    isinstance(w.message, DeprecationWarning)
                    or w.category is DeprecationWarning
                ):
                    msg = str(w.message)
                    if DEPRECATION_SUBSTR in msg:
                        recorded.append((module, msg))

    if recorded:
        print("\nDeprecation warnings detected during imports:")
        for mod, msg in recorded:
            print(f"  - Module: {mod} raised DeprecationWarning: {msg}")
        print(
            "\nPlease ensure your environment installs protobuf wheels and any related C-extensions that are built against up-to-date ABIs; typically this means upgrading `protobuf` and rebuilding/reinstalling dependant wheels."
        )
        return 2

    print("No relevant DeprecationWarning found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
