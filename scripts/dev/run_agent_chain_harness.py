#!/usr/bin/env python3
"""Run the editorial agent-chain harness against normalized articles stored in MariaDB."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agents.common.editorial_harness_runner import AgentChainRunner, ArtifactWriter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of articles to evaluate (default: 5)",
    )
    parser.add_argument(
        "--article-id",
        action="append",
        dest="article_ids",
        help="Specific article ID to evaluate (repeat for multiple)",
    )
    parser.add_argument(
        "--no-artifacts",
        action="store_true",
        help="Skip writing JSON artifacts under output/agent_chain_runs",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Override the artifact directory (default: output/agent_chain_runs)",
    )
    parser.add_argument(
        "--publish-on-accept",
        action="store_true",
        help="When set, accepted harness outputs (high acceptance score) will be published to the lightweight publisher DB",
    )
    parser.add_argument(
        "--publish-token",
        type=str,
        default=None,
        help="Approval token required to allow automated publishing (must match deploy/publish.token or PUBLISH_APPROVAL_TOKEN env var)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    writer = None if args.no_artifacts else ArtifactWriter(args.artifact_dir)
    runner = AgentChainRunner(
        artifact_writer=writer,
        write_artifacts=not args.no_artifacts,
        publish_on_accept=args.publish_on_accept,
        publish_token=args.publish_token,
    )
    results = runner.run(limit=args.limit, article_ids=args.article_ids)

    summary = {
        "evaluated": len(results),
        "accepted": sum(not r.needs_followup for r in results),
        "needs_followup": sum(r.needs_followup for r in results),
        "avg_acceptance": round(
            sum(r.acceptance_score for r in results) / len(results), 3
        )
        if results
        else 0.0,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
