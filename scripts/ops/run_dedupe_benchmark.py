#!/usr/bin/env python3
"""Run repeat crawl+orchestrator cycles and report throughput/latency.

This script is mode-agnostic. Run it once with DEDUPE_ARTICLES=false and once
with DEDUPE_ARTICLES=true using the same arguments, then compare outputs.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mysql.connector
import requests


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run dedupe benchmark cycles")
    parser.add_argument("--label", required=True, help="Run label (for output filenames)")
    parser.add_argument(
        "--domains",
        default="bbc.co.uk,reuters.com,apnews.com,aljazeera.com,cnn.com",
        help="Comma-separated domains",
    )
    parser.add_argument("--cycles", type=int, default=6, help="Number of benchmark cycles")
    parser.add_argument("--max-articles-per-site", type=int, default=25)
    parser.add_argument("--concurrent-sites", type=int, default=3)
    parser.add_argument("--crawl-timeout-seconds", type=int, default=420)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--sleep-between-cycles", type=float, default=20.0)
    parser.add_argument("--crawler-url", default="http://127.0.0.1:8022")
    parser.add_argument("--out-dir", default="logs/operations/dedupe_ab")
    parser.add_argument("--smoke-limit", type=int, default=8)
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip running refactor E2E smoke per cycle",
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


def read_total_articles() -> int:
    conn = mysql.connector.connect(**db_config())
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM articles")
        row = cur.fetchone()
        return int((row or [0])[0] or 0)
    finally:
        cur.close()
        conn.close()


def read_queue_counts() -> dict[str, int]:
    conn = mysql.connector.connect(**db_config())
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM articles WHERE analyzed = 0),
              (SELECT COUNT(*) FROM articles WHERE analyzed = 1 AND embedded = 0),
              (SELECT COUNT(*) FROM articles WHERE analyzed = 1 AND fact_check_status IS NULL),
              (SELECT COUNT(*) FROM articles WHERE is_synthesized = 0 AND input_cluster_ids IS NOT NULL AND input_cluster_ids != '[]' AND input_cluster_ids != ''),
              (SELECT COUNT(*) FROM synthesized_articles WHERE is_published = 0 AND (critique_status IS NULL OR critique_status = 'pending')),
              (SELECT COUNT(*) FROM synthesized_articles WHERE is_published = 0 AND critique_status = 'completed')
            """
        )
        row = cur.fetchone() or (0, 0, 0, 0, 0, 0)
        return {
            "unanalyzed": int(row[0] or 0),
            "unembedded": int(row[1] or 0),
            "unfactchecked": int(row[2] or 0),
            "unsynth_clustered": int(row[3] or 0),
            "pending_critique": int(row[4] or 0),
            "ready_publish": int(row[5] or 0),
        }
    finally:
        cur.close()
        conn.close()


def submit_crawl(crawler_url: str, domains: list[str], max_articles_per_site: int, concurrent_sites: int) -> str:
    payload = {
        "args": [domains],
        "kwargs": {
            "max_articles_per_site": int(max_articles_per_site),
            "concurrent_sites": int(concurrent_sites),
        },
    }
    response = requests.post(
        f"{crawler_url.rstrip('/')}/unified_production_crawl",
        json=payload,
        timeout=(5, 60),
    )
    response.raise_for_status()
    body = response.json()
    job_id = str(body.get("job_id") or "").strip()
    if not job_id:
        raise RuntimeError(f"crawler did not return job_id: {body}")
    return job_id


def wait_job(crawler_url: str, job_id: str, timeout_seconds: int, poll_seconds: float) -> dict[str, Any]:
    deadline = time.time() + float(timeout_seconds)
    while time.time() < deadline:
        resp = requests.get(f"{crawler_url.rstrip('/')}/job_status/{job_id}", timeout=(5, 60))
        resp.raise_for_status()
        body = resp.json()
        status = str(body.get("status") or "").lower()
        if status in {"completed", "failed", "cancelled"}:
            return body
        time.sleep(max(poll_seconds, 0.5))
    raise TimeoutError(f"job {job_id} timed out after {timeout_seconds}s")


def run_smoke(smoke_limit: int) -> dict[str, Any]:
    cmd = [
        "/app/.venv/bin/python",
        "scripts/ops/run_refactor_e2e_smoke.py",
        "--execute",
        "--limit",
        str(smoke_limit),
    ]
    proc = subprocess.run(cmd, cwd="/app", capture_output=True, text=True)
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    try:
        summary = json.loads(stdout.splitlines()[-1]) if stdout else {}
    except Exception:
        summary = {"raw_stdout": stdout}
    return {
        "return_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "summary": summary,
    }


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return float(ordered[index])


