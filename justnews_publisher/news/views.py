import json
import math
import re
from email.utils import format_datetime
from html import escape

from django.conf import settings
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

    related_qs = (
        Article.objects.filter(category=article.category)
        .exclude(id=article.id)
        .order_by("-published_at")[:4]
    )
    related_cards = [_build_article_card(item) for item in related_qs]
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
            "related_cards": related_cards,
            "latest_audit": latest_audit,
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
    # Normalize category to match model choices
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
    cat_label = category_map.get(category.lower())
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
        for article in Article.objects.filter(category=cat_label).order_by("-published_at")
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
            Article.objects.filter(category=label)
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
