#!/usr/bin/env python3
"""
Crawler Engine for JustNews

Unified production crawler that combines all crawling strategies
into a single intelligent system.
"""

import asyncio
import json
import os
import time
from collections.abc import Mapping, Sequence
from datetime import timezone, datetime
from typing import Any
from urllib.parse import urlparse

import requests

try:
    from lxml import etree as lxml_etree  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    lxml_etree = None

# Database imports
from agents.crawler.enhancements import (
    ModalHandler,
    PaywallDetector,
    ProxyManager,
    StealthBrowserFactory,
    UserAgentProvider,
)
from common.json_utils import make_json_safe
from common.observability import get_logger
from common.tracing import traced
from config import get_crawling_config

from ..performance_monitoring import (
    PerformanceOptimizer,
    get_performance_monitor,
    start_performance_monitoring,
)
from ..sites.generic_site_crawler import (
    GenericSiteCrawler,
    MultiSiteCrawler,
    SiteConfig,
)
from .adaptive_metrics import summarise_adaptive_articles
from .crawler_utils import (
    RateLimiter,
    RobotsChecker,
    create_crawling_performance_table,
    get_active_sources,
    get_source_performance_history,
    get_sources_by_domain,
    initialize_connection_pool,
    record_crawling_performance,
    record_paywall_detection,
)

MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")
try:
    _site_batches_env = int(os.environ.get("UNIFIED_CRAWLER_MAX_SITE_BATCHES", "4"))
except (TypeError, ValueError):
    _site_batches_env = 4
MAX_SITE_BATCHES = max(1, _site_batches_env)

try:
    PAYWALL_SKIP_ACTIVATION_THRESHOLD = max(
        1, int(os.environ.get("UNIFIED_CRAWLER_PAYWALL_SKIP_THRESHOLD", "3"))
    )
except (TypeError, ValueError):
    PAYWALL_SKIP_ACTIVATION_THRESHOLD = 3


def call_analyst_tool(tool: str, *args, **kwargs) -> Any:
    payload = {"agent": "analyst", "tool": tool, "args": list(args), "kwargs": kwargs}
    resp = requests.post(f"{MCP_BUS_URL}/call", json=payload)
    resp.raise_for_status()
    return resp.json().get("data")


logger = get_logger(__name__)


