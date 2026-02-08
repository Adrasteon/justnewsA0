from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

import requests

from agents.common.agent_chain_harness import NormalizedArticle


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not slug:
        slug = "article"
    return slug


def _publisher_db_path() -> Path:
    # project root -> db.sqlite3
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "db.sqlite3"


def publish_normalized_article(
    article: NormalizedArticle,
    *,
    author: str | None = None,
    score: float = 0.0,
    evidence: str = "",
    is_featured: bool = False,
    category: str = "world",
) -> bool:
    """Publish a normalized article into the lightweight publisher DB.

    Returns True on insertion or update, False on failure.
    """
    # If an external PUBLISHER_URL is set we POST the payload instead of using the
    # local SQLite DB. This is used in CI/staging to publish into a running staging
    # publisher instance that accepts API-key authenticated POSTs.
    publisher_url = os.environ.get("PUBLISHER_URL")
    api_key = os.environ.get("PUBLISHER_API_KEY")
    payload = {
        "article_id": article.article_id,
        "title": article.title,
        "slug": _slugify(article.title or article.article_id or "article"),
        "summary": (article.text or "")[:400],
        "body": article.text or "",
        "author": author or "Editorial Harness",
        "score": float(score),
        "evidence": evidence,
        "is_featured": 1 if is_featured else 0,
        "category": category,
    }

    if publisher_url:
        # Try HTTP publish
        try:
            headers = {}
            if api_key:
                headers["X-API-KEY"] = api_key
            resp = requests.post(
                publisher_url.rstrip("/") + "/api/publish/",
                json=payload,
                headers=headers,
                timeout=10,
            )
            return resp.status_code == 200 and resp.json().get("result") == "ok"
        except Exception:
            raise

    # Fallback to local SQLite DB for dev / tests
    db_path = _publisher_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Publisher DB not found at {db_path}")

    slug = payload["slug"]
    summary = payload["summary"]
    body = payload["body"]
    author = payload["author"]

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO news_article (slug, title, summary, body, author, score, evidence, is_featured, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                article.title,
                summary,
                body,
                author,
                float(score),
                evidence,
                1 if is_featured else 0,
                category,
            ),
        )
        conn.commit()
        # If ignored because exists, we still treat as success
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify_publish_token(token: str | None) -> bool:
    """Return True when the given token matches an approved publish token.

    Token resolution precedence:
    1. Environment variable PUBLISH_APPROVAL_TOKEN (recommended for CI)
    2. File at <repo_root>/deploy/publish.token (recommended for operator manual approval)
    """
    if not token:
        return False

    # Check environment variable override
    env_token = os.environ.get("PUBLISH_APPROVAL_TOKEN")
    if env_token and token == env_token:
        return True

    # Optionally read the token file path from environment for testability / CI
    token_file_path = os.environ.get("PUBLISH_APPROVAL_TOKEN_FILE")
    if token_file_path:
        token_file = Path(token_file_path)
    else:
        # Fall back to checking a local file under repo deploy/ (safe operator signal)
        repo_root = Path(__file__).resolve().parents[3]
        token_file = repo_root / "deploy" / "publish.token"
    if token_file.exists():
        try:
            content = token_file.read_text(encoding="utf-8").strip()
            return content == token
        except Exception:
            return False

    return False