def to_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Dedupe Benchmark Report")
    lines.append("")
    lines.append(f"Generated: {report['generated_at']}")
    lines.append(f"Label: {report['label']}")
    lines.append(f"Dedupe setting: {report['dedupe_articles']}")
    lines.append(f"Domains: {', '.join(report['domains'])}")
    lines.append("")
    lines.append("## Summary")
    for k, v in report["summary"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Cycles")
    for c in report["cycles"]:
        lines.append(
            "- "
            + f"cycle={c['cycle']} job_id={c.get('job_id')} job_status={c.get('job_status')} "
            + f"crawl_seconds={c.get('crawl_seconds')} articles_returned={c.get('articles_returned')} "
            + f"smoke_rc={c.get('smoke_return_code')} queue_after={c.get('queue_after')}"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    domains = [d.strip() for d in args.domains.split(",") if d.strip()]
    if not domains:
        raise SystemExit("--domains cannot be empty")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline_articles = read_total_articles()
    cycles: list[dict[str, Any]] = []
    crawl_durations: list[float] = []
    total_returned = 0
    smoke_ok = 0

    for i in range(1, args.cycles + 1):
        cycle: dict[str, Any] = {"cycle": i, "started_at": utc_now()}
        print(f"[cycle {i}/{args.cycles}] submitting crawl job", flush=True)
        start = time.time()
        try:
            job_id = submit_crawl(args.crawler_url, domains, args.max_articles_per_site, args.concurrent_sites)
            cycle["job_id"] = job_id
            print(f"[cycle {i}/{args.cycles}] job_id={job_id} waiting completion", flush=True)
            result = wait_job(args.crawler_url, job_id, args.crawl_timeout_seconds, args.poll_seconds)
            status = str(result.get("status") or "")
            cycle["job_status"] = status
            payload = result.get("result") if isinstance(result.get("result"), dict) else {}
            articles = payload.get("articles") if isinstance(payload.get("articles"), list) else []
            cycle["articles_returned"] = len(articles)
            total_returned += len(articles)
        except Exception as exc:
            cycle["job_status"] = "error"
            cycle["error"] = str(exc)
            cycle["articles_returned"] = 0
            print(f"[cycle {i}/{args.cycles}] crawl error: {exc}", flush=True)

        crawl_seconds = round(time.time() - start, 3)
        cycle["crawl_seconds"] = crawl_seconds
        crawl_durations.append(crawl_seconds)

        if args.skip_smoke:
            cycle["smoke_return_code"] = None
            cycle["smoke_summary"] = {"status": "skipped"}
        else:
            smoke = run_smoke(args.smoke_limit)
            cycle["smoke_return_code"] = smoke["return_code"]
            cycle["smoke_summary"] = smoke["summary"]
            if smoke["return_code"] == 0:
                smoke_ok += 1

        cycle["queue_after"] = read_queue_counts()
        cycle["ended_at"] = utc_now()
        cycles.append(cycle)
        print(
            f"[cycle {i}/{args.cycles}] done status={cycle.get('job_status')} "
            f"crawl_seconds={crawl_seconds} queue_after={cycle.get('queue_after')}",
            flush=True,
        )

        if i < args.cycles:
            time.sleep(max(args.sleep_between_cycles, 0.0))

    final_articles = read_total_articles()
    summary = {
        "cycles": args.cycles,
        "jobs_completed": sum(1 for c in cycles if c.get("job_status") == "completed"),
        "jobs_failed_or_error": sum(1 for c in cycles if c.get("job_status") != "completed"),
        "smoke_ok_cycles": smoke_ok,
        "smoke_nonzero_cycles": (args.cycles - smoke_ok) if not args.skip_smoke else 0,
        "total_articles_returned_by_crawler": int(total_returned),
        "article_table_delta": int(final_articles - baseline_articles),
        "crawl_seconds_avg": round(statistics.fmean(crawl_durations), 3) if crawl_durations else 0.0,
        "crawl_seconds_p95": round(percentile(crawl_durations, 95), 3),
        "final_queue_counts": read_queue_counts(),
    }

    report = {
        "generated_at": utc_now(),
        "label": args.label,
        "dedupe_articles": os.environ.get("DEDUPE_ARTICLES", "<unset>"),
        "domains": domains,
        "config": {
            "cycles": args.cycles,
            "max_articles_per_site": args.max_articles_per_site,
            "concurrent_sites": args.concurrent_sites,
            "crawl_timeout_seconds": args.crawl_timeout_seconds,
            "poll_seconds": args.poll_seconds,
            "sleep_between_cycles": args.sleep_between_cycles,
            "smoke_limit": args.smoke_limit,
            "crawler_url": args.crawler_url,
        },
        "summary": summary,
        "cycles": cycles,
    }

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"dedupe_benchmark_{args.label}_{stamp}.json"
    md_path = out_dir / f"dedupe_benchmark_{args.label}_{stamp}.md"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(to_markdown(report), encoding="utf-8")

    print(json.dumps({"status": "ok", "json_out": str(json_path), "md_out": str(md_path), "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
