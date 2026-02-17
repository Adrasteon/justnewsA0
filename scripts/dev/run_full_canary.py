#!/usr/bin/env python3
"""Run the full canary pipeline end-to-end and report metrics.

This is a convenience runner for local dev: it executes crawl -> normalize -> parse -> editorial -> publish
and prints a short summary of metrics found in `output/metrics/canary_metrics.json`.
"""

from __future__ import annotations

from scripts.dev.canary_metrics import read_metrics, reset
from scripts.dev.crawl_canary import main as crawl_main
from scripts.dev.editorial_canary import main as editorial_main
from scripts.dev.normalize_canary import main as normalize_main
from scripts.dev.parse_canary import main as parse_main
from scripts.dev.publish_canary import main as publish_main


def main():
    reset()
    print(
        "Starting canary full-run: crawl -> normalize -> parse -> editorial -> publish"
    )
    c = crawl_main()
    print(f"Crawl results: {len(c)} items")
    n = normalize_main()
    print(f"Normalized items: {len(n)}")
    p = parse_main()
    print(f"Parsed items: {len(p)}")
    e = editorial_main()
    print(f"Drafts created: {len(e)}")
    pub = publish_main()
    print(f"Published items: {len(pub)}")

    metrics = read_metrics()
    print("Metrics summary:")
    for k, v in sorted(metrics.items()):
        print(f"  {k}: {v}")

    return metrics


if __name__ == "__main__":
    main()
