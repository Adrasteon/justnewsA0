#!/usr/bin/env python3
"""Simple metrics recorder for canary tests.

Records lightweight counters into `output/metrics/canary_metrics.json` so
tests can validate that each stage emitted at least one successful event.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

OUT = Path.cwd() / "output" / "metrics"
OUT.mkdir(parents=True, exist_ok=True)
FILE = OUT / "canary_metrics.json"


def read_metrics() -> dict[str, int]:
    if not FILE.exists():
        return {}
    return json.loads(FILE.read_text(encoding="utf-8"))


def incr(metric: str, amount: int = 1) -> None:
    data = Counter(read_metrics())
    data[metric] += amount
    FILE.write_text(json.dumps(dict(data), indent=2), encoding="utf-8")


def reset() -> None:
    FILE.write_text(json.dumps({}, indent=2), encoding="utf-8")
