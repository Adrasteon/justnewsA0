import json
import math
import re
from datetime import date, datetime
from email.utils import format_datetime
from html import escape
from urllib.parse import urlparse

from django.conf import settings
from django.db import connection
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .models import Article, ArticleSlugRedirect, PublishAudit


SOURCE_LINK_PATTERN = re.compile(r"https?://[^\s)\]]+", re.IGNORECASE)


def _trust_band(score: float) -> tuple[str, str]:
    if score >= 0.85:
        return "High Confidence", "trust-high"
    if score >= 0.6:
        return "Moderate Confidence", "trust-medium"
    return "Low Confidence", "trust-low"


def _estimate_read_time(text: str) -> int:
    words = len((text or "").split())
    return max(1, math.ceil(words / 220))


def _extract_source_links(evidence: str) -> list[str]:
    links = SOURCE_LINK_PATTERN.findall(evidence or "")
    deduped: list[str] = []
    for link in links:
        cleaned = link.rstrip(".,;:")
        if cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def _derive_narrative_signals(article: Article) -> dict[str, object]:
    text = f"{article.title} {article.summary} {article.body}".lower()
    loaded_terms = [
        "must",
        "clearly",
        "obviously",
        "undeniable",
        "shocking",
        "outrage",
        "traitor",
        "threat",
        "crisis",
        "extrem",
    ]
    framing_terms = [
        "experts say",
        "critics",
        "supporters",
        "according to",
        "officials",
        "sources say",
    ]
    counterview_terms = [
        "however",
        "but",
        "on the other hand",
        "meanwhile",
        "opponents",
        "counter",
    ]

    loaded_hits = sum(text.count(term) for term in loaded_terms)
    framing_hits = sum(text.count(term) for term in framing_terms)
    counterview_hits = sum(text.count(term) for term in counterview_terms)

    if loaded_hits >= 8:
        emotive_level = "High"
    elif loaded_hits >= 3:
        emotive_level = "Moderate"
    else:
        emotive_level = "Low"

    return {
        "emotive_language_hits": loaded_hits,
        "emotive_language_level": emotive_level,
        "attribution_density_hits": framing_hits,
        "counterview_signals": counterview_hits,
    }


def _build_article_card(article: Article) -> dict[str, object]:
    trust_label, trust_class = _trust_band(float(article.score or 0.0))
    source_links = _extract_source_links(article.evidence or "")
    return {
        "article": article,
        "trust_label": trust_label,
        "trust_class": trust_class,
        "read_time": _estimate_read_time(article.body or article.summary),
        "source_count": len(source_links),
    }


def _seo_description(article: Article, max_words: int = 30) -> str:
    source_text = (article.summary or "").strip() or (article.body or "").strip() or article.title
    words = source_text.split()
    return " ".join(words[:max_words]).strip()


def _safe_json_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _safe_json_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return []
    return []


def _cursor_row_to_dict(row: tuple[object, ...], columns: list[str]) -> dict[str, object]:
    return {columns[index]: row[index] for index in range(len(columns))}


def _resolve_story_suffix(slug: str) -> str | None:
    match = re.search(r"(STORY-[a-f0-9]{2})$", str(slug or ""), re.IGNORECASE)
    return match.group(1).upper() if match else None


def _resolve_story_context(article: Article, latest_audit: PublishAudit | None) -> dict[str, object]:
    story_id = None
    if latest_audit and latest_audit.payload:
        payload = latest_audit.payload if isinstance(latest_audit.payload, dict) else _safe_json_object(latest_audit.payload)
        candidate = payload.get("story_id") if isinstance(payload, dict) else None
        if isinstance(candidate, str) and candidate.strip():
            story_id = candidate.strip()

    with connection.cursor() as cursor:
        if story_id:
            cursor.execute(
                """
                SELECT story_id, cluster_id, input_articles, synth_metadata, updated_at
                FROM synthesized_articles
                WHERE story_id = %s
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                [story_id],
            )
            row = cursor.fetchone()
            if row:
                raw_meta = row[3]
                metadata = _safe_json_object(raw_meta)
                return {
                    "story_id": row[0],
                    "cluster_id": row[1],
                    "input_articles": _safe_json_list(row[2]),
                    "synth_metadata": metadata,
                    "living_story": metadata.get("living_story") if isinstance(metadata.get("living_story"), dict) else {},
                    "publish": metadata.get("publish") if isinstance(metadata.get("publish"), dict) else {},
                    "updated_at": row[4],
                }

        suffix = _resolve_story_suffix(article.slug)
        if not suffix:
            return {}

        cursor.execute(
            """
            SELECT story_id, cluster_id, input_articles, synth_metadata, updated_at
            FROM synthesized_articles
            WHERE story_id LIKE %s
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            [f"{suffix}%"],
        )
        row = cursor.fetchone()
        if not row:
            return {}

        raw_meta = row[3]
        metadata = _safe_json_object(raw_meta)
        return {
            "story_id": row[0],
            "cluster_id": row[1],
            "input_articles": _safe_json_list(row[2]),
            "synth_metadata": metadata,
            "living_story": metadata.get("living_story") if isinstance(metadata.get("living_story"), dict) else {},
            "publish": metadata.get("publish") if isinstance(metadata.get("publish"), dict) else {},
            "updated_at": row[4],
        }


