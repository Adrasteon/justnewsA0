"""
Semantic Search Service - MariaDB + ChromaDB Integration
Provides semantic search capabilities for the JustNews application

Features:
- Vector similarity search using ChromaDB
- Content retrieval from MariaDB
- Hybrid search combining semantic and text search
- Caching and performance optimization
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

try:
    from sentence_transformers import SentenceTransformer

    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except Exception:  # sentence-transformers may be missing or incompatible in CI/dev
    SentenceTransformer = None  # type: ignore
    _SENTENCE_TRANSFORMERS_AVAILABLE = False

from common.observability import get_logger
from database.utils.migrated_database_utils import (
    create_database_service,
    get_database_stats,
    get_db_config,
)

logger = get_logger(__name__)


@dataclass
class SearchResult:
    """Represents a single search result"""

    article_id: int
    title: str
    content: str
    source_name: str
    published_date: str
    similarity_score: float
    metadata: dict[str, Any]


@dataclass
class SearchResponse:
    """Represents the complete search response"""

    query: str
    results: list[SearchResult]
    total_results: int
    search_time: float
    search_type: str  # 'semantic', 'text', 'hybrid'


class SemanticSearchService:
    """
    Service for performing semantic search across the migrated database

    Combines vector similarity search (ChromaDB) with relational data retrieval (MariaDB)
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the semantic search service

        Args:
            config: Database configuration (uses get_db_config() if not provided)
        """
        self.config = config or get_db_config()
        self.db_service = create_database_service(self.config)

        # Initialize embedding model (best-effort). If sentence-transformers is
        # missing or incompatible, run in degraded mode and don't crash at import time.
        embedding_config = self.config.get("embedding", {})
        # If a test or higher scope has provided a patched `SentenceTransformer`
        # (i.e. module-level variable has been replaced), prefer that. Otherwise
        # attempt a runtime import. This keeps test mocking reliable and avoids
        # import-time failures when sentence-transformers is absent.
        st_cls = None
        if "SentenceTransformer" in globals() and SentenceTransformer is not None:
            st_cls = SentenceTransformer
        else:
            try:
                from sentence_transformers import (
                    SentenceTransformer as _ST,  # type: ignore
                )
            except Exception:
                _ST = None
            st_cls = _ST

        if st_cls is None:
            logger.debug(
                "sentence-transformers not available; SemanticSearchService running in degraded mode"
            )
            self.embedding_model = None
        else:
            try:
                self.embedding_model = st_cls(
                    embedding_config.get("model", "all-MiniLM-L6-v2")
                )
            except Exception as e:
                logger.warning(
                    "SentenceTransformer failed to initialize, running degraded: %s", e
                )
                self.embedding_model = None

        # Cache for frequently accessed articles
        self._article_cache = {}
        self._cache_max_size = 1000

        logger.info("SemanticSearchService initialized successfully")

    def search(
        self,
        query: str,
        n_results: int = 10,
        search_type: str = "semantic",
        min_score: float = 0.0,
    ) -> SearchResponse:
        """
        Perform search across the database

        Args:
            query: Search query
            n_results: Number of results to return
            search_type: Type of search ('semantic', 'text', 'hybrid')
            min_score: Minimum similarity score threshold

        Returns:
            SearchResponse with results and metadata
        """
        start_time = time.time()

        # Validate search_type and perform appropriate search. For unsupported
        # types we raise a ValueError (tests expect this behavior).
        if search_type == "semantic":
            results = self._semantic_search(query, n_results, min_score)
        elif search_type == "text":
            results = self._text_search(query, n_results)
        elif search_type == "hybrid":
            results = self._hybrid_search(query, n_results, min_score)
        else:
            logger.error(f"Search failed: Unsupported search type: {search_type}")
            raise ValueError(f"Unsupported search type: {search_type}")

        search_time = time.time() - start_time

        return SearchResponse(
            query=query,
            results=results,
            total_results=len(results),
            search_time=search_time,
            search_type=search_type,
        )

    def _semantic_search(
        self, query: str, n_results: int, min_score: float
    ) -> list[SearchResult]:
        """
        Perform semantic search using vector similarity

        Args:
            query: Search query
            n_results: Number of results to return
            min_score: Minimum similarity score

        Returns:
            List of SearchResult objects
        """
        # Generate embedding for the query — if embedding model unavailable,
        # we run in degraded mode and return an empty result set so unit tests
        # that only import this module won't fail during collection.
        if not getattr(self, "embedding_model", None):
            logger.warning("Embedding model not available - semantic search disabled")
            return []

        emb = self.embedding_model.encode(query)
        # Accept numpy arrays or plain lists from different embedding backends/mocks
        if hasattr(emb, "tolist"):
            query_embedding = emb.tolist()
        else:
            # Ensure a plain list
            query_embedding = list(emb)

        # Search in ChromaDB. Wrap in try/except so backend failures return
        # an empty result set instead of raising (tests expect graceful handling).
        try:
            if not getattr(self.db_service, "collection", None):
                logger.warning(
                    "ChromaDB collection not initialized - semantic search unavailable"
                )
                return []
            chroma_results = self.db_service.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results * 2,  # Get more results for filtering
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"Chroma query failed: {e}")
            return []

        results = []
        if chroma_results["ids"]:
            for i, article_id in enumerate(chroma_results["ids"][0]):
                distance = chroma_results["distances"][0][i]
                similarity_score = 1.0 - distance  # Convert distance to similarity

                if similarity_score < min_score:
                    continue

                # Get full article data from MariaDB
                article_data = self._get_article_by_id(int(article_id))
                if article_data:
                    # Handle publication_date conversion
                    pub_date = article_data.get("publication_date")
                    if pub_date is None:
                        pub_date_str = ""
                    elif isinstance(pub_date, str):
                        pub_date_str = pub_date
                    else:
                        # Assume it's a datetime object
                        pub_date_str = (
                            pub_date.isoformat()
                            if hasattr(pub_date, "isoformat")
                            else str(pub_date)
                        )

                    result = SearchResult(
                        article_id=int(article_id),
                        title=article_data.get("title", ""),
                        content=article_data.get("content", ""),
                        source_name=article_data.get("source_name", "Unknown Source"),
                        published_date=pub_date_str,
                        similarity_score=similarity_score,
                        metadata=chroma_results["metadatas"][0][i]
                        if chroma_results["metadatas"]
                        else {},
                    )
                    results.append(result)

                if len(results) >= n_results:
                    break

        return results

    def _text_search(self, query: str, n_results: int) -> list[SearchResult]:
        """
        Perform text-based search in MariaDB

        Args:
            query: Search query
            n_results: Number of results to return

        Returns:
            List of SearchResult objects
        """
        # Use the database service's text search method
        articles = self.db_service.search_articles_by_text(query, n_results)

        results = []
        for article in articles:
            # Handle publication_date conversion
            pub_date = article.get("publication_date")
            if pub_date is None:
                pub_date_str = ""
            elif isinstance(pub_date, str):
                pub_date_str = pub_date
            else:
                # Assume it's a datetime object
                pub_date_str = (
                    pub_date.isoformat()
                    if hasattr(pub_date, "isoformat")
                    else str(pub_date)
                )

            result = SearchResult(
                article_id=article["id"],
                title=article.get("title", ""),
                content=article.get("content", ""),
                source_name=article.get("source_name", "Unknown Source"),
                published_date=pub_date_str,
                similarity_score=1.0,  # Text search doesn't have similarity scores
                metadata={},
            )
            results.append(result)

        return results

    def _hybrid_search(
        self, query: str, n_results: int, min_score: float
    ) -> list[SearchResult]:
        """
        Perform hybrid search combining semantic and text search

        Args:
            query: Search query
            n_results: Number of results to return
            min_score: Minimum similarity score

        Returns:
            List of SearchResult objects
        """
        # Get semantic results
        semantic_results = self._semantic_search(query, n_results, min_score)

        # Get text results
        text_results = self._text_search(query, n_results)

        # Combine and deduplicate results
        combined_results = {}
        for result in semantic_results + text_results:
            if result.article_id not in combined_results:
                combined_results[result.article_id] = result
            else:
                # If article appears in both, keep the one with higher score
                existing = combined_results[result.article_id]
                if result.similarity_score > existing.similarity_score:
                    combined_results[result.article_id] = result

        # Sort by similarity score and return top results
        sorted_results = sorted(
            combined_results.values(), key=lambda x: x.similarity_score, reverse=True
        )

        return sorted_results[:n_results]

    def _get_article_by_id(self, article_id: int) -> dict[str, Any] | None:
        """
        Get article data by ID with caching

        Args:
            article_id: Article ID

        Returns:
            Article data dictionary or None if not found
        """
        try:
            cursor = self.db_service.mb_conn.cursor(dictionary=True)
            query = """
                SELECT a.id, a.title, a.content, a.publication_date,
                       COALESCE(s.name, 'Unknown Source') as source_name
                FROM articles a
                LEFT JOIN sources s ON a.source_id = s.id
                WHERE a.id = %s
            """
            cursor.execute(query, (article_id,))
            result = cursor.fetchone()
            cursor.close()

            return result

        except Exception as e:
            logger.error(f"Failed to get article {article_id}: {e}")
            return None

    def get_similar_articles(
        self, article_id: int, n_results: int = 5, min_score: float = 0.7
    ) -> list[SearchResult]:
        """
        Find articles similar to a given article

        Args:
            article_id: ID of the reference article
            n_results: Number of similar articles to return
            min_score: Minimum similarity score

        Returns:
            List of similar SearchResult objects
        """
        # Get the reference article
        ref_article = self._get_article_by_id(article_id)
        if not ref_article:
            return []

        # Use the article title and content as the search query
        query = f"{ref_article['title']} {ref_article['content'][:500]}"  # Limit content length

        # Perform semantic search
        results = self._semantic_search(query, n_results + 1, min_score)

        # Remove the reference article from results
        results = [r for r in results if r.article_id != article_id]

        return results[:n_results]

    def get_articles_by_category(
        self, category: str, n_results: int = 10
    ) -> list[SearchResult]:
        """
        Get articles by category/topic

        Args:
            category: Category or topic to search for
            n_results: Number of articles to return

        Returns:
            List of SearchResult objects
        """
        # For now, treat category as a search query
        # In the future, this could use category metadata from the database
        return self._semantic_search(category, n_results, 0.0)

    def get_recent_articles_with_search(
        self, query: str | None = None, n_results: int = 10
    ) -> list[SearchResult]:
        """
        Get recent articles, optionally filtered by search query

        Args:
            query: Optional search query to filter results
            n_results: Number of articles to return

        Returns:
            List of recent SearchResult objects
        """
        if query:
            # Use hybrid search for recent articles matching query
            return self._hybrid_search(query, n_results, 0.0)
        else:
            # Get recent articles without search
            articles = self.db_service.get_recent_articles(n_results)

            results = []
            for article in articles:
                # Handle publication_date conversion
                pub_date = article.get("publication_date")
                if pub_date is None:
                    pub_date_str = ""
                elif isinstance(pub_date, str):
                    pub_date_str = pub_date
                else:
                    # Assume it's a datetime object
                    pub_date_str = (
                        pub_date.isoformat()
                        if hasattr(pub_date, "isoformat")
                        else str(pub_date)
                    )

                result = SearchResult(
                    article_id=article["id"],
                    title=article.get("title", ""),
                    content=article.get("content", ""),
                    source_name=article.get("source_name", "Unknown Source"),
                    published_date=pub_date_str,
                    similarity_score=1.0,
                    metadata={},
                )
                results.append(result)

            return results

    def get_search_statistics(self) -> dict[str, Any]:
        """
        Get statistics about the search system

        Returns:
            Dictionary with search statistics
        """
        stats = get_database_stats(self.db_service)

        # Add search-specific stats
        stats.update(
            {
                "embedding_model": self.config.get("embedding", {}).get("model"),
                "embedding_dimensions": self.config.get("embedding", {}).get(
                    "dimensions", 384
                ),
                "cache_size": len(self._article_cache),
                "cache_max_size": self._cache_max_size,
            }
        )

        return stats

    def clear_cache(self):
        """Clear the article cache"""
        self._article_cache.clear()
        logger.info("Article cache cleared")


# Global service instance
_search_service_instance: SemanticSearchService | None = None


def get_search_service() -> SemanticSearchService:
    """
    Get the global semantic search service instance

    Returns:
        SemanticSearchService instance
    """
    global _search_service_instance
    if _search_service_instance is None:
        _search_service_instance = SemanticSearchService()
    return _search_service_instance


async def async_search(
    query: str,
    n_results: int = 10,
    search_type: str = "semantic",
    min_score: float = 0.0,
) -> SearchResponse:
    """
    Asynchronous search function

    Args:
        query: Search query
        n_results: Number of results to return
        search_type: Type of search ('semantic', 'text', 'hybrid')
        min_score: Minimum similarity score threshold

    Returns:
        SearchResponse with results and metadata
    """
    loop = asyncio.get_event_loop()
    service = get_search_service()

    return await loop.run_in_executor(
        None, service.search, query, n_results, search_type, min_score
    )
