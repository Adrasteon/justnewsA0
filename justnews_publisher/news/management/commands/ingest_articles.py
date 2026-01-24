import json
import os

from django.core.management.base import BaseCommand

from news.models import Article


class Command(BaseCommand):
    help = "Ingest articles released by Chief Editor from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "json_path", type=str, help="Path to JSON file containing articles"
        )

    def handle(self, *args, **options):
        json_path = options["json_path"]
        if not os.path.exists(json_path):
            self.stdout.write(self.style.ERROR(f"File not found: {json_path}"))
            return
        with open(json_path) as f:
            articles = json.load(f)
        count = 0
        for data in articles:
            article, created = Article.objects.get_or_create(
                slug=data["slug"],
                defaults={
                    "title": data["title"],
                    "summary": data["summary"],
                    "body": data["body"],
                    "author": data["author"],
                    "score": data.get("score", 0.0),
                    "evidence": data.get("evidence", ""),
                    "is_featured": data.get("is_featured", False),
                },
            )
            if created:
                count += 1
        self.stdout.write(self.style.SUCCESS(f"Ingested {count} new articles."))
