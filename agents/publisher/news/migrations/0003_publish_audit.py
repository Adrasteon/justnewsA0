from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0002_article_category"),
    ]

    operations = [
        migrations.CreateModel(
            name="PublishAudit",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("success", "success"),
                            ("failure", "failure"),
                            ("skipped", "skipped"),
                        ],
                        max_length=20,
                    ),
                ),
                ("actor", models.CharField(default="", max_length=200, blank=True)),
                ("token", models.CharField(default="", max_length=256, blank=True)),
                ("latency_seconds", models.FloatField(blank=True, null=True)),
                ("payload", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "article",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        to="news.article",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
