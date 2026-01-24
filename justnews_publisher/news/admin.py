from django.contrib import admin

from .models import Article


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "published_at", "score", "is_featured")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "author", "summary", "body")
    list_filter = ("is_featured", "published_at")
