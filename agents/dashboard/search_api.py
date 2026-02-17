"""
Search API Module - JustNews Search Endpoints

This module provides REST API endpoints for semantic search functionality
using the migrated MariaDB + ChromaDB database system.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from common.observability import get_logger
from common.semantic_search_service import (
    SearchResponse,
    SearchResult,
)

logger = get_logger(__name__)


def get_search_service():
    """Compatibility wrapper that returns the active Search service.

    This exists to allow tests to monkeypatch `agents.dashboard.search_api.get_search_service`
    without depending on import-time binding to the implementation module.
    """
    from common.semantic_search_service import get_search_service as _get_search_service

    return _get_search_service()


# Create router for search endpoints
router = APIRouter(prefix="/api/search", tags=["search"])


class SearchQuery(BaseModel):
    """Search query request model"""

    query: str = Field(
        ..., description="Search query text", min_length=1, max_length=500
    )
    search_type: str = Field(
        "semantic", description="Type of search: semantic, text, or hybrid"
    )
    n_results: int = Field(10, description="Number of results to return", ge=1, le=100)
    min_score: float = Field(
        0.0, description="Minimum similarity score threshold", ge=0.0, le=1.0
    )


class SearchStats(BaseModel):
    """Search statistics response model"""

    total_articles: int
    total_sources: int
    total_vectors: int
    embedding_model: str
    embedding_dimensions: int


@router.post("/", response_model=SearchResponse)
async def search_articles(search_query: SearchQuery):
    """
    Perform semantic search across news articles

    This endpoint supports three types of search:
    - semantic: Vector similarity search using embeddings
    - text: Traditional text-based search in article content
    - hybrid: Combination of semantic and text search
    """
    try:
        service = get_search_service()

        response = service.search(
            query=search_query.query,
            n_results=search_query.n_results,
            search_type=search_query.search_type,
            min_score=search_query.min_score,
        )

        return response

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}") from e


@router.get("/semantic", response_model=SearchResponse)
async def semantic_search(
    q: str = Query(..., description="Search query", min_length=1, max_length=500),
    n: int = Query(10, description="Number of results", ge=1, le=100),
    min_score: float = Query(
        0.0, description="Minimum similarity score", ge=0.0, le=1.0
    ),
):
    """
    Perform semantic search using vector similarity

    GET endpoint for easy browser access and simple queries.
    """
    try:
        service = get_search_service()

        response = service.search(
            query=q, n_results=n, search_type="semantic", min_score=min_score
        )

        return response

    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Semantic search failed: {str(e)}"
        ) from e


@router.get("/text", response_model=SearchResponse)
async def text_search(
    q: str = Query(..., description="Search query", min_length=1, max_length=500),
    n: int = Query(10, description="Number of results", ge=1, le=100),
):
    """
    Perform text-based search in article content

    GET endpoint for traditional keyword-based search.
    """
    try:
        service = get_search_service()

        response = service.search(query=q, n_results=n, search_type="text")

        return response

    except Exception as e:
        logger.error(f"Text search failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Text search failed: {str(e)}"
        ) from e


@router.get("/hybrid", response_model=SearchResponse)
async def hybrid_search(
    q: str = Query(..., description="Search query", min_length=1, max_length=500),
    n: int = Query(10, description="Number of results", ge=1, le=100),
    min_score: float = Query(
        0.0, description="Minimum similarity score", ge=0.0, le=1.0
    ),
):
    """
    Perform hybrid search combining semantic and text approaches

    GET endpoint that combines vector similarity with keyword matching.
    """
    try:
        service = get_search_service()

        response = service.search(
            query=q, n_results=n, search_type="hybrid", min_score=min_score
        )

        return response

    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Hybrid search failed: {str(e)}"
        ) from e


@router.get("/similar/{article_id}", response_model=list[SearchResult])
async def find_similar_articles(
    article_id: int,
    n: int = Query(5, description="Number of similar articles", ge=1, le=20),
    min_score: float = Query(
        0.7, description="Minimum similarity score", ge=0.0, le=1.0
    ),
):
    """
    Find articles similar to a given article

    Uses the specified article as a reference to find semantically similar content.
    """
    try:
        service = get_search_service()

        similar_articles = service.get_similar_articles(
            article_id=article_id, n_results=n, min_score=min_score
        )

        return similar_articles

    except Exception as e:
        logger.error(f"Similar articles search failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Similar articles search failed: {str(e)}"
        ) from e


@router.get("/by-source/{source_id}", response_model=list[SearchResult])
async def search_articles_by_source(
    source_id: int, n: int = Query(10, description="Number of articles", ge=1, le=100)
):
    """
    Get articles from a specific news source

    Returns recent articles from the specified source.
    """
    try:
        service = get_search_service()

        articles = service.get_articles_by_source(source_id=source_id, limit=n)

        return articles

    except Exception as e:
        logger.error(f"Source search failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Source search failed: {str(e)}"
        ) from e


@router.get("/by-category/{category}", response_model=list[SearchResult])
async def search_articles_by_category(
    category: str, n: int = Query(10, description="Number of articles", ge=1, le=100)
):
    """
    Get articles by category or topic

    Searches for articles related to a specific topic or category.
    """
    try:
        service = get_search_service()

        articles = service.get_articles_by_category(category=category, n_results=n)

        return articles

    except Exception as e:
        logger.error(f"Category search failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Category search failed: {str(e)}"
        ) from e


@router.get("/recent", response_model=list[SearchResult])
async def get_recent_articles(
    q: str | None = Query(None, description="Optional search query to filter results"),
    n: int = Query(10, description="Number of articles", ge=1, le=100),
):
    """
    Get recent articles with optional search filtering

    Returns the most recent articles, optionally filtered by search query.
    """
    try:
        # Use runtime resolver so tests can monkeypatch `get_search_service`.
        service = get_search_service()
        articles = service.get_recent_articles_with_search(
            query=q,
            n_results=n,
        )

        return articles

    except Exception as e:
        logger.error(f"Recent articles search failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Recent articles search failed: {str(e)}"
        ) from e


@router.get("/stats", response_model=SearchStats)
async def get_search_statistics():
    """
    Get search system statistics

    Returns information about the search database and configuration.
    """
    try:
        from common.semantic_search_service import (
            get_search_service as _get_search_service,
        )

        service = _get_search_service()

        stats = service.get_search_statistics()

        return SearchStats(
            total_articles=stats.get("total_articles", 0),
            total_sources=stats.get("total_sources", 0),
            total_vectors=stats.get("total_vectors", 0),
            embedding_model=stats.get("embedding_model", "unknown"),
            embedding_dimensions=stats.get("embedding_dimensions", 384),
        )

    except Exception as e:
        logger.error(f"Failed to get search statistics: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get search statistics: {str(e)}"
        ) from e


@router.post("/clear-cache")
async def clear_search_cache():
    """
    Clear the search service cache

    This can help resolve issues with stale cached data.
    """
    try:
        from common.semantic_search_service import (
            get_search_service as _get_search_service,
        )

        service = _get_search_service()
        service.clear_cache()

        return {"message": "Search cache cleared successfully"}

    except Exception as e:
        logger.error(f"Failed to clear search cache: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to clear search cache: {str(e)}"
        ) from e


# Public API endpoints (if public API is enabled)
def include_public_api(app):
    """
    Include search endpoints in the public API

    This function is called when PUBLIC_API_AVAILABLE is True.
    """
    # Import here to avoid circular imports
    from fastapi import APIRouter
    from fastapi import Request as _FastAPIRequest
    from fastapi.middleware.cors import CORSMiddleware

    from .rate_limit import (
        rate_limiter_dependency,  # local import to avoid top-level dependency
    )

    def _rate_dep(request: _FastAPIRequest):
        return rate_limiter_dependency(request, max_requests=20, window_seconds=60)

    public_router = APIRouter(
        prefix="/api/public/search",
        tags=["public-search"],
        dependencies=[Depends(_rate_dep)],
    )

    @public_router.get("/semantic")
    async def public_semantic_search(
        q: str = Query(..., description="Search query", min_length=1, max_length=500),
        n: int = Query(5, description="Number of results", ge=1, le=20),
    ):
        """Public semantic search endpoint with rate limiting"""
        try:
            service = get_search_service()
            response = service.search(
                query=q,
                n_results=min(n, 20),  # Limit results for public API
                search_type="semantic",
                min_score=0.1,  # Higher threshold for public searches
            )

            # Return simplified response for public API
            return {
                "query": response.query,
                "total_results": response.total_results,
                "search_time": response.search_time,
                "results": [
                    {
                        "title": result.title,
                        "content": result.content[:300] + "..."
                        if len(result.content) > 300
                        else result.content,
                        "source_name": result.source_name,
                        "published_date": result.published_date,
                        "similarity_score": result.similarity_score,
                    }
                    for result in response.results
                ],
            }

        except Exception as e:
            logger.error(f"Public semantic search failed: {e}")
            raise HTTPException(
                status_code=500, detail="Search temporarily unavailable"
            ) from e

    @public_router.get("/recent")
    async def public_recent_articles(
        n: int = Query(10, description="Number of articles", ge=1, le=50),
    ):
        """Public recent articles endpoint"""
        try:
            service = get_search_service()
            articles = service.get_recent_articles_with_search(n_results=min(n, 50))

            return {
                "total_results": len(articles),
                "results": [
                    {
                        "title": article.title,
                        "content": article.content[:300] + "..."
                        if len(article.content) > 300
                        else article.content,
                        "source_name": article.source_name,
                        "published_date": article.published_date,
                    }
                    for article in articles
                ],
            }

        except Exception as e:
            logger.error(f"Public recent articles failed: {e}")
            raise HTTPException(
                status_code=500, detail="Recent articles temporarily unavailable"
            ) from e

    @public_router.get("/stats")
    async def public_search_stats():
        """Public search statistics endpoint"""
        try:
            service = get_search_service()
            stats = service.get_search_statistics()

            return {
                "total_articles": stats.get("total_articles", 0),
                "total_sources": stats.get("total_sources", 0),
                "last_updated": "recent",
            }

        except Exception as e:
            logger.error(f"Public stats failed: {e}")
            raise HTTPException(
                status_code=500, detail="Statistics temporarily unavailable"
            ) from e

    # Add CORS middleware for public endpoints
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    # NOTE: router inclusion is performed after all handlers are defined so
    # tests and dynamic imports can add handlers before inclusion. See below.

    @public_router.get("/articles")
    async def public_articles(
        n: int = Query(10, description="Number of articles", ge=1, le=50),
    ):
        """
        Public recent articles endpoint tailored for the published website.

        This returns a lightweight list of article summaries for rendering on the
        public site. It is intentionally a smaller, page-focused endpoint than
        the research-facing `/api/public/search/*` endpoints.
        """
        try:
            service = get_search_service()

            articles = service.get_recent_articles_with_search(n_results=min(n, 50))

            out = []
            for a in articles:
                # Support both `FakeArticle`-style objects (id/title/content)
                # and SearchResult dataclasses (article_id/title/content)
                art_id = getattr(a, "id", None) or getattr(a, "article_id", None)
                title = getattr(a, "title", "")
                content = getattr(a, "content", "")
                source = getattr(a, "source_name", None) or getattr(a, "source", None)
                published_date = getattr(a, "published_date", "")

                out.append(
                    {
                        "id": art_id,
                        "title": title,
                        "summary": (content[:300] + "...")
                        if len(content) > 300
                        else content,
                        "source": source,
                        "published_date": published_date,
                        "sentiment_score": getattr(a, "sentiment_score", 0),
                        "fact_check_score": getattr(a, "fact_check_score", None),
                        "url": getattr(a, "url", None),
                    }
                )

            return {"total_results": len(articles), "articles": out}

        except Exception as e:
            logger.error(f"Public articles endpoint failed: {e}")
            raise HTTPException(
                status_code=500, detail="Recent articles temporarily unavailable"
            ) from e

    # Include the public router after all public handlers are defined
    app.include_router(public_router)
    logger.info("Public search API endpoints registered")
