import json

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .models import Article, PublishAudit


def home(request):
    featured = Article.objects.filter(is_featured=True).order_by("-published_at")[:5]
    latest = Article.objects.order_by("-published_at")[:10]
    return render(
        request,
        "news/home.html",
        {
            "featured": featured,
            "latest": latest,
        },
    )


def article_detail(request, slug):
    article = get_object_or_404(Article, slug=slug)
    return render(
        request,
        "news/article_detail.html",
        {
            "article": article,
        },
    )


def archive(request):
    articles = Article.objects.order_by("-published_at")
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
    articles = Article.objects.filter(category=cat_label).order_by("-published_at")
    return render(
        request,
        "news/category.html",
        {
            "category": cat_label,
            "articles": articles,
            "invalid": False,
        },
    )