def _extract_source_article_ids(input_articles: list[object]) -> list[int]:
    ids: list[int] = []
    for item in input_articles:
        if isinstance(item, dict):
            candidate = item.get("id")
            if str(candidate).isdigit():
                ids.append(int(str(candidate)))
        elif str(item).isdigit():
            ids.append(int(str(item)))
    deduped: list[int] = []
    seen: set[int] = set()
    for item_id in ids:
        if item_id in seen:
            continue
        seen.add(item_id)
        deduped.append(item_id)
    return deduped


def _source_bias_score(text: str) -> float:
    normalized = (text or "").lower()
    if not normalized.strip():
        return 0.0
    loaded_terms = [
        "obviously",
        "clearly",
        "must",
        "shocking",
        "outrage",
        "crisis",
        "extreme",
        "undeniable",
    ]
    certainty_terms = ["always", "never", "everyone", "no one", "proves", "without doubt"]
    hits = sum(normalized.count(term) for term in loaded_terms + certainty_terms)
    words = max(1, len(normalized.split()))
    return round(min(1.0, (hits / words) * 55.0), 4)


def _source_persuasion_score(text: str) -> float:
    normalized = (text or "").lower()
    if not normalized.strip():
        return 0.0
    persuasion_terms = [
        "should",
        "need to",
        "act now",
        "you must",
        "demand",
        "urge",
        "support",
        "oppose",
    ]
    hits = sum(normalized.count(term) for term in persuasion_terms)
    words = max(1, len(normalized.split()))
    return round(min(1.0, (hits / words) * 80.0), 4)


def _format_range(values: list[float]) -> str:
    if not values:
        return "N/A"
    return f"{sum(values)/len(values):.2f} avg ({min(values):.2f}–{max(values):.2f})"


