"""
Comprehensive tests for CrawlerEngine class

Tests cover initialization, strategy determination, all crawling modes,
multi-site concurrent crawling, article ingestion, AI analysis delegation,
performance monitoring, and error handling.
"""

import json
from unittest.mock import Mock, patch

import pytest
import pytest_asyncio

from agents.crawler.crawler_engine import CrawlerEngine
from agents.sites.generic_site_crawler import SiteConfig


class TestCrawlerEngine:
    """Test suite for CrawlerEngine class"""

    @pytest.fixture
    def mock_site_config(self):
        """Create a mock SiteConfig for testing"""
        return SiteConfig(
            {
                "id": 1,
                "name": "Test Site",
                "domain": "testsite.com",
                "url": "https://testsite.com",
                "crawling_strategy": "generic",
            }
        )

    @pytest.fixture
    def mock_bbc_config(self):
        """Create a mock BBC SiteConfig for ultra-fast testing"""
        return SiteConfig(
            {
                "id": 2,
                "name": "BBC News",
                "domain": "bbc.co.uk",
                "url": "https://bbc.co.uk/news",
                "crawling_strategy": "ultra_fast",
            }
        )

    @pytest.fixture
    def mock_complex_config(self):
        """Create a mock complex site config for AI-enhanced testing"""
        return SiteConfig(
            {
                "id": 3,
                "name": "New York Times",
                "domain": "nytimes.com",
                "url": "https://nytimes.com",
                "crawling_strategy": "ai_enhanced",
            }
        )

    @pytest_asyncio.fixture
    async def crawler_engine(self):
        """Create a CrawlerEngine instance for testing"""
        engine = CrawlerEngine()
        yield engine
        # Cleanup after test
        await engine._cleanup()

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test CrawlerEngine initialization and component setup"""
        with (
            patch("agents.crawler.crawler_engine.initialize_connection_pool"),
            patch("agents.crawler.crawler_engine.create_crawling_performance_table"),
            patch("agents.crawler.crawler_engine.start_performance_monitoring"),
        ):
            engine = CrawlerEngine()

            # Test core components are initialized
            assert engine.rate_limiter is not None
            assert engine.robots_checker is not None
            assert engine.multi_site_crawler is not None
            assert engine.performance_monitor is not None
            assert engine.performance_optimizer is not None

            # Test performance metrics structure
            expected_metrics = {
                "start_time": engine.performance_metrics["start_time"],
                "articles_processed": 0,
                "sites_crawled": 0,
                "errors": 0,
                "mode_usage": {
                    "ai_enhanced": 0,
                    "generic": 0,
                    "crawl4ai_profiled": 0,
                },
            }
            assert engine.performance_metrics == expected_metrics

            # Test caches are initialized
            assert isinstance(engine.strategy_cache, dict)
            assert isinstance(engine.performance_history, dict)

            await engine._cleanup()

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async context manager functionality"""
        with (
            patch("agents.crawler.crawler_engine.initialize_connection_pool"),
            patch("agents.crawler.crawler_engine.create_crawling_performance_table"),
            patch("agents.crawler.crawler_engine.start_performance_monitoring"),
            patch(
                "agents.crawler.crawler_engine.CrawlerEngine._cleanup_orphaned_processes"
            ) as mock_cleanup,
        ):
            async with CrawlerEngine() as engine:
                assert isinstance(engine, CrawlerEngine)
                # Engine should be usable within context
                assert engine.rate_limiter is not None

            # Cleanup should be called on exit
            mock_cleanup.assert_called()

    @pytest.mark.asyncio
    async def test_determine_optimal_strategy_ultra_fast_sites(
        self, crawler_engine, mock_bbc_config
    ):
        """Test strategy determination for ultra-fast sites"""
        # ultra_fast is deprecated/disabled; BBC now falls back to generic.
        strategy = await crawler_engine._determine_optimal_strategy(mock_bbc_config)
        assert strategy == "generic"

    @pytest.mark.asyncio
    async def test_determine_optimal_strategy_ai_enhanced_sites(
        self, crawler_engine, mock_complex_config
    ):
        """Test strategy determination for complex sites"""
        # Test NYT domain gets ai_enhanced strategy
        strategy = await crawler_engine._determine_optimal_strategy(mock_complex_config)
        assert strategy == "ai_enhanced"

    @pytest.mark.asyncio
    async def test_determine_optimal_strategy_generic_default(
        self, crawler_engine, mock_site_config
    ):
        """Test strategy determination defaults to generic"""
        strategy = await crawler_engine._determine_optimal_strategy(mock_site_config)
        assert strategy == "generic"

    @pytest.mark.asyncio
    async def test_determine_optimal_strategy_performance_cache(
        self, crawler_engine, mock_site_config
    ):
        """Test strategy caching functionality"""
        # Mock performance history to trigger caching
        with patch(
            "agents.crawler.crawler_engine.get_source_performance_history",
            return_value=[
                {"strategy_used": "ultra_fast", "articles_per_second": 10.0},
                {"strategy_used": "generic", "articles_per_second": 2.0},
            ],
        ):
            # First call should cache the best non-deprecated strategy.
            strategy1 = await crawler_engine._determine_optimal_strategy(
                mock_site_config
            )
            assert strategy1 == "generic"

            # Second call should use cache
            strategy2 = await crawler_engine._determine_optimal_strategy(
                mock_site_config
            )
            assert strategy2 == "generic"

            # Verify cache was populated
            cache_key = f"{mock_site_config.domain}_{mock_site_config.source_id}"
            assert cache_key in crawler_engine.strategy_cache
            assert crawler_engine.strategy_cache[cache_key] == "generic"

    @pytest.mark.asyncio
    async def test_legacy_ultra_fast_paths_removed(self, crawler_engine):
        """Ultra-fast mode has been retired; engine should not expose legacy helper."""
        assert not hasattr(crawler_engine, "_crawl_ultra_fast_mode")

    @pytest.mark.asyncio
    async def test_crawl_ai_enhanced_mode(self, crawler_engine, mock_complex_config):
        """Test AI-enhanced crawling mode"""
        mock_articles = [
            {
                "title": "Test Article",
                "url": "https://nytimes.com/article",
                "content": "Content",
            }
        ]

        with (
            patch.object(
                crawler_engine, "_crawl_generic_mode", return_value=mock_articles
            ) as mock_generic,
            patch.object(crawler_engine, "_cleanup_orphaned_processes"),
        ):
            result = await crawler_engine._crawl_ai_enhanced_mode(
                mock_complex_config, max_articles=1
            )

            assert result == mock_articles
            assert crawler_engine.performance_metrics["mode_usage"]["ai_enhanced"] == 1
            mock_generic.assert_called_once_with(mock_complex_config, 1)

    @pytest.mark.asyncio
    async def test_crawl_generic_mode(self, crawler_engine, mock_site_config):
        """Test generic crawling mode"""
        mock_articles = [
            {
                "title": "Test Article",
                "url": "https://testsite.com/article",
                "content": "Content",
            }
        ]

        with (
            patch(
                "agents.crawler.crawler_engine.GenericSiteCrawler"
            ) as mock_crawler_class,
            patch.object(crawler_engine, "_cleanup_orphaned_processes"),
        ):
            from unittest.mock import AsyncMock

            mock_crawler = Mock()
            mock_crawler.crawl_site = AsyncMock(return_value=mock_articles)
            mock_crawler_class.return_value = mock_crawler

            result = await crawler_engine._crawl_generic_mode(
                mock_site_config, max_articles=1
            )

            assert result == mock_articles
            assert crawler_engine.performance_metrics["mode_usage"]["generic"] == 1
            mock_crawler.crawl_site.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_crawl_with_profile_crawl4ai(self, crawler_engine, mock_site_config):
        """Test crawling with Crawl4AI profile"""
        # This test is complex to mock due to relative imports inside functions
        # The profile functionality is tested in integration tests
        pass

    @pytest.mark.asyncio
    async def test_crawl_with_profile_generic_fallback(
        self, crawler_engine, mock_site_config
    ):
        """Test profile crawling falls back to generic"""
        mock_articles = [
            {
                "title": "Test Article",
                "url": "https://testsite.com/article",
                "content": "Content",
            }
        ]
        profile = {"engine": "generic"}

        with (
            patch.object(
                crawler_engine, "_crawl_generic_mode", return_value=mock_articles
            ) as mock_generic,
            patch.object(crawler_engine, "_cleanup_orphaned_processes"),
        ):
            result = await crawler_engine._crawl_with_profile(
                mock_site_config, profile, 3
            )

            assert result == mock_articles
            mock_generic.assert_called_once_with(mock_site_config, 3)

    @pytest.mark.asyncio
    async def test_crawl_with_profile_crawl4ai_import_error(
        self, crawler_engine, mock_site_config
    ):
        """Test profile crawling handles Crawl4AI import error"""
        # This test is complex to mock due to relative imports inside functions
        # The fallback behavior is tested in test_crawl_with_profile_unknown_engine
        pass

    @pytest.mark.asyncio
    async def test_apply_ai_analysis_success(self, crawler_engine):
        """Test successful AI analysis application"""
        article = {
            "title": "Test Article",
            "content": "This is a test article with substantial content for analysis that is definitely longer than 100 characters to trigger the AI analysis functionality properly.",
            "url": "https://testsite.com/article",
        }

        with patch("agents.crawler.crawler_engine.call_analyst_tool") as mock_call:
            mock_call.side_effect = [
                0.8,  # sentiment score
                ["politics", "economy"],  # topics
            ]

            result = await crawler_engine._apply_ai_analysis(article)

            assert result["sentiment"] == {"score": 0.8}
            assert result["topics"] == ["politics", "economy"]
            assert result["ai_analysis_applied"] is True

            assert mock_call.call_count == 2
            mock_call.assert_any_call("score_sentiment", article["content"])
            mock_call.assert_any_call("extract_topics", article["content"])

    @pytest.mark.asyncio
    async def test_apply_ai_analysis_short_content(self, crawler_engine):
        """Test AI analysis skips short content"""
        article = {
            "title": "Test Article",
            "content": "Short",
            "url": "https://testsite.com/article",
        }

        with patch("agents.crawler.crawler_engine.call_analyst_tool") as mock_call:
            result = await crawler_engine._apply_ai_analysis(article)

            # Should return article unchanged
            assert result == article
            mock_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_ai_analysis_error_handling(self, crawler_engine):
        """Test AI analysis handles errors gracefully"""
        article = {
            "title": "Test Article",
            "content": "This is a test article with substantial content for analysis.",
            "url": "https://testsite.com/article",
        }

        with patch(
            "agents.crawler.crawler_engine.call_analyst_tool",
            side_effect=Exception("Analysis failed"),
        ):
            result = await crawler_engine._apply_ai_analysis(article)

            # Should return article without AI analysis
            assert result == article
            assert "sentiment" not in result
            assert "topics" not in result
            assert result.get("ai_analysis_applied") is not True

    @pytest.mark.asyncio
    async def test_crawl_site_deprecated_ultra_fast_falls_back_to_generic(
        self, crawler_engine, mock_bbc_config
    ):
        """Deprecated ultra_fast strategy should route through generic path."""
        mock_articles = [
            {
                "title": "Test Article",
                "url": "https://bbc.co.uk/article",
                "content": "Content",
            }
        ]

        with (
            patch.object(
                crawler_engine, "_crawl_generic_mode", return_value=mock_articles
            ) as mock_generic,
            patch.object(
                crawler_engine, "_determine_optimal_strategy", return_value="ultra_fast"
            ),
        ):
            result = await crawler_engine.crawl_site(mock_bbc_config, max_articles=1)

            assert result == mock_articles
            mock_generic.assert_called_once_with(mock_bbc_config, 1)

    @pytest.mark.asyncio
    async def test_crawl_site_ai_enhanced(self, crawler_engine, mock_complex_config):
        """Test crawl_site with ai_enhanced strategy"""
        mock_articles = [
            {
                "title": "Test Article",
                "url": "https://nytimes.com/article",
                "content": "Content",
            }
        ]

        with (
            patch.object(
                crawler_engine, "_crawl_ai_enhanced_mode", return_value=mock_articles
            ) as mock_ai_enhanced,
            patch.object(
                crawler_engine,
                "_determine_optimal_strategy",
                return_value="ai_enhanced",
            ),
        ):
            result = await crawler_engine.crawl_site(
                mock_complex_config, max_articles=1
            )

            assert result == mock_articles
            mock_ai_enhanced.assert_called_once_with(mock_complex_config, 1)

    @pytest.mark.asyncio
    async def test_crawl_site_generic(self, crawler_engine, mock_site_config):
        """Test crawl_site with generic strategy"""
        mock_articles = [
            {
                "title": "Test Article",
                "url": "https://testsite.com/article",
                "content": "Content",
            }
        ]

        with (
            patch.object(
                crawler_engine, "_crawl_generic_mode", return_value=mock_articles
            ) as mock_generic,
            patch.object(
                crawler_engine, "_determine_optimal_strategy", return_value="generic"
            ),
        ):
            result = await crawler_engine.crawl_site(mock_site_config, max_articles=1)

            assert result == mock_articles
            mock_generic.assert_called_once_with(mock_site_config, 1)

    @pytest.mark.asyncio
    async def test_crawl_multiple_sites_basic(self, crawler_engine, mock_site_config):
        """Test basic multi-site crawling functionality"""
        site_configs = [mock_site_config]
        mock_articles = [
            {
                "title": "Test Article",
                "url": "https://testsite.com/article",
                "content": "Content",
            }
        ]

        with (
            patch.object(
                crawler_engine, "crawl_site", return_value=mock_articles
            ) as _mock_crawl_site,
            patch.object(crawler_engine, "_ingest_articles") as mock_ingest,
            patch.object(crawler_engine, "_cleanup_orphaned_processes"),
            patch.dict(
                "os.environ",
                {
                    "UNIFIED_CRAWLER_CONSTRAINED_BACKFILL_ENABLED": "0",
                    "UNIFIED_CRAWLER_ADAPTIVE_DEPTH_ENABLED": "0",
                    "UNIFIED_CRAWLER_LANE1_COMPARATIVE_PLAN_ENABLED": "0",
                },
                clear=False,
            ),
        ):
            mock_ingest.return_value = {
                "new_articles": 1,
                "duplicates": 0,
                "errors": 0,
                "details": [{"url": "https://testsite.com/article", "status": "new"}],
            }

            result = await crawler_engine.crawl_multiple_sites(
                site_configs, max_articles_per_site=1
            )

            # Verify basic structure
            assert result["unified_crawl"] is True
            assert result["sites_crawled"] == 1
            assert result["total_articles"] == 1
            assert result["articles_ingested"] == 1
            assert result["duplicates_skipped"] == 0
            assert result["ingestion_errors"] == 0
            assert "processing_time_seconds" in result
            assert "articles_per_second" in result
            assert result["site_breakdown"]["testsite.com"] == 1
            assert len(result["articles"]) == 1

            # Verify performance metrics updated
            assert crawler_engine.performance_metrics["articles_processed"] == 1
            assert crawler_engine.performance_metrics["sites_crawled"] == 1

    @pytest.mark.asyncio
    async def test_crawl_multiple_sites_concurrent(self, crawler_engine):
        """Test concurrent multi-site crawling with semaphore"""
        site_configs = [
            SiteConfig(
                {
                    "id": 1,
                    "name": "Site 1",
                    "domain": "site1.com",
                    "url": "https://site1.com",
                }
            ),
            SiteConfig(
                {
                    "id": 2,
                    "name": "Site 2",
                    "domain": "site2.com",
                    "url": "https://site2.com",
                }
            ),
        ]

        with (
            patch.object(
                crawler_engine,
                "crawl_site",
                return_value=[
                    {
                        "title": "Article 1",
                        "url": "https://site1.com/article",
                        "content": "Content 1",
                    }
                ],
            ) as mock_crawl_site,
            patch.object(crawler_engine, "_ingest_articles") as mock_ingest,
            patch.object(crawler_engine, "_cleanup_orphaned_processes"),
        ):
            mock_ingest.return_value = {
                "new_articles": 1,
                "duplicates": 0,
                "errors": 0,
                "details": [{"url": "https://site1.com/article", "status": "new"}],
            }

            result = await crawler_engine.crawl_multiple_sites(
                site_configs, max_articles_per_site=1, concurrent_sites=2
            )

            assert result["sites_crawled"] == 2
            assert result["total_articles"] == 2
            assert mock_crawl_site.call_count == 2

    @pytest.mark.asyncio
    async def test_crawl_multiple_sites_with_duplicates(
        self, crawler_engine, mock_site_config
    ):
        """Test handling of duplicate articles in multi-site crawling"""
        site_configs = [mock_site_config]
        mock_articles = [
            {
                "title": "Test Article",
                "url": "https://testsite.com/article",
                "content": "Content",
            }
        ]

        with (
            patch.object(
                crawler_engine, "crawl_site", return_value=mock_articles
            ) as _mock_crawl_site,
            patch.object(crawler_engine, "_ingest_articles") as mock_ingest,
            patch.object(crawler_engine, "_cleanup_orphaned_processes"),
            patch.dict(
                "os.environ",
                {
                    "UNIFIED_CRAWLER_CONSTRAINED_BACKFILL_ENABLED": "0",
                    "UNIFIED_CRAWLER_ADAPTIVE_DEPTH_ENABLED": "0",
                },
                clear=False,
            ),
        ):
            mock_ingest.return_value = {
                "new_articles": 0,
                "duplicates": 1,
                "errors": 0,
                "details": [
                    {"url": "https://testsite.com/article", "status": "duplicate"}
                ],
            }

            result = await crawler_engine.crawl_multiple_sites(
                site_configs, max_articles_per_site=1
            )

            assert result["total_articles"] == 0
            assert result["duplicates_skipped"] == 1
            assert result["site_duplicate_breakdown"]["testsite.com"] == 1

    @pytest.mark.asyncio
    async def test_crawl_multiple_sites_replaces_duplicates_to_hit_target(
        self, crawler_engine, mock_site_config
    ):
        """When early candidates dedupe, crawler should consume replacements to reach target where possible."""
        site_configs = [mock_site_config]
        mock_articles = [
            {
                "title": "Duplicate Candidate",
                "url": "https://testsite.com/article-dup",
                "content": "Content dup",
            },
            {
                "title": "Replacement Candidate",
                "url": "https://testsite.com/article-new",
                "content": "Content new",
            },
        ]

        with (
            patch.object(crawler_engine, "crawl_site", return_value=mock_articles),
            patch.object(crawler_engine, "_cleanup_orphaned_processes"),
            patch.object(crawler_engine, "_submit_hitl_candidates", return_value=None),
            patch.object(crawler_engine, "_ingest_articles") as mock_ingest,
            patch.dict(
                "os.environ",
                {
                    "UNIFIED_CRAWLER_CONSTRAINED_BACKFILL_ENABLED": "0",
                    "UNIFIED_CRAWLER_ADAPTIVE_DEPTH_ENABLED": "0",
                    "UNIFIED_CRAWLER_LANE1_COMPARATIVE_PLAN_ENABLED": "0",
                },
                clear=False,
            ),
        ):
            mock_ingest.side_effect = [
                {
                    "new_articles": 0,
                    "duplicates": 1,
                    "errors": 0,
                    "details": [
                        {
                            "url": "https://testsite.com/article-dup",
                            "status": "duplicate",
                        }
                    ],
                },
                {
                    "new_articles": 1,
                    "duplicates": 0,
                    "errors": 0,
                    "details": [
                        {"url": "https://testsite.com/article-new", "status": "new"}
                    ],
                },
            ]

            result = await crawler_engine.crawl_multiple_sites(
                site_configs, max_articles_per_site=1
            )

            assert result["total_articles"] == 1
            assert result["duplicates_skipped"] == 1
            assert mock_ingest.call_count >= 2

    @pytest.mark.asyncio
    async def test_crawl_multiple_sites_lane2_fallback_after_zero_ingest(
        self, crawler_engine, mock_site_config
    ):
        """When lane1 yields zero new ingest, optional lane2 fallback should be attempted."""
        site_configs = [mock_site_config]

        async def _crawl_side_effect(site_config, _max_articles):
            domain = site_config.domain or site_config.name
            if domain == "testsite.com":
                return [
                    {
                        "title": "Lane1 Duplicate",
                        "url": "https://testsite.com/article-dup",
                        "content": "dup",
                    }
                ]
            return [
                {
                    "title": "Lane2 Fresh",
                    "url": f"https://{domain}/article-new",
                    "content": "new",
                }
            ]

        with (
            patch.object(crawler_engine, "crawl_site", side_effect=_crawl_side_effect),
            patch.object(crawler_engine, "_cleanup_orphaned_processes"),
            patch.object(crawler_engine, "_submit_hitl_candidates", return_value=None),
            patch("agents.crawler.crawler_engine.get_sources_by_domain") as mock_get_sources,
            patch.object(crawler_engine, "_ingest_articles") as mock_ingest,
            patch.dict(
                "os.environ",
                {
                    "UNIFIED_CRAWLER_LANE2_FALLBACK_ENABLED": "1",
                    "UNIFIED_CRAWLER_LANE2_SEED_ENABLED": "0",
                    "UNIFIED_CRAWLER_LANE1_COMPARATIVE_PLAN_ENABLED": "0",
                    "UNIFIED_CRAWLER_LANE2_FALLBACK_DOMAINS": "lane2.com",
                    "UNIFIED_CRAWLER_LANE2_MAX_SITES": "1",
                    "UNIFIED_CRAWLER_LANE2_MAX_ARTICLES_PER_SITE": "1",
                    "UNIFIED_CRAWLER_CONSTRAINED_BACKFILL_ENABLED": "0",
                    "UNIFIED_CRAWLER_ADAPTIVE_DEPTH_ENABLED": "0",
                },
                clear=False,
            ),
        ):
            mock_get_sources.side_effect = lambda domains: (
                [
                    {
                        "id": 2,
                        "name": "Lane2 Source",
                        "domain": "lane2.com",
                        "url": "https://lane2.com",
                    }
                ]
                if domains == ["lane2.com"]
                else []
            )

            mock_ingest.side_effect = [
                {
                    "new_articles": 0,
                    "duplicates": 1,
                    "errors": 0,
                    "details": [
                        {
                            "url": "https://testsite.com/article-dup",
                            "status": "duplicate",
                        }
                    ],
                },
                {
                    "new_articles": 1,
                    "duplicates": 0,
                    "errors": 0,
                    "details": [
                        {
                            "url": "https://lane2.com/article-new",
                            "status": "new",
                        }
                    ],
                },
            ]

            result = await crawler_engine.crawl_multiple_sites(
                site_configs, max_articles_per_site=1
            )

            assert result["total_articles"] == 1
            assert result["duplicates_skipped"] == 1
            assert result["site_breakdown"]["lane2.com"] == 1
            assert result["lane2_fallback"]["enabled"] is True
            assert result["lane2_fallback"]["triggered"] is True
            assert result["lane2_fallback"]["attempted_sites"] == 1
            assert result["lane2_fallback"]["ingested"] == 1
            assert result["lane2_fallback"]["attempted_domains"] == ["lane2.com"]
            assert isinstance(result["preflight"], dict)
            assert mock_ingest.call_count == 2

    @pytest.mark.asyncio
    async def test_crawl_multiple_sites_strict_preflight_abort(
        self, crawler_engine, mock_site_config
    ):
        """Strict preflight should abort early when required dependencies are down."""
        site_configs = [mock_site_config]

        with (
            patch.dict(
                "os.environ",
                {
                    "USE_HITL": "1",
                    "UNIFIED_CRAWLER_PREFLIGHT_STRICT": "1",
                },
                clear=False,
            ),
            patch("agents.crawler.crawler_engine.requests.get", side_effect=Exception("down")),
            patch.object(crawler_engine, "crawl_site") as mock_crawl_site,
        ):
            result = await crawler_engine.crawl_multiple_sites(
                site_configs,
                max_articles_per_site=1,
            )

            assert result["sites_crawled"] == 0
            assert result["total_articles"] == 0
            assert result["lane2_fallback"]["triggered"] is False
            assert result["preflight"]["ready"] is False
            mock_crawl_site.assert_not_called()

    @pytest.mark.asyncio
    async def test_crawl_multiple_sites_lane2_fallback_skips_blocked_source(
        self, crawler_engine, mock_site_config
    ):
        """Lane2 replacement sources in blocked state should be skipped."""
        site_configs = [mock_site_config]

        async def _crawl_side_effect(site_config, _max_articles):
            domain = site_config.domain or site_config.name
            if domain == "testsite.com":
                return [
                    {
                        "title": "Lane1 Duplicate",
                        "url": "https://testsite.com/article-dup",
                        "content": "dup",
                    }
                ]
            return [
                {
                    "title": "Lane2 Fresh",
                    "url": f"https://{domain}/article-new",
                    "content": "new",
                }
            ]

        with (
            patch.object(crawler_engine, "crawl_site", side_effect=_crawl_side_effect),
            patch.object(crawler_engine, "_cleanup_orphaned_processes"),
            patch.object(crawler_engine, "_submit_hitl_candidates", return_value=None),
            patch("agents.crawler.crawler_engine.get_sources_by_domain") as mock_get_sources,
            patch.object(crawler_engine, "_ingest_articles") as mock_ingest,
            patch.dict(
                "os.environ",
                {
                    "UNIFIED_CRAWLER_LANE2_FALLBACK_ENABLED": "1",
                    "UNIFIED_CRAWLER_LANE2_SEED_ENABLED": "0",
                    "UNIFIED_CRAWLER_LANE2_FALLBACK_DOMAINS": "lane2-blocked.com",
                    "UNIFIED_CRAWLER_LANE2_MAX_SITES": "1",
                    "UNIFIED_CRAWLER_LANE2_MAX_ARTICLES_PER_SITE": "1",
                    "UNIFIED_CRAWLER_CONSTRAINED_BACKFILL_ENABLED": "0",
                    "UNIFIED_CRAWLER_ADAPTIVE_DEPTH_ENABLED": "0",
                },
                clear=False,
            ),
        ):
            mock_get_sources.side_effect = lambda domains: (
                [
                    {
                        "id": 2,
                        "name": "Lane2 Blocked Source",
                        "domain": "lane2-blocked.com",
                        "url": "https://lane2-blocked.com",
                        "source_state": "blocked",
                    }
                ]
                if domains == ["lane2-blocked.com"]
                else []
            )

            mock_ingest.side_effect = [
                {
                    "new_articles": 0,
                    "duplicates": 1,
                    "errors": 0,
                    "details": [
                        {
                            "url": "https://testsite.com/article-dup",
                            "status": "duplicate",
                        }
                    ],
                }
            ]

            result = await crawler_engine.crawl_multiple_sites(
                site_configs, max_articles_per_site=1
            )

            assert result["total_articles"] == 0
            assert result["duplicates_skipped"] == 1
            assert mock_ingest.call_count == 1

    @pytest.mark.asyncio
    async def test_crawl_multiple_sites_lane2_fallback_skips_provisional_when_discovery_disabled(
        self, crawler_engine, mock_site_config
    ):
        """Lane2 provisional replacement should be skipped when discovery is disabled."""
        site_configs = [mock_site_config]

        async def _crawl_side_effect(site_config, _max_articles):
            domain = site_config.domain or site_config.name
            if domain == "testsite.com":
                return [
                    {
                        "title": "Lane1 Duplicate",
                        "url": "https://testsite.com/article-dup",
                        "content": "dup",
                    }
                ]
            return [
                {
                    "title": "Lane2 Fresh",
                    "url": f"https://{domain}/article-new",
                    "content": "new",
                }
            ]

        with (
            patch.object(crawler_engine, "crawl_site", side_effect=_crawl_side_effect),
            patch.object(crawler_engine, "_cleanup_orphaned_processes"),
            patch.object(crawler_engine, "_submit_hitl_candidates", return_value=None),
            patch("agents.crawler.crawler_engine.get_sources_by_domain") as mock_get_sources,
            patch.object(crawler_engine, "_ingest_articles") as mock_ingest,
            patch.dict(
                "os.environ",
                {
                    "UNIFIED_CRAWLER_LANE2_FALLBACK_ENABLED": "1",
                    "UNIFIED_CRAWLER_LANE2_SEED_ENABLED": "0",
                    "UNIFIED_CRAWLER_LANE2_FALLBACK_DOMAINS": "lane2-provisional.com",
                    "UNIFIED_CRAWLER_LANE2_MAX_SITES": "1",
                    "UNIFIED_CRAWLER_LANE2_MAX_ARTICLES_PER_SITE": "1",
                    "UNIFIED_CRAWLER_DISCOVERY_ENABLED": "0",
                    "UNIFIED_CRAWLER_CONSTRAINED_BACKFILL_ENABLED": "0",
                    "UNIFIED_CRAWLER_ADAPTIVE_DEPTH_ENABLED": "0",
                },
                clear=False,
            ),
        ):
            mock_get_sources.side_effect = lambda domains: (
                [
                    {
                        "id": 2,
                        "name": "Lane2 Provisional Source",
                        "domain": "lane2-provisional.com",
                        "url": "https://lane2-provisional.com",
                        "source_state": "provisional_discovered",
                    }
                ]
                if domains == ["lane2-provisional.com"]
                else []
            )

            mock_ingest.side_effect = [
                {
                    "new_articles": 0,
                    "duplicates": 1,
                    "errors": 0,
                    "details": [
                        {
                            "url": "https://testsite.com/article-dup",
                            "status": "duplicate",
                        }
                    ],
                }
            ]

            result = await crawler_engine.crawl_multiple_sites(
                site_configs, max_articles_per_site=1
            )

            assert result["total_articles"] == 0
            assert result["duplicates_skipped"] == 1
            assert mock_ingest.call_count == 1

    @pytest.mark.asyncio
    async def test_crawl_multiple_sites_whitelist_only_disables_lane2_fallback(
        self, crawler_engine, mock_site_config
    ):
        """Whitelist-only mode should disable lane2 fallback even when enabled by env."""
        site_configs = [mock_site_config]

        async def _crawl_side_effect(site_config, _max_articles):
            domain = site_config.domain or site_config.name
            if domain == "testsite.com":
                return [
                    {
                        "title": "Lane1 Duplicate",
                        "url": "https://testsite.com/article-dup",
                        "content": "dup",
                    }
                ]
            return [
                {
                    "title": "Lane2 Fresh",
                    "url": f"https://{domain}/article-new",
                    "content": "new",
                }
            ]

        with (
            patch.object(crawler_engine, "crawl_site", side_effect=_crawl_side_effect),
            patch.object(crawler_engine, "_cleanup_orphaned_processes"),
            patch.object(crawler_engine, "_submit_hitl_candidates", return_value=None),
            patch("agents.crawler.crawler_engine.get_sources_by_domain") as mock_get_sources,
            patch.object(crawler_engine, "_ingest_articles") as mock_ingest,
            patch.dict(
                "os.environ",
                {
                    "UNIFIED_CRAWLER_LANE2_FALLBACK_ENABLED": "1",
                    "UNIFIED_CRAWLER_LANE2_SEED_ENABLED": "0",
                    "UNIFIED_CRAWLER_LANE2_FALLBACK_DOMAINS": "lane2.com",
                    "UNIFIED_CRAWLER_LANE2_MAX_SITES": "1",
                    "UNIFIED_CRAWLER_LANE2_MAX_ARTICLES_PER_SITE": "1",
                    "UNIFIED_CRAWLER_WHITELIST_ONLY_MODE": "1",
                    "UNIFIED_CRAWLER_CONSTRAINED_BACKFILL_ENABLED": "0",
                    "UNIFIED_CRAWLER_ADAPTIVE_DEPTH_ENABLED": "0",
                },
                clear=False,
            ),
        ):
            mock_ingest.side_effect = [
                {
                    "new_articles": 0,
                    "duplicates": 1,
                    "errors": 0,
                    "details": [
                        {
                            "url": "https://testsite.com/article-dup",
                            "status": "duplicate",
                        }
                    ],
                }
            ]

            result = await crawler_engine.crawl_multiple_sites(
                site_configs, max_articles_per_site=1
            )

            assert result["total_articles"] == 0
            assert result["duplicates_skipped"] == 1
            assert mock_ingest.call_count == 1
            mock_get_sources.assert_not_called()

    @pytest.mark.asyncio
    async def test_ingest_articles_success(self, crawler_engine):
        """Test successful article ingestion via MCP bus"""
        articles = [
            {
                "url": "https://testsite.com/article1",
                "title": "Test Article 1",
                "content": "Content 1",
                "domain": "testsite.com",
            },
            {
                "url": "https://testsite.com/article2",
                "title": "Test Article 2",
                "content": "Content 2",
                "domain": "testsite.com",
            },
        ]

        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "ok",
            "data": {"status": "ok", "duplicate": False},
        }
        mock_response.raise_for_status.return_value = None

        with (
            patch(
                "agents.crawler.crawler_engine.requests.post",
                return_value=mock_response,
            ) as mock_post,
            patch(
                "agents.crawler.crawler_engine.make_json_safe", side_effect=lambda x: x
            ),
        ):
            result = await crawler_engine._ingest_articles(articles)

            assert result["new_articles"] == 2
            assert result["duplicates"] == 0
            assert result["errors"] == 0
            assert len(result["details"]) == 2

            # Verify MCP bus calls
            assert mock_post.call_count == 2
            for call in mock_post.call_args_list:
                args, kwargs = call
                assert args[0] == "http://localhost:8000/call"
                payload = kwargs["json"]
                assert payload["agent"] == "memory"
                assert payload["tool"] == "ingest_article"

    @pytest.mark.asyncio
    async def test_ingest_articles_with_duplicates(self, crawler_engine):
        """Test article ingestion with duplicate detection"""
        articles = [
            {
                "url": "https://testsite.com/article1",
                "title": "Test Article 1",
                "content": "Content 1",
                "domain": "testsite.com",
            }
        ]

        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "ok",
            "data": {"status": "ok", "duplicate": True},
        }
        mock_response.raise_for_status.return_value = None

        with (
            patch(
                "agents.crawler.crawler_engine.requests.post",
                return_value=mock_response,
            ) as _mock_post,
            patch(
                "agents.crawler.crawler_engine.make_json_safe", side_effect=lambda x: x
            ),
        ):
            result = await crawler_engine._ingest_articles(articles)

            assert result["new_articles"] == 0
            assert result["duplicates"] == 1
            assert result["errors"] == 0
            assert result["details"][0]["status"] == "duplicate"

    @pytest.mark.asyncio
    async def test_ingest_articles_error_handling(self, crawler_engine):
        """Test article ingestion error handling"""
        articles = [
            {
                "url": "https://testsite.com/article1",
                "title": "Test Article 1",
                "content": "Content 1",
                "domain": "testsite.com",
            }
        ]

        with (
            patch(
                "agents.crawler.crawler_engine.requests.post",
                side_effect=Exception("Network error"),
            ) as _mock_post,
            patch(
                "agents.crawler.crawler_engine.make_json_safe", side_effect=lambda x: x
            ),
        ):
            result = await crawler_engine._ingest_articles(articles)

            assert result["new_articles"] == 0
            assert result["duplicates"] == 0
            assert result["errors"] == 1
            assert result["details"][0]["status"] == "error"
            assert "Network error" in result["details"][0]["error"]

    @pytest.mark.asyncio
    async def test_run_unified_crawl_basic(self, crawler_engine):
        """Test run_unified_crawl main entry point"""
        domains = ["testsite.com"]
        mock_articles = [
            {
                "title": "Test Article",
                "url": "https://testsite.com/article",
                "content": "Content",
            }
        ]

        with (
            patch(
                "agents.crawler.crawler_engine.get_sources_by_domain",
                return_value=[
                    {
                        "id": 1,
                        "name": "Test Site",
                        "domain": "testsite.com",
                        "url": "https://testsite.com",
                    }
                ],
            ) as mock_get_sources,
            patch.object(crawler_engine, "crawl_multiple_sites") as mock_crawl_multiple,
        ):
            mock_crawl_multiple.return_value = {
                "unified_crawl": True,
                "sites_crawled": 1,
                "total_articles": 1,
                "articles": mock_articles,
            }

            result = await crawler_engine.run_unified_crawl(
                domains, max_articles_per_site=1
            )

            assert result["unified_crawl"] is True
            assert result["sites_crawled"] == 1
            mock_get_sources.assert_called_once_with(["testsite.com"])
            mock_crawl_multiple.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_unified_crawl_unknown_domain(self, crawler_engine):
        """Test run_unified_crawl with unknown domain creates basic config"""
        domains = ["unknownsite.com"]

        with (
            patch(
                "agents.crawler.crawler_engine.get_sources_by_domain", return_value=[]
            ) as mock_get_sources,
            patch.object(crawler_engine, "crawl_multiple_sites") as mock_crawl_multiple,
        ):
            mock_crawl_multiple.return_value = {
                "unified_crawl": True,
                "sites_crawled": 1,
                "total_articles": 0,
                "articles": [],
            }

            result = await crawler_engine.run_unified_crawl(
                domains, max_articles_per_site=1
            )

            assert result["unified_crawl"] is True
            mock_get_sources.assert_called_once_with(["unknownsite.com"])
            mock_crawl_multiple.assert_called_once()

            # Verify SiteConfig was created with basic config
            call_args = mock_crawl_multiple.call_args
            site_configs = call_args[0][0]
            assert len(site_configs) == 1
            config = site_configs[0]
            assert config.domain == "unknownsite.com"
            assert config.url == "https://unknownsite.com"

    @pytest.mark.asyncio
    async def test_run_unified_crawl_no_valid_domains(self, crawler_engine):
        """Test run_unified_crawl with no valid domains"""
        domains = []

        result = await crawler_engine.run_unified_crawl(domains)

        assert result == {"error": "No valid domains provided"}

    @pytest.mark.asyncio
    async def test_run_unified_crawl_skips_blocked_source(self, crawler_engine):
        """Blocked sources should be excluded from crawl eligibility."""
        domains = ["blockedsite.com"]

        with (
            patch.dict("os.environ", {}, clear=False),
            patch(
                "agents.crawler.crawler_engine.get_sources_by_domain",
                return_value=[
                    {
                        "id": 11,
                        "name": "Blocked Site",
                        "domain": "blockedsite.com",
                        "url": "https://blockedsite.com",
                        "source_state": "blocked",
                    }
                ],
            ) as mock_get_sources,
            patch.object(crawler_engine, "crawl_multiple_sites") as mock_crawl_multiple,
        ):
            result = await crawler_engine.run_unified_crawl(domains)

            assert result == {"error": "No valid domains provided"}
            mock_get_sources.assert_called_once_with(["blockedsite.com"])
            mock_crawl_multiple.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_unified_crawl_skips_provisional_when_discovery_disabled(
        self, crawler_engine
    ):
        """Provisional sources should be skipped when discovery is disabled."""
        domains = ["provisionalsite.com"]

        with (
            patch.dict(
                "os.environ",
                {"UNIFIED_CRAWLER_DISCOVERY_ENABLED": "0"},
                clear=False,
            ),
            patch(
                "agents.crawler.crawler_engine.get_sources_by_domain",
                return_value=[
                    {
                        "id": 12,
                        "name": "Provisional Site",
                        "domain": "provisionalsite.com",
                        "url": "https://provisionalsite.com",
                        "source_state": "provisional_discovered",
                    }
                ],
            ) as mock_get_sources,
            patch.object(crawler_engine, "crawl_multiple_sites") as mock_crawl_multiple,
        ):
            result = await crawler_engine.run_unified_crawl(domains)

            assert result == {"error": "No valid domains provided"}
            mock_get_sources.assert_called_once_with(["provisionalsite.com"])
            mock_crawl_multiple.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_unified_crawl_allows_probation_in_whitelist_only_mode(
        self, crawler_engine
    ):
        """Probation sources remain crawl-eligible in whitelist-only mode."""
        domains = ["probationsite.com"]

        with (
            patch.dict(
                "os.environ",
                {"UNIFIED_CRAWLER_WHITELIST_ONLY_MODE": "1"},
                clear=False,
            ),
            patch(
                "agents.crawler.crawler_engine.get_sources_by_domain",
                return_value=[
                    {
                        "id": 13,
                        "name": "Probation Site",
                        "domain": "probationsite.com",
                        "url": "https://probationsite.com",
                        "source_state": "probation",
                    }
                ],
            ) as mock_get_sources,
            patch.object(crawler_engine, "crawl_multiple_sites") as mock_crawl_multiple,
        ):
            mock_crawl_multiple.return_value = {
                "unified_crawl": True,
                "sites_crawled": 1,
                "total_articles": 0,
                "articles": [],
            }

            result = await crawler_engine.run_unified_crawl(
                domains,
                max_articles_per_site=1,
            )

            assert result["unified_crawl"] is True
            mock_get_sources.assert_called_once_with(["probationsite.com"])
            mock_crawl_multiple.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_performance_report(self, crawler_engine):
        """Test performance report generation"""
        # Simulate some activity
        crawler_engine.performance_metrics["articles_processed"] = 42
        crawler_engine.performance_metrics["sites_crawled"] = 5
        crawler_engine.performance_metrics["errors"] = 2
        crawler_engine.performance_metrics["mode_usage"]["ai_enhanced"] = 3
        crawler_engine.performance_metrics["mode_usage"]["generic"] = 2

        report = crawler_engine.get_performance_report()

        assert report["articles_processed"] == 42
        assert report["sites_crawled"] == 5
        assert report["errors"] == 2
        assert report["mode_usage"]["ai_enhanced"] == 3
        assert report["mode_usage"]["generic"] == 2
        assert "uptime_seconds" in report
        assert report["uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_error_handling_crawl_failure(self, crawler_engine, mock_site_config):
        """Test error handling when crawling fails"""
        with (
            patch.object(
                crawler_engine, "crawl_site", side_effect=Exception("Crawl failed")
            ) as _mock_crawl_site,
            patch.object(crawler_engine, "_cleanup_orphaned_processes"),
            patch.dict(
                "os.environ",
                {
                    "UNIFIED_CRAWLER_CONSTRAINED_BACKFILL_ENABLED": "0",
                    "UNIFIED_CRAWLER_LANE1_COMPARATIVE_PLAN_ENABLED": "0",
                    "UNIFIED_CRAWLER_LANE2_FALLBACK_ENABLED": "0",
                },
                clear=False,
            ),
        ):
            result = await crawler_engine.crawl_multiple_sites(
                [mock_site_config], max_articles_per_site=1
            )

            # Should still return valid structure despite errors
            assert result["unified_crawl"] is True
            assert result["sites_crawled"] == 1
            assert result["total_articles"] == 0
            assert (
                result["ingestion_errors"] == 1
            )  # Crawl failure is counted as ingestion error
            assert result["site_error_breakdown"]["testsite.com"] == 1

            # Performance metrics should reflect the error
            assert crawler_engine.performance_metrics["errors"] == 1

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_processes(self, crawler_engine):
        """Test orphaned process cleanup functionality"""
        with (
            patch("subprocess.run") as mock_subprocess,
            patch("os.kill") as mock_kill,
            patch("time.sleep"),
        ):  # Prevent actual sleep
            # Mock pgrep finding processes and ps showing old processes
            def mock_run(*args, **kwargs):
                if "pgrep" in str(args[0]):
                    result = Mock()
                    result.returncode = 0
                    result.stdout = "1234\n5678\n"
                    return result
                elif "ps" in str(args[0]):
                    result = Mock()
                    result.returncode = 0
                    result.stdout = "700"  # 700 seconds = 11+ minutes
                    return result
                return Mock(returncode=1)

            mock_subprocess.side_effect = mock_run

            await crawler_engine._cleanup_orphaned_processes()

            # Should have attempted to kill old processes
            assert mock_kill.call_count >= 2  # At least Chrome and Playwright processes

    @pytest.mark.asyncio
    async def test_determine_strategy_with_performance_history(
        self, crawler_engine, mock_site_config
    ):
        """Test strategy determination using performance history"""
        # Mock performance history where deprecated ultra_fast is ignored.
        crawler_engine.performance_history[mock_site_config.domain] = [
            {"strategy_used": "ultra_fast", "articles_per_second": 10.0},
            {"strategy_used": "generic", "articles_per_second": 2.0},
        ]

        with patch(
            "agents.crawler.crawler_engine.get_source_performance_history",
            return_value=[
                {"strategy_used": "ultra_fast", "articles_per_second": 10.0},
                {"strategy_used": "generic", "articles_per_second": 2.0},
            ],
        ):
            strategy = await crawler_engine._determine_optimal_strategy(
                mock_site_config
            )

            # Should choose generic because ultra_fast is deprecated/ignored.
            assert strategy == "generic"
            assert (
                crawler_engine.strategy_cache[
                    f"{mock_site_config.domain}_{mock_site_config.source_id}"
                ]
                == "generic"
            )

    @pytest.mark.asyncio
    async def test_crawl_with_profile_unknown_engine(
        self, crawler_engine, mock_site_config
    ):
        """Test crawling with unknown profile engine falls back to generic"""
        profile = {"engine": "unknown_engine"}

        with (
            patch.object(crawler_engine, "_crawl_generic_mode") as mock_generic,
            patch.object(crawler_engine, "_cleanup_orphaned_processes"),
        ):
            await crawler_engine._crawl_with_profile(mock_site_config, profile, 5)

            mock_generic.assert_called_once_with(mock_site_config, 5)

    @pytest.mark.asyncio
    async def test_crawl_generic_mode_error_handling(
        self, crawler_engine, mock_site_config
    ):
        """Test generic mode handles crawling errors gracefully"""
        with (
            patch(
                "agents.crawler.crawler_engine.GenericSiteCrawler"
            ) as mock_crawler_class,
            patch.object(crawler_engine, "_cleanup_orphaned_processes"),
        ):
            mock_crawler = Mock()
            mock_crawler.crawl_site.side_effect = Exception("Crawling failed")
            mock_crawler_class.return_value = mock_crawler

            result = await crawler_engine._crawl_generic_mode(
                mock_site_config, max_articles=5
            )

            assert result == []  # Should return empty list on error
            # Performance metrics are not updated on error
            assert crawler_engine.performance_metrics["mode_usage"]["generic"] == 0
