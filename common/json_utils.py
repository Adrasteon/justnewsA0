"""Utility helpers for producing JSON-serialisable structures.

The crawler stack frequently has to deal with third-party libraries that
return complex Python objects (for example ``lxml`` elements or datetime
instances).  Downstream services such as the memory agent expect plain JSON
payloads, so ``make_json_safe`` normalises arbitrarily nested objects into a
format that ``json.dumps`` can consume without raising errors.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

try:  # Optional dependency; ``lxml`` is not always installed.
    from lxml import etree as lxml_etree  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - dependency missing in some deployments
    lxml_etree = None  # type: ignore[assignment]


def make_json_safe(value: Any, depth: int = 32) -> Any:
    """Recursively convert ``value`` into a JSON-serialisable structure.

    The helper keeps the data layout intact (dicts remain dicts, sequences
    remain lists) but stringifies objects that JSON cannot encode.  A depth cap
    prevents runaway recursion on pathological inputs.
    """

    # `depth` is interpreted as the remaining allowed recursion depth.
    # Use a visited set to detect recursive structures and avoid infinite recursion.
    def _inner(val: Any, remaining: int, visited: set[int]) -> Any:
        if remaining <= 0:
            return str(val)

        # Detect reference cycles
        try:
            vid = id(val)
        except Exception:
            vid = None
        if vid is not None:
            if vid in visited:
                return str(val)
            # Only track mutable containers
            if isinstance(val, (Mapping, Sequence, set)):
                visited.add(vid)

        # Base simple types
        if val is None or isinstance(val, (str, int, float, bool)):
            return val

        if isinstance(val, bytes):
            return val.decode("utf-8", errors="ignore")

        if isinstance(val, (datetime, date)):
            return val.isoformat()

        if isinstance(val, Mapping):
            # If the mapping directly contains a reference to itself, return
            # a string to avoid producing nested self-referential dicts.
            try:
                if any(v is val for v in val.values()) or any(
                    k is val for k in val.keys()
                ):
                    return str(val)
            except Exception:
                pass
            return {
                str(_inner(key, remaining - 1, visited)): _inner(
                    val2, remaining - 1, visited
                )
                for key, val2 in val.items()
            }

        if isinstance(val, Sequence) and not isinstance(val, (str, bytes, bytearray)):
            try:
                if any(item is val for item in val):
                    return str(val)
            except Exception:
                pass
            return [_inner(item, remaining - 1, visited) for item in val]

        if isinstance(val, set):
            return [_inner(item, remaining - 1, visited) for item in val]

        if hasattr(val, "tag") and hasattr(val, "attrib"):
            # If lxml is available, use a proper serialization; otherwise, present a
            # compact string containing the tag and attributes for readability.
            if lxml_etree is not None:
                try:
                    return lxml_etree.tostring(val, encoding="unicode")
                except Exception:  # pragma: no cover - fallback makes best effort
                    return str(val)
            else:
                try:
                    return f"<{getattr(val, 'tag', 'element')} {getattr(val, 'attrib', {})}>"
                except Exception:
                    return str(val)

        return str(val)

    return _inner(value, depth, set())
