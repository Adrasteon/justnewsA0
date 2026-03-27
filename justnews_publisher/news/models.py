import uuid

from django.db import models


class Article(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    summary = models.TextField()
    body = models.TextField()
    published_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    author = models.CharField(max_length=100)
    score = models.FloatField(help_text="Editorial score (accuracy, trust)")
    evidence = models.TextField(help_text="Supporting evidence, sources, fact-checks")
    is_featured = models.BooleanField(default=False)
    CATEGORY_CHOICES = [
        ("world", "World"),
        ("uk", "UK"),
        ("business", "Business"),
        ("politics", "Politics"),
        ("health", "Health"),
        ("science", "Science"),
        ("technology", "Tech"),
        ("entertainment", "Entertainment"),
        ("sport", "Sport"),
    ]
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default="world"
    )

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.title


class ArticleSlugRedirect(models.Model):
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="slug_redirects",
    )
    old_slug = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.old_slug} -> {self.article.slug}"


class PublishAudit(models.Model):
    """A record of publishing attempts made against this publisher instance.

    Stores the editorial harness payload, outcome and the approval token used
    (if any). This is intentionally simple for staging and audit checks.
    """

    article = models.ForeignKey(
        Article, null=True, blank=True, on_delete=models.SET_NULL
    )
    status = models.CharField(
        max_length=20,
        choices=(
            ("success", "success"),
            ("failure", "failure"),
            ("skipped", "skipped"),
        ),
    )
    actor = models.CharField(max_length=200, blank=True, default="")
    token = models.CharField(max_length=256, blank=True, default="")
    latency_seconds = models.FloatField(null=True, blank=True)
    payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PublishAudit({self.status}, {self.actor}, {self.created_at})"


# Create your models here.

class BackendArticle(models.Model):
    """
    Refers to the 'articles' table created by 'database/migrations/*.sql'
    Used by the Backend Agents (Crawler/Analyst).
    Mapped here for Foreign Key relationships with Living Stories.
    """
    id = models.AutoField(primary_key=True)

    class Meta:
        managed = False
        db_table = 'articles'

class LivingStory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    semantic_centroid = models.JSONField(null=True, blank=True)
    STATUS_CHOICES = [
        ("active", "Active"),
        ("dormant", "Dormant"),
        ("archived", "Archived"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "living_stories"

class StoryUpdate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    story = models.ForeignKey(LivingStory, on_delete=models.CASCADE, related_name="updates")
    article_ids = models.JSONField(help_text="List of BackendArticle IDs in this batch")
    article_count = models.IntegerField(default=0)
    batch_centroid = models.JSONField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "story_updates"

class PendingArticle(models.Model):
    backend_article = models.OneToOneField(BackendArticle, on_delete=models.CASCADE, db_column='article_id', related_name='pending_status', primary_key=True)
    source_domain = models.CharField(max_length=255)
    vector_blob = models.JSONField()
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pending_articles_pool"
