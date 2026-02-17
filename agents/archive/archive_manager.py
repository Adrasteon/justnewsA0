"""Archive manager implementation for the Archive agent."""

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from common.observability import get_logger

logger = get_logger(__name__)


class _StorageManager:
    """Simple file-backed storage for archived articles."""

    def __init__(self, storage_config: dict[str, Any]):
        storage_root = storage_config.get("local_path") or "./archive_storage"
        self.storage_path = Path(storage_root).expanduser().resolve()
        self.storage_path.mkdir(parents=True, exist_ok=True)

    async def store_article(self, article_data: dict[str, Any]) -> str:
        """Persist an article to disk and return its storage key."""
        storage_key = article_data.get("url_hash")
        if not storage_key:
            url = article_data.get("url", "")
            storage_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
            article_data["url_hash"] = storage_key

        file_path = self.storage_path / f"{storage_key}.json"
        await asyncio.to_thread(self._write_json, file_path, article_data)
        return storage_key

    async def retrieve_article(self, storage_key: str) -> dict[str, Any] | None:
        """Load an article by storage key."""
        file_path = self.storage_path / f"{storage_key}.json"
        if not file_path.exists():
            return None
        return await asyncio.to_thread(self._read_json, file_path)

    def _write_json(self, file_path: Path, payload: dict[str, Any]) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def _read_json(self, file_path: Path) -> dict[str, Any]:
        with file_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


class _MetadataIndex:
    """Very small in-process metadata search helper."""

    def __init__(self, storage_manager: _StorageManager):
        self._storage_manager = storage_manager

    async def search_articles(
        self, query: str, filters: dict[str, Any] | None
    ) -> list[str]:
        query = (query or "").strip().lower()
        filters = filters or {}
        if not query and not filters:
            return []

        def matches_filters(article: dict[str, Any]) -> bool:
            for key, expected in filters.items():
                if article.get(key) != expected:
                    return False
            return True

        matches: list[str] = []
        file_paths = list(self._storage_manager.storage_path.glob("*.json"))
        for file_path in file_paths:
            article = await asyncio.to_thread(
                self._storage_manager._read_json, file_path
            )
            if filters and not matches_filters(article):
                continue
            haystack = (
                f"{article.get('title', '')} {article.get('content', '')}".lower()
            )
            if query and query not in haystack:
                continue
            matches.append(file_path.stem)
        return matches


class ArchiveManager:
    """Facade that coordinates archive storage and metadata indexing."""

    def __init__(self, storage_config: dict[str, Any]):
        self.storage_manager = _StorageManager(storage_config)
        self.metadata_index = _MetadataIndex(self.storage_manager)
        logger.info(
            "ArchiveManager ready; storage path: %s", self.storage_manager.storage_path
        )

    async def archive_from_crawler(
        self, crawler_results: dict[str, Any]
    ) -> dict[str, Any]:
        articles = crawler_results.get("articles") or []
        storage_keys: list[str] = []
        for article in articles:
            storage_key = await self.storage_manager.store_article(article)
            storage_keys.append(storage_key)

        summary = {
            "stored_count": len(storage_keys),
            "storage_keys": storage_keys,
            "metadata": {
                "multi_site_crawl": crawler_results.get("multi_site_crawl", False),
                "sites_crawled": crawler_results.get("sites_crawled", 0),
                "total_articles": crawler_results.get("total_articles", len(articles)),
                "processing_time_seconds": crawler_results.get(
                    "processing_time_seconds", 0.0
                ),
                "articles_per_second": crawler_results.get("articles_per_second", 0.0),
            },
        }
        logger.info("Archived %d articles", len(storage_keys))
        return summary
