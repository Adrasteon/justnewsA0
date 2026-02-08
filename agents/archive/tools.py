"""
Archive Tools for JustNews

Wrapper functions for archive operations that can be called by other agents
via the MCP protocol. Provides clean interfaces to archive functionality.
"""

from typing import Any

from agents.archive import ingest_pipeline
from agents.archive.archive_engine import get_archive_engine
from common.observability import get_logger

logger = get_logger(__name__)

# Get archive engine instance
archive_engine = get_archive_engine()


def queue_article(job_payload: dict[str, Any]) -> dict[str, Any]:
    """Expose the Stage 2 ingest helper via the archive tool surface."""

    try:
        return ingest_pipeline.queue_article(job_payload)
    except Exception as exc:
        logger.error(f"Error queueing article via archive tools: {exc}")
        raise


async def archive_articles(
    multi_site_crawl: bool = False,
    sites_crawled: int = 0,
    total_articles: int = 0,
    processing_time_seconds: float = 0.0,
    articles_per_second: float = 0.0,
    articles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Archive articles from crawler results.

    Args:
        multi_site_crawl: Whether this was a multi-site crawl
        sites_crawled: Number of sites crawled
        total_articles: Total number of articles
        processing_time_seconds: Processing time in seconds
        articles_per_second: Articles processed per second
        articles: List of article data dictionaries

    Returns:
        Archive operation results
    """
    try:
        crawler_results = {
            "multi_site_crawl": multi_site_crawl,
            "sites_crawled": sites_crawled,
            "total_articles": total_articles,
            "processing_time_seconds": processing_time_seconds,
            "articles_per_second": articles_per_second,
            "articles": articles or [],
        }

        result = await archive_engine.archive_articles(crawler_results)
        logger.info(f"Archived {len(articles or [])} articles successfully")
        return result

    except Exception as e:
        logger.error(f"Error in archive_articles: {e}")
        raise


async def retrieve_article(storage_key: str) -> dict[str, Any] | None:
    """
    Retrieve an archived article by storage key.

    Args:
        storage_key: Unique storage key for the article

    Returns:
        Article data dictionary or None if not found
    """
    try:
        article = await archive_engine.retrieve_article(storage_key)
        if article:
            logger.info(f"Retrieved article: {storage_key}")
        else:
            logger.warning(f"Article not found: {storage_key}")
        return article

    except Exception as e:
        logger.error(f"Error retrieving article {storage_key}: {e}")
        raise


async def search_archive(
    query: str, filters: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Search archived articles by query and filters.

    Args:
        query: Search query string
        filters: Optional metadata filters

    Returns:
        Search results with matching storage keys
    """
    try:
        storage_keys = await archive_engine.search_archive(query, filters)

        result = {
            "query": query,
            "results": storage_keys,
            "count": len(storage_keys),
            "filters_applied": filters or {},
        }

        logger.info(f"Search '{query}' returned {len(storage_keys)} results")
        return result

    except Exception as e:
        logger.error(f"Error searching archive: {e}")
        raise


def get_archive_stats() -> dict[str, Any]:
    """
    Get comprehensive archive statistics.

    Returns:
        Archive statistics dictionary
    """
    try:
        stats = archive_engine.get_archive_stats()
        logger.info(
            f"Retrieved archive stats: {stats.get('total_archived_articles', 0)} articles"
        )
        return stats

    except Exception as e:
        logger.error(f"Error getting archive stats: {e}")
        raise


async def store_single_article(
    url: str,
    title: str,
    content: str,
    domain: str,
    url_hash: str | None = None,
    extraction_method: str = "generic_dom",
    status: str = "success",
    crawl_mode: str = "generic_site",
    canonical: str | None = None,
    paywall_flag: bool = False,
    confidence: float = 0.8,
    publisher_meta: dict[str, Any] | None = None,
    news_score: float = 0.7,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """
    Store a single article with complete metadata.

    Args:
        url: Article URL
        title: Article title
        content: Article content
        domain: Source domain
        url_hash: Optional URL hash
        extraction_method: Content extraction method
        status: Processing status
        crawl_mode: Crawl mode used
        canonical: Canonical URL
        paywall_flag: Whether article is behind paywall
        confidence: Extraction confidence score
        publisher_meta: Publisher metadata
        news_score: News quality score
        timestamp: Article timestamp

    Returns:
        Storage result with storage key
    """
    try:
        article_data = {
            "url": url,
            "title": title,
            "content": content,
            "domain": domain,
            "url_hash": url_hash or "",
            "extraction_method": extraction_method,
            "status": status,
            "crawl_mode": crawl_mode,
            "canonical": canonical or url,
            "paywall_flag": paywall_flag,
            "confidence": confidence,
            "publisher_meta": publisher_meta or {},
            "news_score": news_score,
            "timestamp": timestamp,
        }

        storage_key = await archive_engine.store_single_article(article_data)

        result = {
            "storage_key": storage_key,
            "article_title": title,
            "status": "success",
        }

        logger.info(f"Stored single article: {title[:50]}...")
        return result

    except Exception as e:
        logger.error(f"Error storing single article: {e}")
        raise


async def get_article_entities(storage_key: str) -> dict[str, Any] | None:
    """
    Get knowledge graph entities for an article.

    Args:
        storage_key: Article storage key

    Returns:
        Entity data or None if not available
    """
    try:
        if (
            not hasattr(archive_engine, "kg_manager")
            or archive_engine.kg_manager is None
        ):
            return None

        entities = await archive_engine.kg_manager.get_article_entities(storage_key)
        logger.debug(f"Retrieved entities for article {storage_key}")
        return entities

    except Exception as e:
        logger.error(f"Error getting article entities for {storage_key}: {e}")
        raise


async def search_knowledge_graph(query: str) -> list[dict[str, Any]]:
    """
    Search the knowledge graph for entities and relationships.

    Args:
        query: Search query

    Returns:
        List of matching entities and relationships
    """
    try:
        if (
            not hasattr(archive_engine, "kg_manager")
            or archive_engine.kg_manager is None
        ):
            return []

        results = await archive_engine.kg_manager.search_entities(query)
        logger.info(f"Knowledge graph search '{query}' returned {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"Error searching knowledge graph: {e}")
        raise


async def link_entities(article_data: dict[str, Any]) -> dict[str, Any]:
    """
    Link article entities to external knowledge bases.

    Args:
        article_data: Article data dictionary

    Returns:
        Linked entity data
    """
    try:
        if (
            not hasattr(archive_engine, "entity_linker")
            or archive_engine.entity_linker is None
        ):
            return {"linked_entities": []}

        linked_entities = await archive_engine.entity_linker.link_entities(article_data)

        result = {
            "linked_entities": linked_entities,
            "article_url": article_data.get("url"),
            "linking_timestamp": archive_engine.config.get("timestamp"),
        }

        logger.debug(f"Linked {len(linked_entities)} entities for article")
        return result

    except Exception as e:
        logger.error(f"Error linking entities: {e}")
        raise
