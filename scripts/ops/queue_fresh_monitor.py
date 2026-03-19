#!/usr/bin/env python3
"""Monitor workflow queue counts using a fresh DB connection per sample.

This avoids stale transactional snapshots when reading MariaDB repeatedly.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone

import mysql.connector


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fresh-connection workflow queue monitor")
    parser.add_argument("--interval-seconds", type=float, default=10.0, help="Polling interval")
    parser.add_argument("--samples", type=int, default=0, help="Number of samples (0 = run forever)")
    parser.add_argument(
        "--out-jsonl",
        default="logs/operations/queue_fresh_monitor/queue_samples.jsonl",
        help="Output JSONL file",
    )
    return parser.parse_args()


def db_config() -> dict[str, object]:
    return {
        "host": os.environ.get("MARIADB_HOST", "mariadb"),
        "port": int(os.environ.get("MARIADB_PORT", "3306")),
        "user": os.environ.get("MARIADB_USER", "justnews"),
        "password": os.environ.get("MARIADB_PASSWORD", "dev_justnews_password"),
        "database": os.environ.get("MARIADB_DB", "justnews"),
        "connection_timeout": 10,
        "autocommit": True,
    }


def read_queue_counts() -> dict[str, int]:
    conn = mysql.connector.connect(**db_config())
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM articles WHERE analyzed = 0) AS unanalyzed_count,
              (SELECT COUNT(*) FROM articles WHERE analyzed = 1 AND embedded = 0) AS unembedded_count,
              (SELECT COUNT(*) FROM articles WHERE analyzed = 1 AND fact_check_status IS NULL) AS unfactchecked_count,
              (SELECT COUNT(*) FROM articles WHERE is_synthesized = 0 AND input_cluster_ids IS NOT NULL AND input_cluster_ids != '[]' AND input_cluster_ids != '') AS unsynth_clustered_count,
              (SELECT COUNT(*) FROM synthesized_articles WHERE is_published = 0 AND (critique_status IS NULL OR critique_status = 'pending')) AS pending_critique_count,
              (SELECT COUNT(*) FROM synthesized_articles WHERE is_published = 0 AND critique_status = 'completed') AS ready_to_publish_count
            """
        )
        row = cur.fetchone() or (0, 0, 0, 0, 0, 0)
        return {
            "unanalyzed_count": int(row[0] or 0),
            "unembedded_count": int(row[1] or 0),
            "unfactchecked_count": int(row[2] or 0),
            "unsynth_clustered_count": int(row[3] or 0),
            "pending_critique_count": int(row[4] or 0),
            "ready_to_publish_count": int(row[5] or 0),
        }
    finally:
        cur.close()
        conn.close()


def main() -> int:
    args = parse_args()
    os.makedirs(os.path.dirname(args.out_jsonl), exist_ok=True)

    sample_idx = 0
    while True:
        sample_idx += 1
        payload = {
            "sample": sample_idx,
            "captured_at": utc_now(),
            "queue_counts": read_queue_counts(),
        }
        line = json.dumps(payload, sort_keys=True)
        print(line)
        with open(args.out_jsonl, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

        if args.samples > 0 and sample_idx >= args.samples:
            break

        time.sleep(max(args.interval_seconds, 0.1))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
