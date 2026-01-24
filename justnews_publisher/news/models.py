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