class CrawlerEngine:
    """
    Unified production crawler that combines all crawling strategies
    into a single intelligent system.

    Features:
    - Intelligent mode selection per site
    - Comprehensive AI analysis pipeline
    - Multi-site concurrent processing
    - Database-driven source management
    - Performance monitoring and metrics
    """

    def __init__(self):
        # Initialize core components
        self.rate_limiter = RateLimiter()
        self.robots_checker = RobotsChecker()

        # AI analysis delegated to Analyst agent; no local model state

        # Load crawling configuration and initialize enhancement helpers
        crawling_config = get_crawling_config()
        enhancements = crawling_config.enhancements

        self.user_agent_provider = None
        if enhancements.enable_user_agent_rotation:
            try:
                self.user_agent_provider = UserAgentProvider(
                    pool=enhancements.user_agent_pool,
                    per_domain=enhancements.per_domain_user_agents,
                )
                logger.info("✅ User agent rotation enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize user agent provider: {e}")

        self.proxy_manager = None
        if enhancements.enable_proxy_pool and enhancements.proxy_pool:
            try:
                self.proxy_manager = ProxyManager(enhancements.proxy_pool)
                logger.info("✅ Proxy pool enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize proxy manager: {e}")

        # PIA SOCKS5 proxy support (alternative to proxy pool)
        self.pia_socks5_manager = None
        if enhancements.enable_pia_socks5:
            try:
                from .enhancements import PIASocks5Manager

                self.pia_socks5_manager = PIASocks5Manager(
                    username=enhancements.pia_socks5_username,
                    password=enhancements.pia_socks5_password,
                )
                logger.info("✅ PIA SOCKS5 proxy enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize PIA SOCKS5 manager: {e}")

        self.stealth_factory = None
        if enhancements.enable_stealth_headers and enhancements.stealth_profiles:
            try:
                self.stealth_factory = StealthBrowserFactory(
                    enhancements.stealth_profiles
                )
                logger.info("✅ Stealth headers enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize stealth factory: {e}")

        self.modal_handler = None
        if enhancements.enable_modal_handler:
            try:
                consent_cookie = enhancements.consent_cookie or {}
                cookie_name = consent_cookie.get("name", "justnews_cookie_consent")
                cookie_value = consent_cookie.get("value", "1")
                enable_cookie_injection = consent_cookie.get("enabled", True)
                self.modal_handler = ModalHandler(
                    enable_cookie_injection=enable_cookie_injection,
                    consent_cookie_name=cookie_name,
                    consent_cookie_value=cookie_value,
                )
                logger.info("✅ Modal handler enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize modal handler: {e}")

        self.paywall_detector = None
        if enhancements.enable_paywall_detector:
            try:
                paywall_config = enhancements.paywall_detector
                enable_remote = getattr(paywall_config, "enable_remote_analysis", False)
                max_remote_chars = getattr(paywall_config, "max_remote_chars", 6000)
                self.paywall_detector = PaywallDetector(
                    enable_remote_analysis=enable_remote,
                    max_remote_chars=max_remote_chars,
                )
                logger.info("✅ Paywall detector enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize paywall detector: {e}")

        # Crawling components
        self.multi_site_crawler = MultiSiteCrawler()
        self.site_strategies = {}  # Cache for site-specific strategies

        # Performance monitoring
        self.performance_monitor = get_performance_monitor()
        self.performance_optimizer = PerformanceOptimizer(self.performance_monitor)
        # Initialize performance metrics tracking
        import time

        self.performance_metrics = {
            "start_time": time.time(),
            "articles_processed": 0,
            "sites_crawled": 0,
            "errors": 0,
            "mode_usage": {
                "ai_enhanced": 0,
                "generic": 0,
                "crawl4ai_profiled": 0,
            },
        }

        # Start monitoring if enabled
        if (
            os.environ.get("UNIFIED_CRAWLER_PERFORMANCE_MONITORING", "true").lower()
            == "true"
        ):
            start_performance_monitoring(interval_seconds=60)

        # Initialize database connection and performance table
        try:
            initialize_connection_pool()
            create_crawling_performance_table()
            logger.info("✅ Database connection pool and performance table initialized")
        except Exception as e:
            logger.warning(
                f"⚠️ Database initialization failed (crawler will work without performance tracking): {e}"
            )
            # Continue without database - crawler can still work via MCP bus

        # Strategy optimization cache
        self.strategy_cache = {}
        self.performance_history = {}

        # Background cleanup management
        self.cleanup_task = None
        self._start_background_cleanup()

        # HITL integration controls
        def _parse_int(env_key: str, default: int, minimum: int) -> int:
            try:
                return max(minimum, int(os.environ.get(env_key, str(default))))
            except (TypeError, ValueError):
                return default

        self.hitl_base_url = (
            os.environ.get("HITL_SERVICE_URL")
            or os.environ.get("HITL_SERVICE_ADDRESS")
            or "http://localhost:8019"
        ).rstrip("/")
        self.hitl_enabled = (
            os.environ.get("ENABLE_HITL_PIPELINE", "true").lower() != "false"
        )
        self.hitl_stats_interval = _parse_int("HITL_STATS_INTERVAL_SECONDS", 60, 0)
        self.hitl_backoff_seconds = _parse_int("HITL_FAILURE_BACKOFF_SECONDS", 180, 30)
        self._hitl_last_stats_check = 0.0
        self._hitl_failure_streak = 0
        self._hitl_suspended_until = 0.0

    def _start_background_cleanup(self):
        """Start background cleanup task - disabled to prevent conflicts with async context manager"""
        # Background cleanup disabled - cleanup is now handled by async context manager
        # which is more reliable and prevents process accumulation
        pass

    async def _periodic_cleanup(self):
        """Run periodic cleanup every 30 seconds"""
        while True:
            try:
                await self._cleanup_orphaned_processes()
                await asyncio.sleep(30)  # Clean every 30 seconds
            except Exception as e:
                logger.debug(f"Periodic cleanup failed: {e}")
                await asyncio.sleep(30)

    async def _cleanup_orphaned_processes(self):
        """Aggressively cleanup orphaned browser processes - only kill very old processes"""
        try:
            import os

            # Kill Chrome processes older than 10 minutes (very conservative)
            try:
                import psutil

                now_ts = time.time()
                current_pid = os.getpid()
                cleaned_count = 0
                for proc in psutil.process_iter(
                    attrs=["pid", "name", "cmdline", "create_time"]
                ):
                    try:
                        info = proc.info
                        name = (info.get("name") or "").lower()
                        cmdline = " ".join(info.get("cmdline") or [])
                        if (
                            "chrome" not in name
                            and "chromium" not in name
                            and "chrome" not in cmdline
                        ):
                            continue

                        # Only consider processes that are descendants of this process
                        parents = [p.pid for p in proc.parents()]
                        if current_pid not in parents:
                            continue

                        # Age check
                        etime = int(now_ts - (info.get("create_time") or now_ts))
                        if etime > 600:  # 10 minutes conservative limit
                            proc.terminate()
                            cleaned_count += 1
                            logger.debug(
                                f"Cleaned up very old Chrome process {proc.pid} (age: {etime}s)"
                            )
                    except (
                        psutil.NoSuchProcess,
                        psutil.AccessDenied,
                        psutil.ZombieProcess,
                    ):
                        continue
                if cleaned_count > 0:
                    logger.info(f"Cleaned up {cleaned_count} very old Chrome processes")
            except Exception as e:
                logger.debug(f"Chrome cleanup failed: {e}")

            # Kill Playwright driver processes older than 15 minutes
            try:
                import psutil

                now_ts = time.time()
                current_pid = os.getpid()
                for proc in psutil.process_iter(
                    attrs=["pid", "name", "cmdline", "create_time"]
                ):
                    try:
                        cmdline = " ".join(proc.info.get("cmdline") or [])
                        if "run-driver" not in cmdline and "playwright" not in cmdline:
                            continue
                        parents = [p.pid for p in proc.parents()]
                        if current_pid not in parents:
                            continue
                        etime = int(now_ts - (proc.info.get("create_time") or now_ts))
                        if etime > 900:  # 15 minutes
                            proc.terminate()
                            logger.debug(
                                f"Cleaned up very old Playwright driver {proc.pid}"
                            )
                    except (
                        psutil.NoSuchProcess,
                        psutil.AccessDenied,
                        psutil.ZombieProcess,
                    ):
                        continue
            except Exception as e:
                logger.debug(f"Playwright cleanup failed: {e}")

            # Fallback for environments without psutil or when unit tests patch subprocess calls.
            # This replicates earlier behaviour that used `pgrep`/`ps` shell tools.
            try:
                import signal
                import subprocess

                # Find chrome-like pids
                pgrep_proc = subprocess.run(
                    ["pgrep", "-f", "chrome"], capture_output=True, text=True, timeout=5
                )
                if pgrep_proc.returncode == 0 and pgrep_proc.stdout:
                    pids = [
                        int(pid.strip())
                        for pid in pgrep_proc.stdout.splitlines()
                        if pid.strip().isdigit()
                    ]
                    for pid in pids:
                        try:
                            # Get elapsed time via ps (seconds)
                            ps_proc = subprocess.run(
                                ["ps", "-p", str(pid), "-o", "etimes="],
                                capture_output=True,
                                text=True,
                                timeout=5,
                            )
                            if ps_proc.returncode != 0:
                                continue
                            age_seconds = int(ps_proc.stdout.strip() or 0)
                            if age_seconds > 600:
                                try:
                                    os.kill(pid, signal.SIGTERM)
                                    logger.debug(
                                        f"Cleaned up shell-detected Chrome process {pid} (age: {age_seconds}s)"
                                    )
                                except Exception:
                                    continue
                        except Exception:
                            continue

                # Find playwright pids
                pgrep_proc = subprocess.run(
                    ["pgrep", "-f", "playwright.*run-driver"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if pgrep_proc.returncode == 0 and pgrep_proc.stdout:
                    pids = [
                        int(pid.strip())
                        for pid in pgrep_proc.stdout.splitlines()
                        if pid.strip().isdigit()
                    ]
                    for pid in pids:
                        try:
                            ps_proc = subprocess.run(
                                ["ps", "-p", str(pid), "-o", "etimes="],
                                capture_output=True,
                                text=True,
                                timeout=5,
                            )
                            if ps_proc.returncode != 0:
                                continue
                            age_seconds = int(ps_proc.stdout.strip() or 0)
                            if age_seconds > 900:
                                try:
                                    os.kill(pid, signal.SIGTERM)
                                    logger.debug(
                                        f"Cleaned up shell-detected Playwright process {pid} (age: {age_seconds}s)"
                                    )
                                except Exception:
                                    continue
                        except Exception:
                            continue

            except Exception as e:
                logger.debug(f"Shell-based process cleanup failed: {e}")

        except Exception as e:
            logger.warning(f"Orphaned process cleanup failed: {e}")

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup resources"""
        await self._cleanup()

    async def _cleanup(self):
        """Cleanup all resources"""
        try:
            # Cancel background cleanup task
            if self.cleanup_task and not self.cleanup_task.done():
                self.cleanup_task.cancel()
                try:
                    await self.cleanup_task
                except asyncio.CancelledError:
                    pass

            # Final aggressive cleanup - kill all browser processes from this session
            await self._cleanup_orphaned_processes()

            # Force kill any remaining processes - be more aggressive here
            import subprocess

            try:
                # Kill all Chrome processes (they should all be from this crawler instance)
                subprocess.run(
                    ["pkill", "-9", "-f", "chrome"], timeout=10, capture_output=True
                )
                # Kill Playwright drivers
                subprocess.run(
                    ["pkill", "-9", "-f", "playwright.*run-driver"],
                    timeout=10,
                    capture_output=True,
                )
                logger.info(
                    "Forced cleanup of all browser processes from crawler session"
                )
            except subprocess.TimeoutExpired:
                logger.warning("Force cleanup timed out")
            except Exception as e:
                logger.debug(f"Force cleanup failed: {e}")

        except Exception as e:
            logger.warning(f"Resource cleanup failed: {e}")

    async def _load_ai_models(self):
        """No-op stub: AI model loading handled by GPU Orchestrator"""
        return

    async def _determine_optimal_strategy(self, site_config: SiteConfig) -> str:
        """
        Determine optimal crawling strategy based on site characteristics and performance history

        Uses performance data to optimize strategy selection dynamically.
        """

        domain = site_config.domain.lower()
        source_id = site_config.source_id

        # Check cache first
        cache_key = f"{domain}_{source_id}"
        if cache_key in self.strategy_cache:
            return self.strategy_cache[cache_key]

        # Get performance history for this source
        if source_id:
            performance_history = get_source_performance_history(source_id, limit=5)
            if performance_history:
                # Calculate average performance by strategy
                strategy_performance = {}
                for record in performance_history:
                    strategy = record["strategy_used"]
                    if strategy not in strategy_performance:
                        strategy_performance[strategy] = []
                    strategy_performance[strategy].append(record["articles_per_second"])

                # Find best performing strategy
                best_strategy = None
                best_avg_performance = 0

                for strategy, performances in strategy_performance.items():
                    # Skip deprecated strategies
                    if strategy == "ultra_fast":
                        continue
                        
                    avg_performance = sum(performances) / len(performances)
                    if avg_performance > best_avg_performance:
                        best_avg_performance = avg_performance
                        best_strategy = strategy

                if best_strategy and best_avg_performance > 0.1:  # Minimum threshold
                    self.strategy_cache[cache_key] = best_strategy
                    logger.info(
                        f"🎯 Using performance-optimized strategy for {domain}: {best_strategy} ({best_avg_performance:.2f} articles/sec)"
                    )
                    return best_strategy

        # 1. Check for pre-defined ultra-fast sites
        # These are high-volume, well-structured sites with dedicated parsers
        # DISABLED: User requested to disable forced ultra_fast mode
        # if any(d in domain for d in ["bbc.co.uk", "cnn.com", "reuters.com"]):
        #     return "ultra_fast"

        # Force AI-enhanced for known complex/paywalled sites
        if any(
            d in domain
            for d in [
                "nytimes.com",
                "wsj.com",
                "washingtonpost.com",
                "theatlantic.com",
                "newyorker.com",
            ]
        ):
            logger.info(
                f"Found known complex site {domain}, forcing 'ai_enhanced' strategy."
            )
            return "ai_enhanced"

        # 2. Check database for historical performance
        if domain not in self.performance_history:
            self.performance_history[domain] = get_source_performance_history(domain)

        # Default to generic strategy
        return "generic"

    @traced(name="crawler.mode.ai_enhanced")
    async def _crawl_ai_enhanced_mode(
        self, site_config: SiteConfig, max_articles: int = 25
    ) -> list[dict]:
        """AI-enhanced crawling stub: delegates to generic mode"""
        logger.info(
            f"🤖 AI-enhanced crawling stub: delegating to generic mode for {site_config.name}"
        )
        try:
            articles = await self._crawl_generic_mode(site_config, max_articles)
            self.performance_metrics["mode_usage"]["ai_enhanced"] += 1
            return articles
        finally:
            # Always cleanup after AI-enhanced crawling
            await self._cleanup_orphaned_processes()

    async def _crawl_generic_mode(
        self, site_config: SiteConfig, max_articles: int = 25
    ) -> list[dict]:
        """
        Generic crawling mode with Crawl4AI-first strategy
        Supports any news source with graceful fallbacks
        """
        logger.info(f"🌐 Generic crawling: {site_config.name}")

        try:
            crawling_config = get_crawling_config()
            enhancements = crawling_config.enhancements
            crawler = GenericSiteCrawler(
                site_config,
                concurrent_browsers=2,
                batch_size=8,
                user_agent_provider=self.user_agent_provider,
                proxy_manager=self.proxy_manager or self.pia_socks5_manager,
                stealth_factory=self.stealth_factory,
                modal_handler=self.modal_handler,
                paywall_detector=self.paywall_detector,
                enable_stealth_headers=enhancements.enable_stealth_headers,
            )
            articles = await crawler.crawl_site(max_articles)

            self.performance_metrics["mode_usage"]["generic"] += 1
            return articles

        except Exception as e:
            logger.error(f"Generic crawling failed for {site_config.name}: {e}")
            return []
        finally:
            # Always cleanup after generic crawling
            await self._cleanup_orphaned_processes()

    async def _crawl_with_profile(
        self,
        site_config: SiteConfig,
        profile: dict[str, Any],
        max_articles: int | None,
    ) -> list[dict[str, Any]]:
        """Execute a crawl using an explicit profile override."""
        effective_limit = max_articles or profile.get("max_pages") or 25
        engine = str(profile.get("engine", "crawl4ai")).lower() or "crawl4ai"

        if engine == "generic":
            return await self._crawl_generic_mode(site_config, effective_limit)

        if engine != "crawl4ai":
            logger.warning(
                "Unknown crawl engine '%s' for %s; falling back to generic",
                engine,
                site_config.name,
            )
            return await self._crawl_generic_mode(site_config, effective_limit)

        try:
            from .crawl4ai_adapter import crawl_site_with_crawl4ai
        except ImportError:
            logger.warning(
                "Crawl4AI integration not available; falling back to generic crawl for %s",
                site_config.name,
            )
            return await self._crawl_generic_mode(site_config, effective_limit)

        try:
            # Respect profile-level 'follow_external' override (or let the adapter
            # consult environment variables when None).
            return await crawl_site_with_crawl4ai(
                site_config,
                profile,
                effective_limit,
                follow_external=profile.get("follow_external", None),
            )
        except Exception as exc:  # noqa: BLE001 - resilience over strict typing
            logger.error(
                "Crawl4AI profiled crawl failed for %s: %s", site_config.name, exc
            )
            return []
        finally:
            await self._cleanup_orphaned_processes()

    async def _apply_ai_analysis(self, article: dict) -> dict:
        """Delegate AI analysis to Analyst agent via MCP bus"""
        content = article.get("content", "")
        if not content or len(content) < 100:
            return article
        try:
            sentiment_score = call_analyst_tool("score_sentiment", content)
            article["sentiment"] = {"score": sentiment_score}
            topics = call_analyst_tool("extract_topics", content)
            article["topics"] = topics
            article["ai_analysis_applied"] = True
        except Exception as e:
            logger.error(f"Remote AI analysis failed: {e}")
        return article

    @traced(name="crawler.crawl_site", record_args=True)
    async def crawl_site(
        self, site_config: SiteConfig, max_articles: int = 25
    ) -> list[dict]:
        """
        Crawl a single site using the optimal strategy
        """
        strategy = await self._determine_optimal_strategy(site_config)

        if strategy == "ai_enhanced":
            return await self._crawl_ai_enhanced_mode(site_config, max_articles)
        else:  # generic (fallback for everything else including deprecated "ultra_fast")
            return await self._crawl_generic_mode(site_config, max_articles)

    @traced(name="crawler.run_unified_crawl", record_args=True)
    async def run_unified_crawl(
        self,
        domains: list[str],
        max_articles_per_site: int = 25,
        concurrent_sites: int = 3,
        *,
        profile_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Main entry point for unified crawling - converts domains to SiteConfig objects and runs crawl
        """
        logger.info(f"🚀 Starting unified crawl for domains: {domains}")

        # Convert domains to SiteConfig objects
        site_configs = []
        for domain in domains:
            if isinstance(domain, list):
                domain = domain[0] if domain else ""
            try:
                # Get source info from database
                sources = get_sources_by_domain([domain])  # Pass as list
                if sources:
                    source = sources[0]  # Use first match
                    config = SiteConfig(source)
                    site_configs.append(config)
                else:
                    # Create basic config for unknown domains
                    logger.warning(
                        f"No database entry for {domain}, creating basic config"
                    )
                    parsed = urlparse(domain)
                    if parsed.scheme and parsed.netloc:
                        fallback_domain = parsed.netloc
                        fallback_url = domain
                    else:
                        fallback_domain = domain
                        fallback_url = f"https://{domain}" if domain else ""

                    config = SiteConfig(
                        {
                            "id": None,
                            "name": fallback_domain or domain or "unknown",
                            "domain": fallback_domain,
                            "url": fallback_url,
                            "crawling_strategy": "generic",
                        }
                    )
                    site_configs.append(config)
            except Exception as e:
                logger.error(f"Failed to create config for {domain}: {e}")
                continue

        if not site_configs:
            logger.error("❌ No valid site configurations created")
            return {"error": "No valid domains provided"}

        # Execute the crawl
        return await self.crawl_multiple_sites(
            site_configs,
            max_articles_per_site,
            concurrent_sites,
            profile_overrides=profile_overrides,
        )

    async def crawl_multiple_sites(
        self,
        site_configs: list[SiteConfig],
        max_articles_per_site: int = 25,
        concurrent_sites: int = 3,
        *,
        profile_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Crawl multiple sites concurrently using optimal strategies."""
        logger.info(f"🚀 Starting unified multi-site crawl: {len(site_configs)} sites")

        start_time = time.time()
        site_articles: dict[str, list[dict[str, Any]]] = {}
        site_metrics: dict[str, dict[str, Any]] = {}
        ingestion_totals = {
            "new_articles": 0,
            "duplicates": 0,
            "errors": 0,
            "paywalls": 0,
        }
        total_successful = 0
        total_candidates = 0
        all_articles: list[dict[str, Any]] = []

        resolved_profiles: dict[str, dict[str, Any]] = {}
        if profile_overrides:
            resolved_profiles = {
                (key or "").lower(): value
                for key, value in profile_overrides.items()
                if key
            }

        def _lookup_profile(config: SiteConfig) -> dict[str, Any] | None:
            if not resolved_profiles:
                return None
            candidates = [
                (config.domain or "").lower(),
                (config.name or "").lower(),
            ]
            for candidate in candidates:
                if candidate and candidate in resolved_profiles:
                    return resolved_profiles[candidate]
            return None

        semaphore = asyncio.Semaphore(max(1, concurrent_sites))
        aggregation_lock = asyncio.Lock()

        async def crawl_site_with_limit(
            site_config: SiteConfig,
            site_budget: int | None = None,
        ):
            nonlocal total_successful, total_candidates
            async with semaphore:
                domain_key = site_config.domain or site_config.name or "unknown"
                site_candidates = 0
                site_ingested = 0
                site_duplicates = 0
                site_errors = 0
                site_paywalls = 0
                site_articles_local: list[dict[str, Any]] = []
                site_details: list[dict[str, Any]] = []
                seen_keys: set[str] = set()
                remaining_budget: int | None = (
                    site_budget
                    if site_budget is not None
                    else (
                        max_articles_per_site
                        if max_articles_per_site is not None
                        else None
                    )
                )
                exhaustion_reason: str | None = None
                batches_run = 0

                profile_override = _lookup_profile(site_config)
                site_started_at = time.time()
                strategy_used = (
                    "crawl4ai_profiled"
                    if (
                        profile_override
                        and profile_override.get("engine", "crawl4ai") != "generic"
                    )
                    else "generic"
                )

                dedupe_replacement_factor = max(
                    1, int(os.environ.get("UNIFIED_CRAWLER_DEDUPE_REPLACEMENT_FACTOR", "3"))
                )
                max_candidate_request = max(
                    1, int(os.environ.get("UNIFIED_CRAWLER_MAX_REQUEST_CAP", "150"))
                )
                adaptive_depth_enabled = (
                    str(os.environ.get("UNIFIED_CRAWLER_ADAPTIVE_DEPTH_ENABLED", "true"))
                    .strip()
                    .lower()
                    in {"1", "true", "yes", "on"}
                )
                try:
                    adaptive_initial_depth = max(
                        0,
                        int(
                            os.environ.get(
                                "UNIFIED_CRAWLER_ADAPTIVE_DEPTH_INITIAL", "2"
                            )
                        ),
                    )
                except (TypeError, ValueError):
                    adaptive_initial_depth = 2
                try:
                    adaptive_fallback_depth = max(
                        adaptive_initial_depth,
                        int(
                            os.environ.get(
                                "UNIFIED_CRAWLER_ADAPTIVE_DEPTH_FALLBACK", "3"
                            )
                        ),
                    )
                except (TypeError, ValueError):
                    adaptive_fallback_depth = max(adaptive_initial_depth, 3)
                try:
                    adaptive_max_batches = max(
                        1,
                        int(
                            os.environ.get(
                                "UNIFIED_CRAWLER_ADAPTIVE_DEPTH_MAX_BATCHES", "2"
                            )
                        ),
                    )
                except (TypeError, ValueError):
                    adaptive_max_batches = 2
                try:
                    adaptive_min_fill_ratio = float(
                        os.environ.get("UNIFIED_CRAWLER_ADAPTIVE_MIN_FILL_RATIO", "0.9")
                    )
                except (TypeError, ValueError):
                    adaptive_min_fill_ratio = 0.9
                adaptive_min_fill_ratio = max(0.0, min(adaptive_min_fill_ratio, 1.0))

                def _candidate_request_cap() -> int:
                    base = (
                        remaining_budget
                        if remaining_budget is not None and remaining_budget > 0
                        else max_articles_per_site
                    )
                    base = base or max_articles_per_site or 25
                    base = max(1, int(base))
                    return max(1, min(max_candidate_request, base * dedupe_replacement_factor))

                def _build_adaptive_depth_profile(
                    base_profile: dict[str, Any] | None,
                ) -> tuple[dict[str, Any] | None, bool]:
                    profile: dict[str, Any] = dict(base_profile or {})
                    if not profile:
                        profile = {"engine": "crawl4ai", "mode": "landing"}

                    engine = str(profile.get("engine", "crawl4ai")).strip().lower()
                    if engine == "generic":
                        return None, False
                    if engine not in {"", "crawl4ai"}:
                        return None, False
                    profile["engine"] = "crawl4ai"

                    extra = dict(profile.get("extra") or {})
                    raw_depth = extra.get("crawl_depth")
                    try:
                        current_depth = (
                            max(0, int(raw_depth))
                            if raw_depth is not None
                            else adaptive_initial_depth
                        )
                    except (TypeError, ValueError):
                        current_depth = adaptive_initial_depth

                    target_depth = max(current_depth, adaptive_fallback_depth)
                    if target_depth <= current_depth and raw_depth is not None:
                        return None, False

                    extra["crawl_depth"] = target_depth
                    profile["extra"] = extra
                    profile["follow_internal_links"] = True

                    request_cap = _candidate_request_cap()
                    try:
                        existing_pages = int(profile.get("max_pages") or 0)
                    except (TypeError, ValueError):
                        existing_pages = 0
                    profile["max_pages"] = max(existing_pages, request_cap)
                    return profile, True

                async def _ingest_with_replacements(filtered_batch: list[dict[str, Any]]) -> int:
                    """Ingest candidates in chunks, pulling replacements from the same batch when dedupe occurs."""
                    nonlocal site_candidates
                    nonlocal site_ingested
                    nonlocal site_duplicates
                    nonlocal site_errors
                    nonlocal remaining_budget
                    nonlocal site_articles_local
                    nonlocal site_details

                    total_new_articles = 0
                    cursor = 0
                    while cursor < len(filtered_batch):
                        if remaining_budget is not None and remaining_budget <= 0:
                            break

                        chunk_size = (
                            max(1, remaining_budget)
                            if remaining_budget is not None
                            else max(1, len(filtered_batch) - cursor)
                        )
                        chunk = filtered_batch[cursor : cursor + chunk_size]
                        cursor += chunk_size
                        if not chunk:
                            break

                        await self._submit_hitl_candidates(chunk, site_config)
                        site_candidates += len(chunk)

                        ingestion_result = await self._ingest_articles(chunk)
                        site_articles_local.extend(chunk)
                        site_details.extend(ingestion_result.get("details", []))
                        site_ingested += ingestion_result["new_articles"]
                        site_duplicates += ingestion_result["duplicates"]
                        site_errors += ingestion_result["errors"]
                        total_new_articles += ingestion_result["new_articles"]

                        if remaining_budget is not None:
                            remaining_budget = max(
                                remaining_budget - ingestion_result["new_articles"],
                                0,
                            )

                    return total_new_articles

                def _filter_paywall_skips(
                    batch: list[dict[str, Any]],
                ) -> tuple[list[dict[str, Any]], int]:
                    """Separate paywalled articles from the batch and record skip metadata."""
                    nonlocal site_articles_local, site_details, site_paywalls
                    if not batch:
                        return batch, 0

                    paywall_skips = [
                        article for article in batch if article.get("skip_ingest")
                    ]
                    if paywall_skips:
                        for article in paywall_skips:
                            metadata = article.setdefault("extraction_metadata", {})
                            paywall_meta = metadata.setdefault("paywall_detection", {})
                            paywall_meta["skipped"] = True
                            article["paywall_flag"] = True
                            article["ingestion_status"] = "paywall_skipped"
                        site_articles_local.extend(paywall_skips)
                        site_details.extend(
                            {"url": article.get("url"), "status": "paywall_skipped"}
                            for article in paywall_skips
                        )
                        site_paywalls += len(paywall_skips)

                    remaining = [
                        article for article in batch if not article.get("skip_ingest")
                    ]
                    return remaining, len(paywall_skips)

                try:
                    if (
                        profile_override
                        and profile_override.get("engine", "crawl4ai") != "generic"
                    ):
                        while True:
                            if remaining_budget is not None and remaining_budget <= 0:
                                exhaustion_reason = "limit_reached"
                                break
                            if batches_run >= MAX_SITE_BATCHES:
                                exhaustion_reason = "max_batches_reached"
                                break

                            request_cap = _candidate_request_cap()
                            raw_batch = await self._crawl_with_profile(
                                site_config,
                                profile_override,
                                request_cap,
                            )
                            batches_run += 1
                            self.performance_metrics["mode_usage"]["crawl4ai_profiled"] += 1

                            filtered_batch: list[dict[str, Any]] = []
                            for article in raw_batch or []:
                                key = (
                                    article.get("url_hash")
                                    or article.get("normalized_url")
                                    or article.get("url")
                                )
                                if key and key in seen_keys:
                                    continue
                                if key:
                                    seen_keys.add(key)
                                filtered_batch.append(article)

                            if not filtered_batch:
                                exhaustion_reason = "no_new_candidates"
                                break

                            filtered_batch, paywall_skipped = _filter_paywall_skips(
                                filtered_batch
                            )

                            if not filtered_batch:
                                if paywall_skipped:
                                    if (
                                        remaining_budget is not None
                                        and remaining_budget <= 0
                                    ):
                                        exhaustion_reason = "limit_reached"
                                        break
                                    continue
                                exhaustion_reason = "no_new_candidates"
                                break

                            batch_new = await _ingest_with_replacements(filtered_batch)

                            if remaining_budget is not None and remaining_budget <= 0:
                                exhaustion_reason = "limit_reached"
                                break

                            if batch_new == 0:
                                # Dedupe/paywall dominated batch; try another batch until max site batches.
                                exhaustion_reason = "ingestion_stalled"
                                continue
                    else:
                        while True:
                            if remaining_budget is not None and remaining_budget <= 0:
                                exhaustion_reason = "limit_reached"
                                break
                            if batches_run >= MAX_SITE_BATCHES:
                                exhaustion_reason = "max_batches_reached"
                                break

                            request_cap = _candidate_request_cap()

                            raw_batch = await self.crawl_site(site_config, request_cap)
                            batches_run += 1
                            if not raw_batch:
                                exhaustion_reason = "no_candidates"
                                break

                            filtered_batch: list[dict[str, Any]] = []
                            for article in raw_batch:
                                key = (
                                    article.get("url_hash")
                                    or article.get("normalized_url")
                                    or article.get("url")
                                )
                                if key and key in seen_keys:
                                    continue
                                if key:
                                    seen_keys.add(key)
                                filtered_batch.append(article)

                            filtered_batch, paywall_skipped = _filter_paywall_skips(
                                filtered_batch
                            )

                            if not filtered_batch:
                                if paywall_skipped:
                                    if (
                                        remaining_budget is not None
                                        and remaining_budget <= 0
                                    ):
                                        exhaustion_reason = "limit_reached"
                                        break
                                    continue
                                exhaustion_reason = "no_new_candidates"
                                break

                            if remaining_budget is not None:
                                filtered_batch = filtered_batch[:request_cap]

                            batch_new = await _ingest_with_replacements(filtered_batch)

                            if batch_new == 0:
                                exhaustion_reason = "ingestion_stalled"
                                continue

                    target_articles = (
                        site_budget
                        if site_budget is not None
                        else (max_articles_per_site or 25)
                    )
                    min_expected_articles = max(
                        1, int(target_articles * adaptive_min_fill_ratio)
                    )
                    can_retry_depth = (
                        adaptive_depth_enabled
                        and site_ingested < min_expected_articles
                        and (remaining_budget is None or remaining_budget > 0)
                        and exhaustion_reason
                        in {
                            "no_candidates",
                            "no_new_candidates",
                            "ingestion_stalled",
                            "max_batches_reached",
                            "paywalls_only",
                        }
                    )

                    if can_retry_depth:
                        adaptive_profile, profile_changed = _build_adaptive_depth_profile(
                            profile_override
                        )
                        if adaptive_profile and profile_changed:
                            logger.info(
                                "↗️ Adaptive depth fallback for %s (ingested=%s/%s, reason=%s, depth=%s)",
                                site_config.name,
                                site_ingested,
                                target_articles,
                                exhaustion_reason,
                                (adaptive_profile.get("extra") or {}).get("crawl_depth"),
                            )
                            adaptive_batches = 0
                            while adaptive_batches < adaptive_max_batches:
                                if remaining_budget is not None and remaining_budget <= 0:
                                    exhaustion_reason = "limit_reached"
                                    break

                                request_cap = _candidate_request_cap()
                                raw_batch = await self._crawl_with_profile(
                                    site_config,
                                    adaptive_profile,
                                    request_cap,
                                )
                                adaptive_batches += 1
                                batches_run += 1
                                self.performance_metrics["mode_usage"][
                                    "crawl4ai_profiled"
                                ] += 1

                                filtered_batch: list[dict[str, Any]] = []
                                for article in raw_batch or []:
                                    key = (
                                        article.get("url_hash")
                                        or article.get("normalized_url")
                                        or article.get("url")
                                    )
                                    if key and key in seen_keys:
                                        continue
                                    if key:
                                        seen_keys.add(key)
                                    filtered_batch.append(article)

                                if not filtered_batch:
                                    exhaustion_reason = "adaptive_no_new_candidates"
                                    break

                                filtered_batch, paywall_skipped = _filter_paywall_skips(
                                    filtered_batch
                                )
                                if not filtered_batch:
                                    if paywall_skipped:
                                        exhaustion_reason = "adaptive_paywalls_only"
                                    else:
                                        exhaustion_reason = "adaptive_no_new_candidates"
                                    break

                                batch_new = await _ingest_with_replacements(filtered_batch)
                                if remaining_budget is not None and remaining_budget <= 0:
                                    exhaustion_reason = "limit_reached"
                                    break
                                if batch_new == 0:
                                    exhaustion_reason = "adaptive_ingestion_stalled"
                                    continue

                            if site_ingested >= min_expected_articles and (
                                remaining_budget is None or remaining_budget > 0
                            ):
                                exhaustion_reason = "adaptive_depth_target_reached"

                        if (
                            exhaustion_reason is None
                            and site_ingested == 0
                            and site_paywalls > 0
                        ):
                            exhaustion_reason = "paywalls_only"

                        if exhaustion_reason is None:
                            exhaustion_reason = (
                                "limit_reached"
                                if remaining_budget is not None
                                and remaining_budget <= 0
                                else None
                            )

                except Exception as exc:  # noqa: BLE001 - resilience over strict typing
                    exhaustion_reason = exhaustion_reason or "error"
                    site_errors += 1
                    logger.error(f"Crawl failed for {domain_key}: {exc}")

                finally:
                    should_persist_paywall = (
                        site_paywalls > 0
                        and site_ingested == 0
                        and (site_config.domain or site_config.source_id is not None)
                    )
                    if should_persist_paywall:
                        try:
                            status_changed = record_paywall_detection(
                                source_id=site_config.source_id,
                                domain=site_config.domain,
                                skip_count=site_paywalls,
                                threshold=PAYWALL_SKIP_ACTIVATION_THRESHOLD,
                                paywall_type="hard",
                            )
                            if status_changed:
                                logger.info(
                                    "🚫 Marked %s as paywalled after %s skipped articles",
                                    domain_key,
                                    site_paywalls,
                                )
                        except Exception as err:  # pragma: no cover - defensive logging
                            logger.debug(
                                "Unable to persist paywall state for %s: %s",
                                domain_key,
                                err,
                            )

                    async with aggregation_lock:
                        site_articles[domain_key] = site_articles_local
                        site_metrics[domain_key] = {
                            "attempted": site_ingested,
                            "candidates": site_candidates,
                            "ingested": site_ingested,
                            "duplicates": site_duplicates,
                            "errors": site_errors,
                            "paywalls": site_paywalls,
                            "exhaustion_reason": exhaustion_reason,
                            "details": site_details,
                        }
                        ingestion_totals["new_articles"] += site_ingested
                        ingestion_totals["duplicates"] += site_duplicates
                        ingestion_totals["errors"] += site_errors
                        ingestion_totals["paywalls"] += site_paywalls
                        total_successful += site_ingested
                        total_candidates += site_candidates
                        all_articles.extend(site_articles_local)
                        self.performance_metrics["articles_processed"] += site_ingested
                        self.performance_metrics["sites_crawled"] += 1
                        self.performance_metrics["errors"] += site_errors
                        logger.info(
                            "🏁 Completed %s: %s ingested / %s candidates (reason=%s)",
                            site_config.name,
                            site_ingested,
                            site_candidates,
                            exhaustion_reason or "limit_reached",
                        )

                    await self._cleanup_orphaned_processes()

                try:
                    record_crawling_performance(
                        source_id=site_config.source_id,
                        domain=site_config.domain or domain_key,
                        strategy_used=strategy_used,
                        articles_processed=site_ingested,
                        duration_seconds=max(time.time() - site_started_at, 1e-6),
                    )
                except Exception as perf_exc:  # noqa: BLE001 - non-critical telemetry
                    logger.debug(
                        "Unable to record crawling performance for %s: %s",
                        domain_key,
                        perf_exc,
                    )

        tasks = [crawl_site_with_limit(config) for config in site_configs]
        await asyncio.gather(*tasks, return_exceptions=True)

        constrained_backfill_enabled = (
            str(
                os.environ.get(
                    "UNIFIED_CRAWLER_CONSTRAINED_BACKFILL_ENABLED", "true"
                )
            )
            .strip()
            .lower()
            in {"1", "true", "yes", "on"}
        )
        try:
            constrained_max_articles = max(
                1,
                int(
                    os.environ.get(
                        "UNIFIED_CRAWLER_CONSTRAINED_MAX_ARTICLES_PER_SITE", "10"
                    )
                ),
            )
        except (TypeError, ValueError):
            constrained_max_articles = 10
        try:
            constrained_backfill_max_sites = max(
                1,
                int(
                    os.environ.get(
                        "UNIFIED_CRAWLER_CONSTRAINED_BACKFILL_MAX_SITES", "12"
                    )
                ),
            )
        except (TypeError, ValueError):
            constrained_backfill_max_sites = 12
        try:
            constrained_backfill_source_limit = max(
                10,
                int(
                    os.environ.get(
                        "UNIFIED_CRAWLER_CONSTRAINED_BACKFILL_SOURCE_LIMIT", "200"
                    )
                ),
            )
        except (TypeError, ValueError):
            constrained_backfill_source_limit = 200

        constrained_mode = (
            constrained_backfill_enabled
            and max_articles_per_site is not None
            and int(max_articles_per_site) <= constrained_max_articles
        )

        if constrained_mode and site_configs:
            target_total_articles = len(site_configs) * int(max_articles_per_site)
            if total_successful < target_total_articles:
                remaining_target = target_total_articles - total_successful
                attempted_domains = {
                    (cfg.domain or cfg.name or "").strip().lower()
                    for cfg in site_configs
                    if (cfg.domain or cfg.name)
                }
                try:
                    constrained_backfill_max_zero_streak = max(
                        1,
                        int(
                            os.environ.get(
                                "UNIFIED_CRAWLER_CONSTRAINED_BACKFILL_MAX_ZERO_STREAK",
                                "4",
                            )
                        ),
                    )
                except (TypeError, ValueError):
                    constrained_backfill_max_zero_streak = 4

                priority_domains = [
                    d.strip().lower()
                    for d in os.environ.get(
                        "UNIFIED_CRAWLER_CONSTRAINED_BACKFILL_PRIORITY_DOMAINS",
                        "motherjones.com,slate.com,psychologytoday.com,news.yale.edu,news.berkeley.edu,time.com,elpais.com",
                    ).split(",")
                    if d.strip()
                ]
                priority_rank = {
                    domain: (len(priority_domains) - idx)
                    for idx, domain in enumerate(priority_domains)
                }

                def _source_health_score(source_row: dict[str, Any]) -> float:
                    domain_value = str(source_row.get("domain") or "").strip().lower()
                    heuristic = 0.0
                    if domain_value:
                        if domain_value in priority_rank:
                            heuristic += 100.0 + priority_rank[domain_value]
                        if domain_value.endswith(".edu") or domain_value.endswith(".gov"):
                            heuristic -= 3.0
                        news_tokens = (
                            "news",
                            "times",
                            "post",
                            "tribune",
                            "journal",
                            "guardian",
                            "herald",
                            "observer",
                        )
                        if any(token in domain_value for token in news_tokens):
                            heuristic += 1.0

                    identifier = source_row.get("id") or source_row.get("domain")
                    history = get_source_performance_history(identifier, limit=3)
                    if not history:
                        return heuristic
                    processed = [
                        max(0.0, float(item.get("articles_processed") or 0.0))
                        for item in history
                    ]
                    speeds = [
                        max(0.0, float(item.get("articles_per_second") or 0.0))
                        for item in history
                    ]
                    avg_processed = sum(processed) / len(processed) if processed else 0.0
                    avg_speed = sum(speeds) / len(speeds) if speeds else 0.0
                    return heuristic + avg_processed + avg_speed

                source_candidates = get_active_sources(
                    limit=constrained_backfill_source_limit,
                    include_paywalled=False,
                )
                ranked_candidates: list[tuple[float, int, dict[str, Any]]] = []
                for idx, source in enumerate(source_candidates):
                    domain = str(source.get("domain") or "").strip().lower()
                    if not domain or domain in attempted_domains:
                        continue
                    ranked_candidates.append((_source_health_score(source), idx, source))

                ranked_candidates.sort(key=lambda item: (item[0], -item[1]), reverse=True)

                backfill_used = 0
                zero_yield_streak = 0
                for score, _idx, source in ranked_candidates:
                    if total_successful >= target_total_articles:
                        break
                    if backfill_used >= constrained_backfill_max_sites:
                        break
                    if zero_yield_streak >= constrained_backfill_max_zero_streak:
                        logger.info(
                            "🔁 Constrained backfill early stop after %s consecutive zero-yield domains",
                            zero_yield_streak,
                        )
                        break

                    try:
                        replacement_config = SiteConfig(source)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Skipping backfill source due to config error: %s", exc)
                        continue

                    domain_key = (
                        replacement_config.domain
                        or replacement_config.name
                        or str(source.get("domain") or "")
                    ).strip().lower()
                    if not domain_key or domain_key in attempted_domains:
                        continue

                    attempted_domains.add(domain_key)
                    remaining_target = max(target_total_articles - total_successful, 0)
                    if remaining_target <= 0:
                        break

                    site_budget = min(int(max_articles_per_site), max(1, remaining_target))
                    logger.info(
                        "🔁 Constrained backfill: adding domain %s (score=%.3f, budget=%s, remaining_target=%s)",
                        domain_key,
                        score,
                        site_budget,
                        remaining_target,
                    )
                    before_total = total_successful
                    await crawl_site_with_limit(replacement_config, site_budget=site_budget)
                    after_total = total_successful
                    if after_total > before_total:
                        zero_yield_streak = 0
                    else:
                        zero_yield_streak += 1
                    backfill_used += 1

                if backfill_used > 0:
                    logger.info(
                        "🔁 Constrained backfill summary: added_sites=%s total_ingested=%s target=%s",
                        backfill_used,
                        total_successful,
                        target_total_articles,
                    )

        total_time = time.time() - start_time
        total_ingested = ingestion_totals["new_articles"]
        articles_per_second = total_ingested / total_time if total_time > 0 else 0

        summary = {
            "unified_crawl": True,
            "sites_crawled": len(site_articles),
            "total_articles_attempted": total_successful,
            "total_ingest_candidates": total_candidates,
            "total_articles": total_ingested,
            "articles_ingested": total_ingested,
            "duplicates_skipped": ingestion_totals["duplicates"],
            "ingestion_errors": ingestion_totals["errors"],
            "total_paywalls_detected": ingestion_totals["paywalls"],
            "processing_time_seconds": total_time,
            "articles_per_second": articles_per_second,
            "strategy_breakdown": self.performance_metrics["mode_usage"],
            "site_breakdown": {
                domain: metrics["ingested"] for domain, metrics in site_metrics.items()
            },
            "site_attempted_breakdown": {
                domain: metrics["attempted"] for domain, metrics in site_metrics.items()
            },
            "site_candidate_breakdown": {
                domain: metrics["candidates"]
                for domain, metrics in site_metrics.items()
                if metrics["candidates"]
            },
            "site_duplicate_breakdown": {
                domain: metrics["duplicates"]
                for domain, metrics in site_metrics.items()
                if metrics["duplicates"]
            },
            "site_error_breakdown": {
                domain: metrics["errors"]
                for domain, metrics in site_metrics.items()
                if metrics["errors"]
            },
            "site_paywall_breakdown": {
                domain: metrics["paywalls"]
                for domain, metrics in site_metrics.items()
                if metrics["paywalls"]
            },
            "site_exhaustion": {
                domain: metrics["exhaustion_reason"]
                for domain, metrics in site_metrics.items()
                if metrics["exhaustion_reason"]
            },
            "site_ingestion_details": {
                domain: metrics["details"]
                for domain, metrics in site_metrics.items()
                if metrics["details"]
            },
            "articles": all_articles,
        }

        adaptive_summary = summarise_adaptive_articles(all_articles)
        if adaptive_summary:
            summary["adaptive_summary"] = adaptive_summary

        logger.info(
            "✅ Unified crawl completed: %s ingested out of %s candidates in %.2fs (%.2f new articles/sec)",
            total_ingested,
            total_candidates,
            total_time,
            articles_per_second,
        )
        return summary

    def _build_hitl_candidate_payload(
        self, article: dict, site_config: SiteConfig | None
    ) -> dict[str, Any] | None:
        """Create the payload expected by the HITL candidate endpoint."""
        url = article.get("url")
        if not url:
            return None

        extracted_text = article.get("content") or article.get("extracted_text") or ""
        features: dict[str, Any] = {}
        if extracted_text:
            features["word_count"] = len(extracted_text.split())

        extraction_meta = article.get("extraction_metadata") or {}
        link_density = extraction_meta.get("link_density")
        if isinstance(link_density, (int, float)):
            features["link_density"] = float(link_density)

        if article.get("confidence") is not None:
            features["confidence"] = article.get("confidence")
        if article.get("paywall_flag") is not None:
            features["paywall_flag"] = bool(article.get("paywall_flag"))
        if article.get("language"):
            features["language"] = article.get("language")

        candidate = {
            "url": url,
            "site_id": article.get("source_id")
            or getattr(site_config, "source_id", None),
            "extracted_title": article.get("title") or article.get("extracted_title"),
            "extracted_text": extracted_text,
            "raw_html_ref": article.get("raw_html_ref"),
            "features": features or None,
            "crawler_ts": article.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "crawler_job_id": article.get("crawler_job_id"),
        }
        return candidate

    def _post_hitl_candidate_sync(self, payload: dict[str, Any]) -> bool:
        """Synchronously post a single candidate to the HITL service."""
        url = f"{self.hitl_base_url}/api/candidates"
        try:
            response = requests.post(url, json=payload, timeout=(2, 6))
            response.raise_for_status()
            self._hitl_failure_streak = 0
            return True
        except Exception as exc:  # noqa: BLE001 - avoid failing the crawl on HITL issues
            self._hitl_failure_streak += 1
            if self._hitl_failure_streak == 1:
                logger.warning(
                    "HITL candidate submission failed (%s): %s", payload.get("url"), exc
                )
            if self._hitl_failure_streak >= 3:
                self._hitl_suspended_until = time.time() + self.hitl_backoff_seconds
                logger.warning(
                    "Suspending HITL submissions for %ss after %s consecutive failures",
                    self.hitl_backoff_seconds,
                    self._hitl_failure_streak,
                )
            return False

    async def _submit_hitl_candidates(
        self, articles: list[dict], site_config: SiteConfig | None
    ) -> None:
        """Submit a batch of candidates to the HITL service and optionally log queue depth."""
        if not self.hitl_enabled or not self.hitl_base_url:
            return
        if not articles:
            return
        now = time.time()
        if self._hitl_suspended_until and now < self._hitl_suspended_until:
            return

        tasks = []
        for article in articles:
            payload = self._build_hitl_candidate_payload(article, site_config)
            if not payload:
                continue
            tasks.append(asyncio.to_thread(self._post_hitl_candidate_sync, payload))

        if not tasks:
            return

        results = await asyncio.gather(*tasks, return_exceptions=True)
        if any(isinstance(result, bool) and result for result in results):
            await self._maybe_log_hitl_stats()

    async def _maybe_log_hitl_stats(self) -> None:
        """Fetch and log HITL queue metrics at a controlled interval."""
        if self.hitl_stats_interval <= 0 or not self.hitl_base_url:
            return
        now = time.time()
        if now - self._hitl_last_stats_check < self.hitl_stats_interval:
            return
        self._hitl_last_stats_check = now

        def _fetch() -> dict[str, Any] | None:
            try:
                response = requests.get(
                    f"{self.hitl_base_url}/api/stats", timeout=(2, 6)
                )
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # noqa: BLE001 - log softly, continue crawl
                logger.debug("HITL stats fetch failed: %s", exc)
                return None

        stats = await asyncio.to_thread(_fetch)
        if stats:
            logger.info(
                "HITL queue depth → pending=%s in_review=%s ingest_queue=%s",
                stats.get("pending"),
                stats.get("in_review"),
                stats.get("ingest_queue_len"),
            )

    async def _ingest_articles(self, articles: list[dict]) -> dict[str, Any]:
        """Ingest articles via the memory agent and annotate ingestion status."""
        MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")
        new_articles = 0
        duplicates = 0
        errors = 0
        details: list[dict[str, Any]] = []

        for article in articles:
            try:
                # Prepare article payload for ingestion
                article_payload = {
                    "url": article.get("url", ""),
                    "normalized_url": article.get("normalized_url"),
                    "title": article.get("title", ""),
                    "content": article.get("content", ""),
                    "domain": article.get("domain", ""),
                    "publisher_meta": article.get("publisher_meta", {}),
                    "confidence": article.get("confidence", 0.5),
                    "paywall_flag": article.get("paywall_flag", False),
                    "extraction_metadata": article.get("extraction_metadata", {}),
                    "extracted_metadata": article.get("extracted_metadata", {}),
                    "structured_metadata": article.get("structured_metadata", {}),
                    "language": article.get("language"),
                    "authors": article.get("authors", []),
                    "section": article.get("section"),
                    "tags": article.get("tags", []),
                    "publication_date": article.get("publication_date"),
                    "raw_html_ref": article.get("raw_html_ref"),
                    "timestamp": article.get("timestamp"),
                    "url_hash": article.get("url_hash"),
                    "url_hash_algorithm": article.get("url_hash_algorithm"),
                    "canonical": article.get("canonical"),
                    "needs_review": article.get("needs_review"),
                    "review_reasons": article.get("extraction_metadata", {}).get(
                        "review_reasons", []
                    ),
                    "disable_dedupe": article.get("disable_dedupe"),
                }

                # Build SQL statements for source upsert and article insertion
                # This mirrors the logic from the site-specific crawlers
                # Use ON DUPLICATE KEY UPDATE to handle existing sources gracefully
                # Note: last_crawl_at is the timestamp field on sources table, not last_verified
                source_sql = """
                INSERT INTO sources (name, domain, url, last_crawl_at)
                VALUES (%s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    last_crawl_at = NOW()
                """

                source_params = (
                    article.get("source_name", article.get("domain", "unknown")),
                    article.get("domain", "unknown"),
                    f"https://{article.get('domain', 'unknown')}",
                )

                # Article insertion SQL (will be handled by memory agent)
                # The memory agent handles the article insertion via save_article

                statements = [[source_sql, list(source_params)]]

                safe_article_payload = make_json_safe(article_payload)

                if lxml_etree is not None:

                    def _find_non_jsonable(
                        value: Any, path: str = "payload"
                    ) -> str | None:
                        if isinstance(value, (str, int, float, bool)) or value is None:
                            return None
                        if isinstance(value, bytes):
                            return None
                        if isinstance(value, Mapping):
                            for key, val in value.items():
                                found = _find_non_jsonable(val, f"{path}.{key}")
                                if found:
                                    return found
                            return None
                        if isinstance(value, Sequence) and not isinstance(
                            value, (str, bytes, bytearray)
                        ):
                            for index, item in enumerate(value):
                                found = _find_non_jsonable(item, f"{path}[{index}]")
                                if found:
                                    return found
                            return None
                        if isinstance(value, set):
                            for index, item in enumerate(value):
                                found = _find_non_jsonable(item, f"{path}{{{index}}}")
                                if found:
                                    return found
                            return None
                        if hasattr(lxml_etree, "_Element") and isinstance(
                            value, lxml_etree._Element
                        ):  # type: ignore[attr-defined]
                            return path
                        return None

                    non_jsonable_path = _find_non_jsonable(safe_article_payload)
                    if non_jsonable_path:
                        logger.warning(
                            "Non-JSONable element present after sanitisation at %s",
                            non_jsonable_path,
                        )

                payload = {
                    "agent": "memory",
                    "tool": "ingest_article",
                    "args": [],
                    "kwargs": {
                        "article_payload": safe_article_payload,
                        "statements": statements,
                    },
                }

                payload = make_json_safe(payload)
                payload_json = json.dumps(payload, default=str)

                # Make MCP bus call to memory agent
                response = requests.post(
                    f"{MCP_BUS_URL}/call",
                    data=payload_json,
                    headers={"Content-Type": "application/json"},
                    timeout=(5, 60),
                )
                response.raise_for_status()
                result = response.json()

                outer_status = result.get("status")
                inner_payload = (
                    result.get("data") if isinstance(result.get("data"), dict) else {}
                )
                effective_payload = inner_payload if inner_payload else result
                inner_status = effective_payload.get("status", outer_status)

                if outer_status in {"ok", "success"} and inner_status in {
                    "ok",
                    "success",
                }:
                    if effective_payload.get("duplicate"):
                        duplicates += 1
                        article["ingestion_status"] = "duplicate"
                        logger.debug(f"Duplicate article skipped: {article.get('url')}")
                    else:
                        new_articles += 1
                        article["ingestion_status"] = "new"
                        logger.debug(f"New article ingested: {article.get('url')}")
                    details.append(
                        {
                            "url": article.get("url"),
                            "status": article.get("ingestion_status"),
                        }
                    )
                else:
                    errors += 1
                    article["ingestion_status"] = "error"
                    details.append(
                        {
                            "url": article.get("url"),
                            "status": "error",
                            "error": effective_payload.get("error") or result,
                        }
                    )
                    logger.warning(
                        f"Failed to ingest article {article.get('url')}: {result}"
                    )

            except Exception as e:
                errors += 1
                article["ingestion_status"] = "error"
                details.append(
                    {
                        "url": article.get("url"),
                        "status": "error",
                        "error": str(e),
                    }
                )
                logger.warning(
                    f"Error ingesting article {article.get('url', 'unknown')}: {e}"
                )
                continue

        return {
            "new_articles": new_articles,
            "duplicates": duplicates,
            "errors": errors,
            "details": details,
        }

    def get_performance_report(self) -> dict[str, Any]:
        """Get current performance metrics"""
        return {
            "articles_processed": self.performance_metrics["articles_processed"],
            "sites_crawled": self.performance_metrics["sites_crawled"],
            "errors": self.performance_metrics["errors"],
            "mode_usage": self.performance_metrics["mode_usage"],
            "uptime_seconds": time.time() - self.performance_metrics["start_time"],
        }
