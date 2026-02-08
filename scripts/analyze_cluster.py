#!/usr/bin/env python3
"""
Script to analyze a cluster of articles using ClusterFetcher + Analyst.

Usage:
  python scripts/analyze_cluster.py --cluster-id <cluster_id> [--verbose]
"""

import argparse
import json
import sys
from pathlib import Path

# Make the project root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.analyst import tools as analyst_tools
from common.observability import get_logger

logger = get_logger(__name__)


def analyze_cluster(cluster_id: str, verbose: bool = False):
    report = analyst_tools.generate_analysis_report([], cluster_id=cluster_id)
    if "error" in report:
        print(f"Error: {report['error']}")
        return report

    if verbose:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"Cluster: {report.get('cluster_id', 'unknown')} | Articles: {report.get('articles_count', 0)}"
        )
        sfc_summary = report.get("cluster_fact_check_summary")
        if sfc_summary:
            print(
                f"Fact-check Verified: {sfc_summary.get('percent_verified', 0.0):.1f}%"
            )
        else:
            print("Fact-check summary: none")

    return report


def main():
    parser = argparse.ArgumentParser(description="Analyze a cluster with Analyst")
    parser.add_argument(
        "--cluster-id", required=True, help="Cluster identifier (transparency cluster)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print detailed JSON report"
    )
    args = parser.parse_args()

    analyze_cluster(args.cluster_id, args.verbose)


if __name__ == "__main__":
    main()
