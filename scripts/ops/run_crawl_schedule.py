#!/usr/bin/env python3
"""Stage B1 crawl scheduler entry-point.

This module orchestrates automated crawl runs by reading
`config/crawl_schedule.yaml`, selecting the runs that are due for the current
window, and invoking the crawler agent sequentially with guarded article
budgets. It is designed to execute from a systemd timer (hourly cadence by
default) but also supports ad-hoc invocations for QA using the `--dry-run`
flag.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure project root is importable when executed as a standalone script
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import requests  # noqa: E402
from prometheus_client import CollectorRegistry, Gauge, write_to_textfile  # noqa: E402

from agents.crawler.adaptive_metrics import summarise_adaptive_articles  # noqa: E402
from agents.crawler.crawler_utils import get_active_sources  # noqa: E402
from agents.crawler_control.crawl_profiles import (  # noqa: E402
    CrawlProfileError,
    CrawlProfileRegistry,
    load_crawl_profiles,
)
from agents.crawler_control.crawl_schedule import (  # noqa: E402
    CrawlRun,
    CrawlSchedule,
    CrawlScheduleError,
    load_crawl_schedule,
    load_crawl_schedule_from_sources,
)
from common.metrics import JustNewsMetrics  # noqa: E402

DEFAULT_SCHEDULE_PATH = Path("config/crawl_schedule.yaml")
DEFAULT_STATE_PATH = Path("logs/analytics/crawl_scheduler_state.json")
DEFAULT_SUCCESS_PATH = Path("logs/analytics/crawl_scheduler_success.json")
DEFAULT_METRICS_OUTPUT = Path("logs/analytics/crawl_scheduler.prom")
DEFAULT_CRAWLER_URL = "http://127.0.0.1:8015"
DEFAULT_CRAWLER_POLL_INTERVAL = 5.0

STOP_REASON_LABELS: set[str] = set()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Stage B1 crawl schedule")
    parser.add_argument(
        "--schedule",
        type=Path,
        default=DEFAULT_SCHEDULE_PATH,
        help="Path to crawl schedule YAML (default: config/crawl_schedule.yaml)",
    )
    parser.add_argument(
        "--state-output",
        type=Path,
        default=DEFAULT_STATE_PATH,
        help="Path to write scheduler state JSON for governance logs",
    )
    parser.add_argument(
        "--success-output",
        type=Path,
        default=DEFAULT_SUCCESS_PATH,
        help="Path to append summary of successful executions",
    )
    parser.add_argument(
        "--crawler-url",
        default=DEFAULT_CRAWLER_URL,
        help="Crawler agent base URL (default: http://127.0.0.1:8015)",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=DEFAULT_METRICS_OUTPUT,
        help="Path to write Prometheus textfile metrics",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not invoke the crawler endpoint; print planned actions only",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Do not sleep until minute offsets; trigger immediately",
    )
    parser.add_argument(
        "--max-target",
        type=int,
        default=None,
        help="Override target articles per hour budget",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Override HTTP timeout for crawl requests",
    )
    parser.add_argument(
        "--testrun",
        action="store_true",
        help="Use the static schedule file instead of database-driven source discovery",
    )
    parser.add_argument(
        "--db-limit",
        type=int,
        default=None,
        help="Limit number of sources fetched from the database when building dynamic schedule",
    )
    parser.add_argument(
        "--db-chunk-size",
        type=int,
        default=10,
        help="Number of domains per run when generating schedule from database sources (default: 10)",
    )
    parser.add_argument(
        "--profiles",
        type=Path,
        default=Path("config/crawl_profiles"),
        help="Path to Crawl4AI profile configuration directory or YAML file (default: config/crawl_profiles)",
    )
    parser.add_argument(
        "--NoFollow",
        choices=("true", "false"),
        default=None,
        help="If true, do not follow external links when crawling (overrides profile/env)",
    )
    return parser.parse_args()


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _now() -> datetime:
    return datetime.now(UTC)


def _sleep_until(target: datetime) -> None:
    now = _now()
    delay = (target - now).total_seconds()
    if delay > 1:
        time.sleep(delay)


def _effective_limit(remaining: int, run: CrawlRun) -> int:
    if remaining <= 0:
        return 0

    domains = max(len(run.domains), 1)
    per_site_cap = run.max_articles_per_site or remaining

    if per_site_cap * domains <= remaining:
        return per_site_cap

    limit = remaining // domains
    return limit if limit > 0 else 0


def _iter_adaptive_articles(runs: list[dict[str, Any]]):
    for run in runs:
        result = run.get("result")
        if not isinstance(result, Mapping):
            continue
        articles = result.get("articles")
        if not isinstance(articles, list):
            continue
        for article in articles:
            if isinstance(article, Mapping):
                yield article


def _build_payload(
    run: CrawlRun,
    max_articles: int,
    timeout_seconds: int,
    strategy: str,
    enable_ai: bool,
    profile_overrides: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    concurrency = run.concurrent_sites
    kwargs = {
        "max_articles_per_site": max_articles,
        "concurrent_sites": concurrency,
        "strategy": strategy,
        "enable_ai": enable_ai,
        "timeout": timeout_seconds,
        "schedule_name": run.name,
        "priority": run.priority,
        "max_sites": len(run.domains),
    }
    if profile_overrides:
        kwargs["profile_overrides"] = profile_overrides
    return {"args": [run.domains], "kwargs": kwargs}


def _await_job(base_url: str, job_id: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    status_url = f"{base_url}/job_status/{job_id}"

    while True:
        request_deadline = max(deadline - time.time(), 0)
        # Give the crawler a generous window to respond while still honouring the overall deadline.
        per_request_timeout = max(min(request_deadline, 30), 5)

        try:
            response = requests.get(status_url, timeout=per_request_timeout)
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            if time.time() >= deadline:
                raise TimeoutError(
                    f"Job {job_id} exceeded timeout {timeout_seconds}s"
                ) from exc
            continue
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Failed to fetch job status for {job_id}: {exc}"
            ) from exc

        status = payload.get("status")
        if status in {"completed", "failed"}:
            return payload

        if time.time() >= deadline:
            raise TimeoutError(f"Job {job_id} exceeded timeout {timeout_seconds}s")

        time.sleep(DEFAULT_CRAWLER_POLL_INTERVAL)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _append_success(path: Path, entry: dict[str, Any]) -> None:
    _ensure_parent(path)
    if not path.exists():
        history: list[dict[str, Any]] = []
    else:
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    history.append(entry)
    path.write_text(json.dumps(history[-200:], indent=2), encoding="utf-8")


def _init_metrics() -> tuple[CollectorRegistry, dict[str, Gauge]]:
    registry = CollectorRegistry()
    JustNewsMetrics("crawler_scheduler", registry=registry)
    gauges = {
        "domains": Gauge(
            "justnews_crawler_scheduler_domains_crawled_total",
            "Domains crawled during this scheduler window",
            registry=registry,
        ),
        "articles": Gauge(
            "justnews_crawler_scheduler_articles_accepted_total",
            "Articles accepted during this scheduler window",
            registry=registry,
        ),
        "lag": Gauge(
            "justnews_crawler_scheduler_lag_seconds",
            "Lag between scheduled and actual crawl start",
            registry=registry,
        ),
        "timestamp": Gauge(
            "justnews_crawler_scheduler_last_successful_run_timestamp",
            "Unix timestamp of last successful crawl batch",
            registry=registry,
        ),
        "adaptive_articles": Gauge(
            "justnews_crawler_scheduler_adaptive_articles_total",
            "Articles produced via adaptive Crawl4AI pipeline this window",
            registry=registry,
        ),
        "adaptive_sufficient": Gauge(
            "justnews_crawler_scheduler_adaptive_articles_sufficient_total",
            "Adaptive articles meeting sufficiency criteria",
            registry=registry,
        ),
        "adaptive_confidence": Gauge(
            "justnews_crawler_scheduler_adaptive_confidence_average",
            "Average adaptive confidence score across the window",
            registry=registry,
        ),
        "adaptive_pages": Gauge(
            "justnews_crawler_scheduler_adaptive_pages_crawled_average",
            "Average pages crawled per adaptive article",
            registry=registry,
        ),
        "adaptive_stop_reasons": Gauge(
            "justnews_crawler_scheduler_adaptive_stop_reasons_total",
            "Adaptive stop reason occurrence counts",
            ["reason"],
            registry=registry,
        ),
    }
    return registry, gauges


def main() -> int:
    args = _parse_args()
    # Backwards-compatibility guard: ensure attributes tests expect exist
    if not hasattr(args, "profiles"):
        args.profiles = None

    try:
        base_schedule: CrawlSchedule = load_crawl_schedule(args.schedule)
    except CrawlScheduleError as exc:
        print(f"[scheduler] failed to load schedule: {exc}", file=sys.stderr)
        return 2

    schedule: CrawlSchedule = base_schedule

    if args.testrun:
        print(
            "[scheduler] test run flag enabled; using static schedule", file=sys.stderr
        )
    else:
        sources = get_active_sources(limit=args.db_limit)
        if sources:
            overrides = {
                "target_articles_per_hour": base_schedule.global_config.target_articles_per_hour,
                "default_max_articles_per_site": base_schedule.global_config.default_max_articles_per_site,
                "default_concurrent_sites": base_schedule.global_config.default_concurrent_sites,
                "default_timeout_seconds": base_schedule.global_config.default_timeout_seconds,
                "strategy": base_schedule.global_config.strategy,
                "enable_ai_enrichment": base_schedule.global_config.enable_ai_enrichment,
                "governance": base_schedule.global_config.governance,
            }
            metadata = dict(base_schedule.metadata)
            try:
                schedule = load_crawl_schedule_from_sources(
                    sources,
                    chunk_size=args.db_chunk_size,
                    metadata=metadata,
                    global_overrides=overrides,
                )
                print("[scheduler] using database-backed source list", file=sys.stderr)
            except CrawlScheduleError as exc:
                print(
                    f"[scheduler] database schedule build failed: {exc}; falling back to static configuration",
                    file=sys.stderr,
                )
        else:
            print(
                "[scheduler] no database sources returned; falling back to static schedule",
                file=sys.stderr,
            )

    profile_registry: CrawlProfileRegistry | None = None
    if args.profiles:
        try:
            profile_registry = load_crawl_profiles(args.profiles)
            print(
                f"[scheduler] loaded crawl profiles from {args.profiles}",
                file=sys.stderr,
            )
        except FileNotFoundError:
            print(
                f"[scheduler] crawl profile file not found: {args.profiles}",
                file=sys.stderr,
            )
        except CrawlProfileError as exc:
            print(f"[scheduler] failed to load crawl profiles: {exc}", file=sys.stderr)

    reference_time = _now()
    due_runs = schedule.due_runs(reference_time)
    if not due_runs:
        print("[scheduler] no runs due for this window")
        return 0

    target_articles = args.max_target or schedule.global_config.target_articles_per_hour
    remaining_articles = max(target_articles, 0)
    timeout_seconds = args.timeout or schedule.global_config.default_timeout_seconds

    registry, gauges = _init_metrics()
    total_domains = 0
    total_articles = 0
    worst_lag = 0.0
    last_success_epoch: float | None = None
    run_results: list[dict[str, Any]] = []

    for run in due_runs:
        scheduled_start = run.scheduled_start(reference_time)

        if remaining_articles <= 0:
            run_results.append(
                {
                    "name": run.name,
                    "status": "skipped",
                    "reason": "article budget exhausted",
                    "scheduled_start": scheduled_start.isoformat(),
                }
            )
            continue

        effective_limit = _effective_limit(remaining_articles, run)
        if effective_limit <= 0:
            run_results.append(
                {
                    "name": run.name,
                    "status": "skipped",
                    "reason": "insufficient article budget per site",
                    "scheduled_start": scheduled_start.isoformat(),
                }
            )
            continue

        if not args.no_wait and not args.dry_run:
            _sleep_until(scheduled_start)

        run_start = _now()
        lag_seconds = max((run_start - scheduled_start).total_seconds(), 0.0)
        worst_lag = max(worst_lag, lag_seconds)

        profile_overrides = (
            profile_registry.build_overrides(run.domains) if profile_registry else {}
        )

        # Apply CLI-level NoFollow override to profile_overrides when provided
        if args.NoFollow is not None:
            # convert NoFollow CLI value to boolean: 'true' -> disable following external
            no_follow_bool = str(args.NoFollow).lower() in ("1", "true", "yes")
            # follow_external is the inverse of NoFollow
            follow_external_value = not no_follow_bool
            for dom in run.domains:
                cur = profile_overrides.get(dom) or {}
                cur["follow_external"] = follow_external_value
                profile_overrides[dom] = cur

        payload = _build_payload(
            run,
            max_articles=effective_limit,
            timeout_seconds=timeout_seconds,
            strategy=schedule.global_config.strategy,
            enable_ai=schedule.global_config.enable_ai_enrichment,
            profile_overrides=profile_overrides,
        )

        result: dict[str, Any]
        status: str
        message: str | None = None

        if args.dry_run:
            status = "dry-run"
            result = {
                "domains": run.domains,
                "max_articles_per_site": effective_limit,
                "concurrent_sites": run.concurrent_sites,
            }
        else:
            try:
                submit_url = f"{args.crawler_url.rstrip('/')}/unified_production_crawl"
                response = requests.post(
                    submit_url, json=payload, timeout=timeout_seconds
                )
                response.raise_for_status()
                submission = response.json()
                job_id = submission.get("job_id")
                if not job_id:
                    raise RuntimeError("Crawler response missing job_id")
                job_payload = _await_job(
                    args.crawler_url.rstrip("/"), job_id, timeout_seconds
                )
                result = job_payload.get("result") or {}
                status = job_payload.get("status", "unknown")
                if status != "completed":
                    message = job_payload.get("error") or job_payload.get("message")
            except requests.RequestException as exc:
                status = "failed"
                message = str(exc)
                result = {}
            except TimeoutError as exc:
                status = "failed"
                message = str(exc)
                result = {}
            except RuntimeError as exc:
                status = "failed"
                message = str(exc)
                result = {}

        domains_count = len(run.domains)
        if status == "completed":
            articles_value = result.get(
                "articles_ingested", result.get("total_articles", 0)
            )
            try:
                articles_count = int(articles_value)
            except (TypeError, ValueError):
                articles_count = 0
        else:
            articles_count = 0

        if status == "completed":
            remaining_articles = max(remaining_articles - articles_count, 0)
            total_domains += domains_count
            total_articles += articles_count
            last_success_epoch = run_start.timestamp()
        elif status == "dry-run":
            total_domains += domains_count
            # No budget changes during dry run
        else:
            # For failed runs we do not deduct the budget to allow retry on next iteration
            pass

        run_results.append(
            {
                "name": run.name,
                "status": status,
                "scheduled_start": scheduled_start.isoformat(),
                "started_at": run_start.isoformat(),
                "lag_seconds": lag_seconds,
                "domains": run.domains,
                "max_articles_per_site": effective_limit,
                "result": result,
                "message": message,
            }
        )

    successful = [run for run in run_results if run["status"] == "completed"]
    adaptive_summary = summarise_adaptive_articles(_iter_adaptive_articles(successful))

    articles_block = adaptive_summary.get("articles", {}) if adaptive_summary else {}
    adaptive_total = float(articles_block.get("total", 0) or 0)
    adaptive_sufficient = float(articles_block.get("sufficient", 0) or 0)

    confidence_avg = None
    if adaptive_summary:
        confidence_avg = adaptive_summary.get("confidence", {}).get("average")
    pages_avg = None
    if adaptive_summary:
        pages_avg = adaptive_summary.get("pages_crawled", {}).get("average")

    gauges["adaptive_articles"].set(adaptive_total)
    gauges["adaptive_sufficient"].set(adaptive_sufficient)
    gauges["adaptive_confidence"].set(
        float(confidence_avg) if confidence_avg is not None else 0.0
    )
    gauges["adaptive_pages"].set(float(pages_avg) if pages_avg is not None else 0.0)

    stop_reasons = adaptive_summary.get("stop_reasons", {}) if adaptive_summary else {}
    if stop_reasons:
        for reason, count in stop_reasons.items():
            STOP_REASON_LABELS.add(reason)
            gauges["adaptive_stop_reasons"].labels(reason=reason).set(float(count))
    for reason in STOP_REASON_LABELS - set(stop_reasons):
        gauges["adaptive_stop_reasons"].labels(reason=reason).set(0.0)

    gauges["domains"].set(total_domains)
    gauges["articles"].set(total_articles)
    gauges["lag"].set(worst_lag)
    if last_success_epoch is not None:
        gauges["timestamp"].set(last_success_epoch)

    if args.metrics_output:
        _ensure_parent(args.metrics_output)
        write_to_textfile(args.metrics_output, registry)

    state_payload = {
        "executed_at": reference_time.isoformat(),
        "runs": run_results,
        "governance": schedule.governance,
        "target_articles": target_articles,
        "remaining_articles": remaining_articles,
        "dry_run": args.dry_run,
        "crawler_url": args.crawler_url,
    }
    if adaptive_summary:
        state_payload["adaptive_summary"] = adaptive_summary
    _write_json(args.state_output, state_payload)

    if successful:
        summary_entry = {
            "timestamp": reference_time.isoformat(),
            "runs": [
                {
                    "name": run["name"],
                    "domains": run["domains"],
                    "articles": run["result"].get("articles_ingested")
                    if isinstance(run.get("result"), dict)
                    else None,
                }
                for run in successful
            ],
            "total_articles": total_articles,
            "total_domains": total_domains,
        }
        _append_success(args.success_output, summary_entry)

    failed_runs = [run for run in run_results if run["status"] == "failed"]
    if failed_runs:
        print("[scheduler] one or more runs failed", file=sys.stderr)
        for run in failed_runs:
            print(f"  - {run['name']}: {run.get('message')}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
