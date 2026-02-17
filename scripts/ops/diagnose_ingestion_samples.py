#!/usr/bin/env python3
"""
Diagnostic helper: sample raw_html files and check whether corresponding
articles already exist in MariaDB (and optionally test memory /ingest_article).

Usage:
  PYTHONPATH=. ./scripts/ops/diagnose_ingestion_samples.py --sample 10 [--post]

The script reads the most recent N files from archive_storage/raw_html, extracts
candidate URLs and runs a SQL query against the configured MariaDB (reads env)
to check for existing articles by `url`, `normalized_url`, and `url_hash`.

Optional `--post` will send the payload to the Memory agent ingest endpoint at
http://localhost:8007/ingest_article to observe the runtime response (safe, but
will cause side effects in a live DB if insertion proceeds).

This is a read-first diagnostic; use care running `--post` on live systems.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

# Ensure top-level imports from repo work
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

try:
    from common.url_normalization import hash_article_url, normalize_article_url
except Exception as exc:
    print("Could not import normalization helpers from the repository:", exc)
    print("You may need to run this from the workspace root with PYTHONPATH=.")
    raise

try:
    import mysql.connector

    _MYSQL_AVAILABLE = True
except Exception:
    mysql = None
    _MYSQL_AVAILABLE = False

HREF_RE = re.compile(r'href=["\'](https?://[^"\']+)["\']', re.I)


def find_recent_raw_html(n: int) -> list[Path]:
    path = REPO_ROOT / "archive_storage" / "raw_html"
    if not path.exists():
        return []
    files = sorted(path.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:n]


def extract_first_url_from_file(fp: Path) -> str | None:
    text = fp.read_text(errors="ignore")
    m = HREF_RE.search(text)
    if m:
        return m.group(1)
    # Fallback: search for bare urls
    m2 = re.search(r"(https?://\S+)", text)
    return m2.group(1) if m2 else None


def connect_mariadb_from_env():
    # If environment variables aren't set (e.g. running directly from repo),
    # try loading project `global.env` to provide sensible defaults.
    if not os.environ.get("MARIADB_HOST") and (REPO_ROOT / "global.env").exists():
        try:
            for line in (REPO_ROOT / "global.env").read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"')
                # only set MARIADB_ and related variables to avoid overwriting runtime env
                if k.startswith("MARIADB_") and k not in os.environ:
                    os.environ[k] = v
        except Exception:
            # best-effort only
            pass

    cfg = {
        "host": os.environ.get("MARIADB_HOST", "127.0.0.1"),
        "port": int(os.environ.get("MARIADB_PORT", 3306)),
        "database": os.environ.get("MARIADB_DB", "justnews"),
        "user": os.environ.get("MARIADB_USER", "justnews"),
        "password": os.environ.get("MARIADB_PASSWORD"),
    }
    # Do NOT print password in logs
    if not _MYSQL_AVAILABLE:
        print("mysql connector not available in this environment; skipping DB checks")
        return None

    try:
        conn = mysql.connector.connect(
            **{k: v for k, v in cfg.items() if v is not None}
        )
        return conn
    except Exception as e:
        print("Failed to connect to MariaDB:", e)
        return None


def check_article_exists(conn, url: str, normalized: str | None, urlhash: str | None):
    cursor = conn.cursor()
    out = {}
    try:
        cursor.execute(
            "SELECT id, url, normalized_url, url_hash, created_at FROM articles WHERE url = %s LIMIT 1",
            (url,),
        )
        row = cursor.fetchone()
        if row:
            out["by_url"] = {
                "id": row[0],
                "url": row[1],
                "normalized_url": row[2],
                "url_hash": row[3],
                "created_at": row[4].isoformat()
                if getattr(row[4], "isoformat", None)
                else str(row[4]),
            }
        else:
            out["by_url"] = None

        if normalized:
            cursor.execute(
                "SELECT id, url, normalized_url, url_hash, created_at FROM articles WHERE normalized_url = %s LIMIT 1",
                (normalized,),
            )
            row = cursor.fetchone()
            out["by_normalized"] = (
                {
                    "id": row[0],
                    "url": row[1],
                    "normalized_url": row[2],
                    "url_hash": row[3],
                    "created_at": row[4].isoformat()
                    if getattr(row[4], "isoformat", None)
                    else str(row[4]),
                }
                if row
                else None
            )
        else:
            out["by_normalized"] = None

        if urlhash:
            cursor.execute(
                "SELECT id, url, normalized_url, url_hash, created_at FROM articles WHERE url_hash = %s LIMIT 1",
                (urlhash,),
            )
            row = cursor.fetchone()
            out["by_hash"] = (
                {
                    "id": row[0],
                    "url": row[1],
                    "normalized_url": row[2],
                    "url_hash": row[3],
                    "created_at": row[4].isoformat()
                    if getattr(row[4], "isoformat", None)
                    else str(row[4]),
                }
                if row
                else None
            )
        else:
            out["by_hash"] = None

    except Exception as e:
        out["error"] = str(e)
    finally:
        try:
            cursor.close()
        except Exception:
            pass
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sample",
        "-n",
        type=int,
        default=10,
        help="Number of recent raw_html files to sample",
    )
    parser.add_argument(
        "--post",
        action="store_true",
        help="POST payload to memory agent /ingest_article for each sample (will cause side effects).",
    )
    parser.add_argument(
        "--post-url",
        default="http://127.0.0.1:8007/ingest_article",
        help="Memory agent ingest endpoint",
    )
    args = parser.parse_args()

    files = find_recent_raw_html(args.sample)
    if not files:
        print("No raw_html files found")
        return

    conn = connect_mariadb_from_env()
    if conn is None:
        print("Could not connect to MariaDB; continuing but DB checks will be skipped")

    report = []
    for f in files:
        sample = {
            "file": str(f),
            "sampled_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        }
        url = extract_first_url_from_file(f)
        sample["found_url"] = url
        if url:
            normalized = normalize_article_url(url, url)
            sample["normalized_url"] = normalized
            urlhash = hash_article_url(normalized or url)
            sample["url_hash"] = urlhash
            if conn:
                sample["db_check"] = check_article_exists(
                    conn, url, normalized, urlhash
                )
            else:
                sample["db_check"] = None

            if args.post:
                payload = {
                    "article_payload": {
                        "url": url,
                        "normalized_url": normalized,
                        "content": f.read_text(errors="ignore")[:2000],
                    }
                }
                try:
                    r = requests.post(args.post_url, json=payload, timeout=15)
                    sample["post_response_status"] = r.status_code
                    sample["post_response_body"] = r.text[:1000]
                except Exception as e:
                    sample["post_error"] = str(e)
        else:
            sample["note"] = "no_url_found"

        report.append(sample)

    # Close DB connection if used
    if conn:
        try:
            conn.close()
        except Exception:
            pass

    # Print a compact summary
    for r in report:
        print("\n---")
        print("file:", r.get("file"))
        print("sampled_at:", r.get("sampled_at"))
        print("found_url:", r.get("found_url"))
        if r.get("found_url"):
            print("normalized_url:", r.get("normalized_url"))
            print("url_hash:", r.get("url_hash"))
            db = r.get("db_check")
            if db:
                print("DB by url:", json.dumps(db.get("by_url")))
                print("DB by normalized:", json.dumps(db.get("by_normalized")))
                print("DB by hash:", json.dumps(db.get("by_hash")))
            else:
                print("DB check: skipped/failed")
        if r.get("post_response_status"):
            print("POST ->", r.get("post_response_status"), r.get("post_response_body"))
        if r.get("post_error"):
            print("POST error:", r.get("post_error"))

    # Exit with non-zero if any DB matches found — to indicate duplicates
    found = any(
        (
            r.get("db_check")
            and (
                r["db_check"].get("by_url")
                or r["db_check"].get("by_normalized")
                or r["db_check"].get("by_hash")
            )
        )
        for r in report
    )
    if found:
        print("\nOne or more samples appear to already exist in MariaDB (duplicates).")
    else:
        print(
            "\nNo matching records found in MariaDB for sampled files — possible issue elsewhere (embeddings/chroma/transaction rollback)."
        )


if __name__ == "__main__":
    main()
