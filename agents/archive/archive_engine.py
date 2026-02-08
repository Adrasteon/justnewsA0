"""
Archive Engine for JustNews

Core business logic for comprehensive article archiving with knowledge graph integration.
Provides research-scale archiving capabilities with complete provenance tracking,
entity linking, and temporal knowledge graphs.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from agents.archive.archive_manager import ArchiveManager
from agents.archive.entity_linker import EntityLinkerManager
from agents.archive.knowledge_graph import KnowledgeGraphManager
from common.observability import get_logger

logger = get_logger(__name__)


class ArchiveEngine:
    """
    Core archive engine providing comprehensive article archiving capabilities.

    Features:
    - Multi-backend storage (local, S3)
    - Knowledge graph integration with entity linking
    - Metadata indexing and search
    - Temporal relationship tracking
    - Research-scale provenance tracking
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the archive engine.

        Args:
            config: Configuration dictionary with storage and KG settings
        """
        self.config = config or self._get_default_config()
        self.logger = get_logger(__name__)

        # Initialize core components
        self._init_storage_manager()
        self._init_knowledge_graph()
        self._init_entity_linker()

        self.logger.info("🚀 Archive Engine initialized successfully")

    def _get_default_config(self) -> dict[str, Any]:
        """Get default configuration for archive engine."""
        return {
            "storage": {
                "type": "local",
                "local_path": "./archive_storage",
                "kg_storage_path": "./kg_storage",
                "entity_cache_path": "./entity_cache",
            },
            "knowledge_graph": {
                "enabled": True,
                "temporal_tracking": True,
                "entity_linking": True,
            },
            "entity_linking": {
                "enabled": True,
                "external_kbs": ["wikidata"],
                "cache_enabled": True,
            },
        }

    def _init_storage_manager(self):
        """Initialize the archive storage manager."""
        storage_config = self.config.get("storage", {})
        self.archive_manager = ArchiveManager(storage_config)
        self.logger.info("Archive storage manager initialized")

    def _init_knowledge_graph(self):
        """Initialize the knowledge graph manager."""
        kg_config = self.config.get("knowledge_graph", {})
        if kg_config.get("enabled", True):
            kg_storage_path = self.config["storage"]["kg_storage_path"]
            backend = kg_config.get("backend") or os.environ.get("KG_BACKEND", "db")
            # Default to DB-backed KG for production + scalability
            self.kg_manager = KnowledgeGraphManager(
                kg_storage_path=kg_storage_path, backend=backend
            )
            self.logger.info("Knowledge graph manager initialized")
        else:
            self.kg_manager = None

    def _init_entity_linker(self):
        """Initialize the entity linker manager."""
        el_config = self.config.get("entity_linking", {})
        if el_config.get("enabled", True) and self.kg_manager:
            cache_path = self.config["storage"]["entity_cache_path"]
            self.entity_linker = EntityLinkerManager(
                self.kg_manager, cache_dir=cache_path
            )
            self.logger.info("Entity linker manager initialized")
        else:
            self.entity_linker = None

    async def archive_articles(self, crawler_results: dict[str, Any]) -> dict[str, Any]:
        """
        Archive articles from crawler results with full KG integration.

        Args:
            crawler_results: Crawler results containing articles and metadata

        Returns:
            Archive summary with statistics and storage keys
        """
        try:
            self.logger.info(
                f"Archiving {len(crawler_results.get('articles', []))} articles"
            )

            # Archive articles using the manager
            archive_summary = await self.archive_manager.archive_from_crawler(
                crawler_results
            )

            # Enhance with knowledge graph if enabled
            if self.kg_manager and crawler_results.get("articles"):
                await self._enhance_with_knowledge_graph(crawler_results["articles"])

            # Add entity linking if enabled
            if self.entity_linker and crawler_results.get("articles"):
                await self._link_entities(crawler_results["articles"])

            self.logger.info("Articles archived successfully with KG integration")
            return archive_summary

        except Exception as e:
            self.logger.error(f"Error archiving articles: {e}")
            raise

    async def _enhance_with_knowledge_graph(self, articles: list[dict[str, Any]]):
        """Enhance articles with knowledge graph relationships."""
        try:
            for article in articles:
                # Extract entities and relationships
                entities = await self.kg_manager.extract_entities(article)
                relationships = await self.kg_manager.extract_relationships(
                    article, entities
                )

                # Store in knowledge graph
                await self.kg_manager.store_article_entities(
                    article, entities, relationships
                )

            self.logger.debug("Knowledge graph enhancement completed")

        except Exception as e:
            self.logger.warning(f"Knowledge graph enhancement failed: {e}")

    async def _link_entities(self, articles: list[dict[str, Any]]):
        """Link entities to external knowledge bases."""
        try:
            for article in articles:
                # Link entities using external knowledge bases
                linked_entities = await self.entity_linker.link_entities(article)
                article["linked_entities"] = linked_entities

            self.logger.debug("Entity linking completed")

        except Exception as e:
            self.logger.warning(f"Entity linking failed: {e}")

    async def retrieve_article(self, storage_key: str) -> dict[str, Any] | None:
        """
        Retrieve archived article by storage key.

        Args:
            storage_key: Unique storage key for the article

        Returns:
            Article data or None if not found
        """
        try:
            article_data = await self.archive_manager.storage_manager.retrieve_article(
                storage_key
            )

            if article_data and self.kg_manager:
                # Enhance with knowledge graph data
                kg_data = await self.kg_manager.get_article_entities(storage_key)
                if kg_data:
                    article_data["knowledge_graph"] = kg_data

            return article_data

        except Exception as e:
            self.logger.error(f"Error retrieving article {storage_key}: {e}")
            raise

    async def search_archive(
        self, query: str, filters: dict[str, Any] | None = None
    ) -> list[str]:
        """
        Search archived articles by metadata and content.

        Args:
            query: Search query string
            filters: Optional metadata filters

        Returns:
            List of matching storage keys
        """
        try:
            filters = filters or {}

            # Search using metadata index
            storage_keys = await self.archive_manager.metadata_index.search_articles(
                query, filters
            )

            # Enhance search with knowledge graph if available
            if self.kg_manager and not storage_keys:
                kg_results = await self.kg_manager.search_entities(query)
                if kg_results:
                    storage_keys.extend([r["storage_key"] for r in kg_results])

            return list(set(storage_keys))  # Remove duplicates

        except Exception as e:
            self.logger.error(f"Error searching archive: {e}")
            raise

    async def store_single_article(self, article_data: dict[str, Any]) -> str:
        """
        Store a single article with complete metadata.

        Args:
            article_data: Complete article data dictionary

        Returns:
            Storage key for the archived article
        """
        try:
            # Validate required fields
            required_fields = ["url", "title", "content", "domain"]
            for field in required_fields:
                if field not in article_data:
                    raise ValueError(f"Missing required field: {field}")

            # Set defaults for optional fields
            article_data.setdefault("timestamp", datetime.now().isoformat())
            article_data.setdefault("extraction_method", "generic_dom")
            article_data.setdefault("status", "success")
            article_data.setdefault("confidence", 0.8)
            article_data.setdefault("news_score", 0.7)

            # Store the article
            storage_key = await self.archive_manager.storage_manager.store_article(
                article_data
            )

            # Enhance with KG and entity linking
            if self.kg_manager:
                entities = await self.kg_manager.extract_entities(article_data)
                relationships = await self.kg_manager.extract_relationships(
                    article_data, entities
                )
                await self.kg_manager.store_article_entities(
                    article_data, entities, relationships
                )

            if self.entity_linker:
                linked_entities = await self.entity_linker.link_entities(article_data)
                article_data["linked_entities"] = linked_entities

            self.logger.info(f"Stored single article: {article_data['title'][:50]}...")
            return storage_key

        except Exception as e:
            self.logger.error(f"Error storing single article: {e}")
            raise

    def get_archive_stats(self) -> dict[str, Any]:
        """
        Get comprehensive archive statistics.

        Returns:
            Dictionary with archive statistics
        """
        try:
            # Get storage statistics
            storage_path = Path(self.config["storage"]["local_path"])
            total_files = 0
            total_size = 0

            if storage_path.exists():
                for file_path in storage_path.rglob("*"):
                    if file_path.is_file():
                        total_files += 1
                        total_size += file_path.stat().st_size

            # Get Knowledge Graph statistics
            kg_stats = {}
            if self.kg_manager and hasattr(self.kg_manager, "get_statistics"):
                kg_stats = self.kg_manager.get_statistics()

            # Get entity linking statistics
            el_stats = {}
            if self.entity_linker and hasattr(self.entity_linker, "get_statistics"):
                el_stats = self.entity_linker.get_statistics()

            stats = {
                "storage_type": self.config["storage"]["type"],
                "total_archived_articles": total_files,
                "total_storage_size_bytes": total_size,
                "total_storage_size_mb": round(total_size / (1024 * 1024), 2),
                "storage_path": str(storage_path.absolute()),
                "knowledge_graph_enabled": self.kg_manager is not None,
                "knowledge_graph_stats": kg_stats,
                "entity_linking_enabled": self.entity_linker is not None,
                "entity_linking_stats": el_stats,
                "archive_manager_initialized": True,
                "phase3_integration": True,
                "timestamp": datetime.now().isoformat(),
            }

            return stats

        except Exception as e:
            self.logger.error(f"Error getting archive stats: {e}")
            raise

    async def health_check(self) -> dict[str, Any]:
        """
        Perform comprehensive health check of archive engine.

        Returns:
            Health status dictionary
        """
        try:
            health = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "components": {},
            }

            # Check storage manager
            try:
                storage_stats = self.get_archive_stats()
                health["components"]["storage"] = {
                    "status": "healthy",
                    "articles_count": storage_stats.get("total_archived_articles", 0),
                }
            except Exception as e:
                health["components"]["storage"] = {
                    "status": "unhealthy",
                    "error": str(e),
                }
                health["status"] = "degraded"

            # Check knowledge graph
            if self.kg_manager:
                try:
                    kg_health = await self.kg_manager.health_check()
                    health["components"]["knowledge_graph"] = kg_health
                except Exception as e:
                    health["components"]["knowledge_graph"] = {
                        "status": "unhealthy",
                        "error": str(e),
                    }
                    health["status"] = "degraded"
            else:
                health["components"]["knowledge_graph"] = {"status": "disabled"}

            # Check entity linker
            if self.entity_linker:
                try:
                    el_health = await self.entity_linker.health_check()
                    health["components"]["entity_linker"] = el_health
                except Exception as e:
                    health["components"]["entity_linker"] = {
                        "status": "unhealthy",
                        "error": str(e),
                    }
                    health["status"] = "degraded"
            else:
                health["components"]["entity_linker"] = {"status": "disabled"}

            return health

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# Global engine instance
_archive_engine = None


def get_archive_engine() -> ArchiveEngine:
    """Get or create the global archive engine instance."""
    global _archive_engine
    if _archive_engine is None:
        _archive_engine = ArchiveEngine()
    return _archive_engine
