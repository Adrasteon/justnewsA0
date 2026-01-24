from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("article/<slug:slug>/", views.article_detail, name="article_detail"),
    path("archive/", views.archive, name="archive"),
    # Publisher API endpoints (staging / CI harness)
    path("api/publish/", views.api_publish, name="api_publish"),
    path("api/metrics/", views.api_metrics, name="api_metrics"),
    path("metrics/", views.metrics_exporter, name="metrics_exporter"),
    # BBC-style category URLs (keep last so explicit API routes are matched first)
    path("<str:category>/", views.category_view, name="category_view"),
]