def _compute_cluster_signals(story_context: dict[str, object]) -> dict[str, object]:
    input_articles = story_context.get("input_articles") if isinstance(story_context, dict) else []
    source_ids = _extract_source_article_ids(input_articles if isinstance(input_articles, list) else [])
    if not source_ids:
        return {
            "available": False,
            "cluster_size": 0,
            "source_sample_size": 0,
            "distinct_source_domains": 0,
            "date_start": None,
            "date_end": None,
            "sentiment_range": "N/A",
            "sentiment_balance": "N/A",
            "sentiment_distribution": {"positive": 0, "neutral": 0, "negative": 0},
            "sentiment_percent": {"positive": 0, "neutral": 0, "negative": 0},
            "bias_range": "N/A",
            "bias_high_share": "N/A",
            "bias_distribution": {"low": 0, "medium": 0, "high": 0},
            "bias_percent": {"low": 0, "medium": 0, "high": 0},
            "persuasion_range": "N/A",
            "persuasion_high_share": "N/A",
            "persuasion_distribution": {"low": 0, "medium": 0, "high": 0},
            "persuasion_percent": {"low": 0, "medium": 0, "high": 0},
        }

    placeholders = ",".join(["%s"] * len(source_ids))
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, source_url, publication_date, published_at, created_at,
                   sentiment_score, title, summary, content
            FROM articles
            WHERE id IN ({placeholders})
            """,
            source_ids,
        )
        columns = [col[0] for col in cursor.description]
        rows = [_cursor_row_to_dict(row, columns) for row in cursor.fetchall()]

    sentiment_scores: list[float] = []
    positive = 0
    neutral = 0
    negative = 0
    bias_scores: list[float] = []
    persuasion_scores: list[float] = []
    domains: set[str] = set()
    dates: list[datetime | date] = []

    for row in rows:
        sentiment = row.get("sentiment_score")
        if sentiment is not None:
            try:
                score = float(sentiment)
                sentiment_scores.append(score)
                if score >= 0.2:
                    positive += 1
                elif score <= -0.2:
                    negative += 1
                else:
                    neutral += 1
            except Exception:
                pass

        source_url = str(row.get("source_url") or "").strip()
        if source_url:
            host = urlparse(source_url).netloc.lower()
            if host.startswith("www."):
                host = host[4:]
            if host:
                domains.add(host)

        published_marker = row.get("publication_date") or row.get("published_at") or row.get("created_at")
        if isinstance(published_marker, (datetime, date)):
            dates.append(published_marker)

        source_text = " ".join(
            str(row.get(key) or "").strip()
            for key in ["title", "summary", "content"]
        ).strip()
        bias_scores.append(_source_bias_score(source_text))
        persuasion_scores.append(_source_persuasion_score(source_text))

    bias_high = sum(1 for value in bias_scores if value >= 0.25)
    persuasion_high = sum(1 for value in persuasion_scores if value >= 0.2)
    denominator = max(1, len(rows))

    sentiment_distribution = {
        "positive": positive,
        "neutral": neutral,
        "negative": negative,
    }
    sentiment_percent = {
        key: int(round((value / denominator) * 100))
        for key, value in sentiment_distribution.items()
    }

    bias_distribution = {
        "low": sum(1 for value in bias_scores if value < 0.15),
        "medium": sum(1 for value in bias_scores if 0.15 <= value < 0.35),
        "high": sum(1 for value in bias_scores if value >= 0.35),
    }
    bias_percent = {
        key: int(round((value / denominator) * 100))
        for key, value in bias_distribution.items()
    }

    persuasion_distribution = {
        "low": sum(1 for value in persuasion_scores if value < 0.12),
        "medium": sum(1 for value in persuasion_scores if 0.12 <= value < 0.28),
        "high": sum(1 for value in persuasion_scores if value >= 0.28),
    }
    persuasion_percent = {
        key: int(round((value / denominator) * 100))
        for key, value in persuasion_distribution.items()
    }

    return {
        "available": bool(rows),
        "cluster_size": len(source_ids),
        "source_sample_size": len(rows),
        "distinct_source_domains": len(domains),
        "date_start": min(dates) if dates else None,
        "date_end": max(dates) if dates else None,
        "sentiment_range": _format_range(sentiment_scores),
        "sentiment_balance": f"+{positive} / ~{neutral} / -{negative}" if sentiment_scores else "N/A",
        "sentiment_distribution": sentiment_distribution,
        "sentiment_percent": sentiment_percent,
        "bias_range": _format_range(bias_scores),
        "bias_high_share": f"{bias_high}/{denominator}",
        "bias_distribution": bias_distribution,
        "bias_percent": bias_percent,
        "persuasion_range": _format_range(persuasion_scores),
        "persuasion_high_share": f"{persuasion_high}/{denominator}",
        "persuasion_distribution": persuasion_distribution,
        "persuasion_percent": persuasion_percent,
    }


def _build_story_insights(story_context: dict[str, object], cluster_signals: dict[str, object]) -> dict[str, object]:
    if not story_context:
        return {
            "available": False,
            "story_type": "One-off",
        }

    living_story = story_context.get("living_story") if isinstance(story_context.get("living_story"), dict) else {}
    explainability = living_story.get("explainability") if isinstance(living_story.get("explainability"), dict) else {}
    last_diff = living_story.get("last_diff") if isinstance(living_story.get("last_diff"), dict) else {}
    reasons = explainability.get("reasons") if isinstance(explainability.get("reasons"), list) else []

    composite_score = living_story.get("last_composite_score")
    if composite_score is None:
        composite_score = last_diff.get("composite_score")

    return {
        "available": True,
        "story_id": story_context.get("story_id") or "N/A",
        "cluster_id": story_context.get("cluster_id") or "N/A",
        "story_type": "Living Story" if living_story else "One-off",
        "update_action": living_story.get("last_update_action") if living_story else "created",
        "revision": living_story.get("revision") if living_story else None,
        "last_new_articles": living_story.get("last_new_articles") if living_story else None,
        "meaningful_score": living_story.get("last_meaningful_score") if living_story else None,
        "composite_score": composite_score,
        "urgency_class": explainability.get("urgency_class") if explainability else None,
        "decision": explainability.get("decision") if explainability else None,
        "primary_reason": reasons[0] if reasons else None,
        "cluster_size": cluster_signals.get("cluster_size", 0),
        "date_start": cluster_signals.get("date_start"),
        "date_end": cluster_signals.get("date_end"),
    }


def home(request):
    featured_qs = Article.objects.filter(is_featured=True).order_by("-published_at")[:5]
    latest_qs = Article.objects.order_by("-published_at")[:12]
    featured = [_build_article_card(article) for article in featured_qs]
    latest = [_build_article_card(article) for article in latest_qs]

    return render(
        request,
        "news/home.html",
        {
            "featured": featured,
            "latest": latest,
        },
    )


def article_detail(request, slug):
    article = Article.objects.filter(slug=slug).first()
    if article is None:
        legacy = ArticleSlugRedirect.objects.select_related("article").filter(old_slug=slug).first()
        if legacy and legacy.article_id:
            return redirect("article_detail", slug=legacy.article.slug, permanent=True)
        raise Http404("Article not found")
    trust_label, trust_class = _trust_band(float(article.score or 0.0))
    evidence_links = _extract_source_links(article.evidence or "")
    narrative_signals = _derive_narrative_signals(article)

    latest_audit = (
        PublishAudit.objects.filter(article=article, status="success")
        .order_by("-created_at")
        .first()
    )
    story_context = _resolve_story_context(article, latest_audit)
    cluster_signals = _compute_cluster_signals(story_context)
    story_insights = _build_story_insights(story_context, cluster_signals)

    latest_news = list(
        Article.objects.exclude(id=article.id).order_by("-published_at")[:6]
    )
    seo_description = _seo_description(article, max_words=30)

    return render(
        request,
        "news/article_detail.html",
        {
            "article": article,
            "seo_description": seo_description,
            "trust_label": trust_label,
            "trust_class": trust_class,
            "read_time": _estimate_read_time(article.body or article.summary),
            "evidence_links": evidence_links,
            "narrative_signals": narrative_signals,
            "latest_news": latest_news,
            "latest_audit": latest_audit,
            "story_insights": story_insights,
            "cluster_signals": cluster_signals,
        },
    )


def archive(request):
    articles = [_build_article_card(article) for article in Article.objects.order_by("-published_at")]
    return render(
        request,
        "news/archive.html",
        {
            "articles": articles,
        },
    )


@csrf_exempt
def api_publish(request):
    """Simple API endpoint to receive published article payloads from editorial harness.

    Expects JSON payload with basic article fields. If `PUBLISHER_API_KEY` is set in
    environment / settings, the request must include header `X-API-KEY: <key>`.
    """
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    required_key = getattr(settings, "PUBLISHER_API_KEY", None)
    if required_key:
        provided = request.headers.get("X-API-KEY")
        if not provided or provided != required_key:
            return HttpResponseForbidden("invalid API key")

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "invalid_json"}, status=400)

    title = payload.get("title") or payload.get("article_id") or "untitled"
    slug = payload.get("slug") or title.lower().replace(" ", "-")
    summary = payload.get("summary", "")
    body = payload.get("body", "")
    author = payload.get("author", "Editorial Harness")
    score = float(payload.get("score", 0.0) or 0.0)
    evidence = payload.get("evidence", "")
    is_featured = bool(payload.get("is_featured", False))
    category = payload.get("category", "world")

    # persist article (simple create-or-ignore semantics)
    try:
        article, created = Article.objects.get_or_create(
            slug=slug,
            defaults={
                "title": title,
                "summary": summary,
                "body": body,
                "author": author,
                "score": score,
                "evidence": evidence,
                "is_featured": is_featured,
                "category": category,
            },
        )
        status = "success"
    except Exception:
        status = "failure"
        article = None

    # record audit
    try:
        PublishAudit.objects.create(
            article=article,
            status=status,
            actor=payload.get("actor", ""),
            token=payload.get("token", "") or "",
            latency_seconds=payload.get("latency_seconds", None),
            payload=payload,
        )
    except Exception:
        # best-effort
        pass

    # record prometheus metrics
    try:
        PUBLISHING_TOTAL.labels(result=status).inc()
        if payload.get("latency_seconds"):
            PUBLISHING_LATENCY_SECONDS.observe(float(payload.get("latency_seconds")))
    except Exception:
        pass

    if status == "success":
        return JsonResponse({"result": "ok", "slug": article.slug})
    return JsonResponse({"result": "error"}, status=500)


def api_metrics(request):
    """Return simple counts of publish audit statuses.

    Used by CI to verify a publish succeeded in sandbox.
    """
    data = {
        "success": PublishAudit.objects.filter(status="success").count(),
        "failure": PublishAudit.objects.filter(status="failure").count(),
        "skipped": PublishAudit.objects.filter(status="skipped").count(),
    }
    return JsonResponse(data)


def metrics_exporter(request):
    """Expose Prometheus metrics for scraping (publisher-specific counters)."""
    try:
        resp = generate_latest()
        from django.http import HttpResponse

        return HttpResponse(resp, content_type=CONTENT_TYPE_LATEST)
    except Exception:
        return JsonResponse({"error": "metrics_export_failed"}, status=500)


# Prometheus metrics for the publisher app — match Stage B metric names used elsewhere
PUBLISHING_TOTAL = Counter(
    "justnews_stage_b_publishing_total",
    "Count of publishing outcomes (success/failure) during Stage B flow.",
    ["result"],
)

PUBLISHING_LATENCY_SECONDS = Histogram(
    "justnews_stage_b_publishing_latency_seconds",
    "Latency of publishing operations in seconds.",
)


# BBC-style category views
def category_view(request, category):
    category_map = {
        "world": "World",
        "uk": "UK",
        "business": "Business",
        "politics": "Politics",
        "health": "Health",
        "science": "Science",
        "technology": "Technology",
        "entertainment": "Entertainment",
        "sport": "Sport",
    }
    cat_key = category.lower()
    cat_label = category_map.get(cat_key)
    if not cat_label:
        return render(
            request,
            "news/category.html",
            {
                "category": category,
                "articles": [],
                "invalid": True,
            },
        )
    articles = [
        _build_article_card(article)
        for article in Article.objects.filter(category=cat_key).order_by("-published_at")
    ]
    return render(
        request,
        "news/category.html",
        {
            "category": cat_label,
            "articles": articles,
            "invalid": False,
        },
    )


def robots_txt(request):
    sitemap_url = request.build_absolute_uri("/sitemap.xml")
    feed_url = request.build_absolute_uri("/feed.xml")
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin/",
            "Disallow: /api/",
            f"Sitemap: {sitemap_url}",
            f"Sitemap: {request.build_absolute_uri('/sitemap-static.xml')}",
            f"Sitemap: {request.build_absolute_uri('/sitemap-articles-1.xml')}",
            f"Feed: {feed_url}",
            "",
        ]
    )
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


SITEMAP_ARTICLE_PAGE_SIZE = 1000


def _category_map() -> dict[str, str]:
    return {
        "world": "World",
        "uk": "UK",
        "business": "Business",
        "politics": "Politics",
        "health": "Health",
        "science": "Science",
        "technology": "Technology",
        "entertainment": "Entertainment",
        "sport": "Sport",
    }


def _render_sitemap_urlset(entries: list[tuple[str, str | None, str | None, str | None]]) -> HttpResponse:
    chunks = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, lastmod, changefreq, priority in entries:
        chunks.append("  <url>")
        chunks.append(f"    <loc>{escape(loc)}</loc>")
        if lastmod:
            chunks.append(f"    <lastmod>{escape(lastmod)}</lastmod>")
        if changefreq:
            chunks.append(f"    <changefreq>{changefreq}</changefreq>")
        if priority:
            chunks.append(f"    <priority>{priority}</priority>")
        chunks.append("  </url>")
    chunks.append("</urlset>")
    return HttpResponse("\n".join(chunks), content_type="application/xml; charset=utf-8")


def _render_sitemap_index(entries: list[tuple[str, str | None]]) -> HttpResponse:
    chunks = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, lastmod in entries:
        chunks.append("  <sitemap>")
        chunks.append(f"    <loc>{escape(loc)}</loc>")
        if lastmod:
            chunks.append(f"    <lastmod>{escape(lastmod)}</lastmod>")
        chunks.append("  </sitemap>")
    chunks.append("</sitemapindex>")
    return HttpResponse("\n".join(chunks), content_type="application/xml; charset=utf-8")


def _article_sitemap_page_lastmod(page: int) -> str | None:
    if page < 1:
        return None
    offset = (page - 1) * SITEMAP_ARTICLE_PAGE_SIZE
    dt = (
        Article.objects.order_by("-updated_at")
        .values_list("updated_at", flat=True)[offset : offset + 1]
        .first()
    )
    return dt.isoformat() if dt else None


def sitemap_static_xml(request):
    base = request.build_absolute_uri("/").rstrip("/")
    latest_article = Article.objects.order_by("-updated_at").first()
    latest_ts = latest_article.updated_at.isoformat() if latest_article and latest_article.updated_at else None

    static_urls: list[tuple[str, str | None, str, str]] = [
        (f"{base}/", latest_ts, "hourly", "1.0"),
        (f"{base}/archive/", latest_ts, "daily", "0.7"),
    ]

    for slug, label in _category_map().items():
        category_latest = (
            Article.objects.filter(category=slug)
            .order_by("-updated_at")
            .values_list("updated_at", flat=True)
            .first()
        )
        category_lastmod = category_latest.isoformat() if category_latest else latest_ts
        static_urls.append(
            (
                f"{base}/{slug}/",
                category_lastmod,
                "hourly" if category_latest else "daily",
                "0.85" if category_latest else "0.6",
            )
        )

    return _render_sitemap_urlset(static_urls)


def sitemap_articles_xml(request, page):
    if page < 1:
        raise Http404("invalid sitemap page")

    base = request.build_absolute_uri("/").rstrip("/")
    offset = (page - 1) * SITEMAP_ARTICLE_PAGE_SIZE
    limit = offset + SITEMAP_ARTICLE_PAGE_SIZE

    articles = list(Article.objects.order_by("-updated_at")[offset:limit])
    if not articles and page != 1:
        raise Http404("sitemap page out of range")

    article_entries: list[tuple[str, str | None, str, str]] = []
    changefreq = "hourly" if page == 1 else "daily"
    priority = "1.0" if page == 1 else "0.85"
    for article in articles:
        loc = f"{base}/article/{article.slug}/"
        lastmod = article.updated_at.isoformat() if article.updated_at else None
        article_entries.append((loc, lastmod, changefreq, priority))

    return _render_sitemap_urlset(article_entries)


def sitemap_xml(request):
    base = request.build_absolute_uri("/").rstrip("/")
    latest_article = Article.objects.order_by("-updated_at").first()
    latest_ts = latest_article.updated_at.isoformat() if latest_article and latest_article.updated_at else None

    total_articles = Article.objects.count()
    total_pages = max(1, math.ceil(total_articles / SITEMAP_ARTICLE_PAGE_SIZE))

    entries: list[tuple[str, str | None]] = [
        (f"{base}/sitemap-static.xml", latest_ts),
    ]
    for page in range(1, total_pages + 1):
        entries.append((f"{base}/sitemap-articles-{page}.xml", _article_sitemap_page_lastmod(page)))

    return _render_sitemap_index(entries)


def feed_xml(request):
    base = request.build_absolute_uri("/").rstrip("/")
    site_url = f"{base}/"
    latest_articles = Article.objects.order_by("-published_at")[:100]
    last_build_date = None
    if latest_articles:
        latest_dt = latest_articles[0].updated_at or latest_articles[0].published_at
        if latest_dt:
            last_build_date = format_datetime(latest_dt)

    chunks = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "  <channel>",
        "    <title>JustNews</title>",
        f"    <link>{escape(site_url)}</link>",
        "    <description>Evidence-aware reporting with trust and narrative context.</description>",
        "    <language>en-gb</language>",
    ]
    if last_build_date:
        chunks.append(f"    <lastBuildDate>{escape(last_build_date)}</lastBuildDate>")

    for article in latest_articles:
        item_url = f"{base}/article/{article.slug}/"
        item_desc = _seo_description(article, max_words=40)
        pub_dt = article.published_at or article.updated_at
        pub_date = format_datetime(pub_dt) if pub_dt else None

        chunks.extend(
            [
                "    <item>",
                f"      <title>{escape(article.title)}</title>",
                f"      <link>{escape(item_url)}</link>",
                f"      <guid isPermaLink=\"true\">{escape(item_url)}</guid>",
                f"      <description>{escape(item_desc)}</description>",
            ]
        )
        if pub_date:
            chunks.append(f"      <pubDate>{escape(pub_date)}</pubDate>")
        if article.author:
            chunks.append(f"      <author>{escape(article.author)}</author>")
        chunks.append("    </item>")

    chunks.extend(["  </channel>", "</rss>"])
    return HttpResponse("\n".join(chunks), content_type="application/rss+xml; charset=utf-8")
