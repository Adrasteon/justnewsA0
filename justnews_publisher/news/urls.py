from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path("sitemap.xml", views.sitemap_xml, name="sitemap_xml"),
    path("sitemap-static.xml", views.sitemap_static_xml, name="sitemap_static_xml"),
    path("sitemap-articles-<int:page>.xml", views.sitemap_articles_xml, name="sitemap_articles_xml"),
    path("feed.xml", views.feed_xml, name="feed_xml"),
    path("article/<slug:slug>/", views.article_detail, name="article_detail"),
    path("archive/", views.archive, name="archive"),
    # Publisher API endpoints (staging / CI harness)
    path("api/publish/", views.api_publish, name="api_publish"),
    path("api/metrics/", views.api_metrics, name="api_metrics"),
    path("metrics/", views.metrics_exporter, name="metrics_exporter"),
    # BBC-style category URLs (keep last so explicit API routes are matched first)
    path("<str:category>/", views.category_view, name="category_view"),
]
