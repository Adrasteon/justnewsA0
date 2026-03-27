#!/usr/bin/env python3
"""Verify BBC Lane 1 crawl returns per-article entities and per-url ingestion records.

This script triggers a live crawler job, polls completion, and validates:
1) Distinct BBC article URLs are returned (not a single blob artifact).
2) Feed/homepage XML is not ingested as one collapsed article body.
3) Ingestion details are tracked per article URL.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("CRAWLER_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _domain_matches(url: str, expected_domain: str) -> bool:
    domain = expected_domain.strip().lower().replace("www.", "")
    candidate = (url or "").strip().lower()
    if not candidate:
        return False
    host = candidate.split("//", 1)[-1].split("/", 1)[0].replace("www.", "")

    if "bbc" in domain:
        return any(
            host.endswith(item)
            for item in {"bbc.com", "bbc.co.uk", "bbci.co.uk", "feeds.bbci.co.uk"}
        )
    return host.endswith(domain)


def _contains_feed_markers(text: str) -> bool:
    sample = (text or "")[:6000].lower()
    markers = ["<rss", "<channel", "<item>", "</item>", "<?xml", "<feed"]
    return any(marker in sample for marker in markers)


def _write_reports(out_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"bbc_lane1_entity_verification_{stamp}.json"
    md_path = out_dir / f"bbc_lane1_entity_verification_{stamp}.md"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# BBC Lane 1 Entity Verification",
        "",
        f"Generated: {report.get('generated_at')}",
        f"Status: {report.get('status')}",
        f"Crawler URL: {report.get('crawler_url')}",
        f"Domain: {report.get('domain')}",
        "",
        "## Assertions",
    ]
    for check in report.get("assertions", []):
        lines.append(f"- {check.get('name')}: {'PASS' if check.get('ok') else 'FAIL'}")
        if check.get("detail"):
            lines.append(f"  - {check.get('detail')}")
    lines.extend(
        [
            "",
            "## Counts",
            f"- returned_articles: {report.get('returned_articles')}",
            f"- distinct_urls: {report.get('distinct_urls')}",
            f"- ingestion_detail_rows: {report.get('ingestion_detail_rows')}",
            f"- ingestion_detail_distinct_urls: {report.get('ingestion_detail_distinct_urls')}",
            "",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def _find_site_detail_rows(result: dict[str, Any], domain: str) -> list[dict[str, Any]]:
    details = result.get("site_ingestion_details")
    if not isinstance(details, dict):
        return []

    selected: list[dict[str, Any]] = []
    for key, rows in details.items():
        key_match = str(key or "").strip().lower()
        if "bbc" in domain.lower():
            is_match = "bbc" in key_match
        else:
            is_match = domain.lower() in key_match
        if not is_match or not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                selected.append(row)
    return selected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify BBC Lane 1 per-article ingestion behavior")
    parser.add_argument("--crawler-url", default=os.environ.get("CRAWLER_URL", "http://localhost:8015"))
    parser.add_argument("--domain", default="bbc.co.uk")
    parser.add_argument("--requested", type=int, default=10)
    parser.add_argument("--min-articles", type=int, default=8)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    parser.add_argument("--out-dir", default="logs/operations/live_validation")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    crawler_url = str(args.crawler_url).rstrip("/")

    submit_payload = {
        "args": [[args.domain]],
        "kwargs": {
            "max_articles_per_site": int(args.requested),
            "concurrent_sites": 1,
        },
    }

    report: dict[str, Any] = {
        "generated_at": _utc_now(),
        "crawler_url": crawler_url,
        "domain": args.domain,
        "requested": int(args.requested),
        "min_articles": int(args.min_articles),
        "status": "error",
        "assertions": [],
    }

    try:
        submit_resp = requests.post(
            f"{crawler_url}/unified_production_crawl",
            headers=_headers(),
            json=submit_payload,
            timeout=(5, 30),
        )
        submit_resp.raise_for_status()
        submit_data = submit_resp.json()
        job_id = str(submit_data.get("job_id") or "").strip()
        if not job_id:
            raise RuntimeError(f"Crawler did not return a job_id: {submit_data}")
        report["job_id"] = job_id
    except Exception as exc:
        report["error"] = f"failed_to_submit: {exc}"
        json_out, md_out = _write_reports(Path(args.out_dir), report)
        print(json.dumps({"status": "error", "json_out": str(json_out), "md_out": str(md_out)}, indent=2))
        return 2

    deadline = time.time() + float(args.timeout_seconds)
    final_job: dict[str, Any] | None = None
    while time.time() < deadline:
        status_resp = requests.get(
            f"{crawler_url}/job_status/{report['job_id']}",
            headers=_headers(),
            timeout=(5, 30),
        )
        status_resp.raise_for_status()
        status_data = status_resp.json()
        state = str(status_data.get("status") or "").strip().lower()
        if state in {"completed", "failed", "cancelled"}:
            final_job = status_data
            break
        time.sleep(float(args.poll_interval))

    if final_job is None:
        report["error"] = "timeout_waiting_for_completion"
        json_out, md_out = _write_reports(Path(args.out_dir), report)
        print(json.dumps({"status": "error", "json_out": str(json_out), "md_out": str(md_out)}, indent=2))
        return 2

    report["job_status"] = final_job.get("status")
    result = final_job.get("result") if isinstance(final_job.get("result"), dict) else {}
    articles = result.get("articles") if isinstance(result.get("articles"), list) else []

    bbc_articles = [a for a in articles if isinstance(a, dict) and _domain_matches(str(a.get("url") or ""), args.domain)]
    urls = [str(a.get("url") or "").strip() for a in bbc_articles if str(a.get("url") or "").strip()]
    distinct_urls = sorted(set(urls))

    feed_blob_marked = False
    for item in bbc_articles:
        title = str(item.get("title") or "")
        content = str(item.get("content") or "")
        if _contains_feed_markers(title) or _contains_feed_markers(content):
            feed_blob_marked = True
            break

    detail_rows = _find_site_detail_rows(result, args.domain)
    detail_urls = sorted(
        {
            str(row.get("url") or "").strip()
            for row in detail_rows
            if str(row.get("url") or "").strip()
        }
    )

    checks = [
        {
            "name": "returned_at_least_minimum_articles",
            "ok": len(bbc_articles) >= int(args.min_articles),
            "detail": f"returned={len(bbc_articles)} min_required={int(args.min_articles)}",
        },
        {
            "name": "not_collapsed_single_blob",
            "ok": len(bbc_articles) > 1,
            "detail": f"returned={len(bbc_articles)}",
        },
        {
            "name": "distinct_article_urls_present",
            "ok": len(distinct_urls) > 1,
            "detail": f"distinct_urls={len(distinct_urls)}",
        },
        {
            "name": "no_feed_xml_ingested_as_article_content",
            "ok": not feed_blob_marked,
            "detail": "feed markers were found in returned article payload" if feed_blob_marked else "no feed markers found",
        },
        {
            "name": "per_article_ingestion_records_present",
            "ok": len(detail_urls) > 1,
            "detail": f"ingestion_detail_rows={len(detail_rows)} distinct_detail_urls={len(detail_urls)}",
        },
    ]

    report["returned_articles"] = len(bbc_articles)
    report["distinct_urls"] = len(distinct_urls)
    report["ingestion_detail_rows"] = len(detail_rows)
    report["ingestion_detail_distinct_urls"] = len(detail_urls)
    report["assertions"] = checks
    report["sample_urls"] = distinct_urls[:20]
    report["sample_ingestion_details"] = detail_rows[:20]

    passed = all(bool(item.get("ok")) for item in checks)
    report["status"] = "pass" if passed else "fail"

    json_out, md_out = _write_reports(Path(args.out_dir), report)
    print(json.dumps({"status": report["status"], "json_out": str(json_out), "md_out": str(md_out)}, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
