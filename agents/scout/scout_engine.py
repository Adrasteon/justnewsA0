"""
Scout Engine - AI-Powered Web Crawling and Analysis [DEPRECATED]

DEPRECATION WARNING:
This engine is deprecated. Use `agents.fact_checker.investigator` or 
`agents.crawler.crawler_engine` instead.

This module implements the core Scout engine for web crawling, content discovery,
and AI-powered analysis.
"""

import os
import re
import time
import warnings
from dataclasses import dataclass
from datetime import timezone, datetime
from enum import Enum
from typing import Any

import requests
import torch

try:
    # transformers is an optional heavy dependency; import pipeline lazily and
    # degrade to None if unavailable so test collection doesn't fail.
    from transformers import pipeline  # type: ignore

    TRANSFORMERS_AVAILABLE = True
except Exception:
    pipeline = None  # type: ignore
    TRANSFORMERS_AVAILABLE = False

from common.observability import get_logger

# Suppress transformers warnings in production, but do not suppress during tests.
if os.environ.get("PYTEST_RUNNING") != "1":
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=UserWarning)

# Crawl4AI imports with fallbacks
try:
    from crawl4ai import AsyncWebCrawler, CrawlResult

    CRAWL4AI_AVAILABLE = True
except ImportError:
    AsyncWebCrawler = None
    CrawlResult = None
    CRAWL4AI_AVAILABLE = False

logger = get_logger(__name__)


class CrawlMode(Enum):
    """Crawling mode enumeration."""

    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"


class ContentType(Enum):
    """Content type enumeration."""

    ARTICLE = "article"
    NEWS = "news"
    BLOG = "blog"
    SOCIAL = "social"
    OTHER = "other"


@dataclass
class CrawlResult:
    """Result container for crawling operations."""

    url: str
    content: str
    title: str
    links: list[str]
    metadata: dict[str, Any]
    processing_time: float
    success: bool


@dataclass
class AnalysisResult:
    """Result container for AI analysis operations."""

    text: str
    result: Any
    confidence: float
    processing_time: float
    model_used: str


@dataclass
class ScoutConfig:
    """Configuration for Scout Engine."""

    # Model configurations
    bert_model: str = "nlptown/bert-base-multilingual-uncased-sentiment"
    deberta_model: str = "microsoft/DialoGPT-medium"
    roberta_model: str = "cardiffnlp/twitter-roberta-base-sentiment-latest"

    # Crawling configurations
    max_crawl_depth: int = 3
    max_concurrent_crawls: int = 5
    crawl_timeout: int = 30
    user_agent: str = "JustNews-Scout/2.0"

    # AI configurations
    max_sequence_length: int = 512
    batch_size: int = 8
    device: str = "auto"

    # Performance configurations
    enable_gpu: bool = True
    cache_models: bool = True
    model_cache_dir: str = "./model_cache"


class ScoutEngine:
    """
    Scout Engine - Core AI-powered web crawling and analysis.

    This engine provides intelligent web crawling capabilities combined with
    AI-powered content analysis using specialized transformer models.

    Key Features:
    - Web crawling with Crawl4AI
    - Sentiment analysis with BERT
    - Content quality assessment with DeBERTa
    - Bias detection with RoBERTa
    - GPU acceleration with memory management
    - Robust error handling and fallbacks
    """

    def __init__(self, config: ScoutConfig):
        warnings.warn(
            "ScoutEngine is deprecated. Use Investigator or Crawler instead.",
            DeprecationWarning,
            stacklevel=2
        )
        self.config = config
        self.device = self._setup_device()

        # Model storage
        self.models = {}
        self.tokenizers = {}
        self.pipelines = {}

        # Processing stats
        self.processing_stats = {
            "total_crawled": 0,
            "total_analyzed": 0,
            "success_rate": 0.0,
            "average_crawl_time": 0.0,
            "average_analysis_time": 0.0,
        }

        # Initialize components
        self._initialize_models()
        logger.info("✅ Scout Engine initialized")

    def _setup_device(self) -> torch.device:
        """Setup optimal compute device."""
        if self.config.enable_gpu and torch.cuda.is_available():
            device = torch.device("cuda:0")
            gpu_name = torch.cuda.get_device_name(0)
            logger.info(f"✅ GPU acceleration enabled: {gpu_name}")
            return device
        else:
            device = torch.device("cpu")
            logger.info("✅ CPU processing mode")
            return device

    def _initialize_models(self):
        """Initialize AI models for analysis."""
        try:
            # Initialize sentiment analysis pipeline
            self._load_sentiment_model()

            # Initialize bias detection pipeline
            self._load_bias_model()

            logger.info("✅ AI models initialized successfully")

        except Exception as e:
            logger.error(f"Error initializing models: {e}")
            self._initialize_fallbacks()

    def _load_sentiment_model(self):
        """Load sentiment analysis model."""
        try:
            if not TRANSFORMERS_AVAILABLE or pipeline is None:
                raise RuntimeError("transformers.pipeline unavailable")

            self.pipelines["sentiment"] = pipeline(
                "sentiment-analysis",
                model=self.config.bert_model,
                tokenizer=self.config.bert_model,
                device=self.device,
                return_all_scores=True,
                truncation=True,
                max_length=self.config.max_sequence_length,
            )
            logger.info("✅ Sentiment analysis model loaded")
        except Exception as e:
            logger.warning(f"Failed to load sentiment model: {e}")
            self.pipelines["sentiment"] = None

    def _load_bias_model(self):
        """Load bias detection model."""
        try:
            if not TRANSFORMERS_AVAILABLE or pipeline is None:
                raise RuntimeError("transformers.pipeline unavailable")

            self.pipelines["bias"] = pipeline(
                "text-classification",
                model=self.config.roberta_model,
                tokenizer=self.config.roberta_model,
                device=self.device,
                truncation=True,
                max_length=self.config.max_sequence_length,
            )
            logger.info("✅ Bias detection model loaded")
        except Exception as e:
            logger.warning(f"Failed to load bias model: {e}")
            self.pipelines["bias"] = None

    def _initialize_fallbacks(self):
        """Initialize fallback processing systems."""
        logger.info("Initializing fallback processing systems...")
        # Simple rule-based fallbacks will be implemented in analysis methods

    async def crawl_url(
        self, url: str, mode: CrawlMode = CrawlMode.STANDARD
    ) -> CrawlResult:
        """
        Crawl a URL and extract content.

        Args:
            url: URL to crawl
            mode: Crawling mode (fast, standard, deep)

        Returns:
            CrawlResult with extracted content
        """
        start_time = time.time()
        logger.info(f"🕷️ Crawling URL: {url} (mode: {mode.value})")

        try:
            if not self._is_valid_url(url):
                raise ValueError(f"Invalid URL: {url}")

            # Use Crawl4AI if available
            if CRAWL4AI_AVAILABLE:
                content = await self._crawl_with_crawl4ai(url, mode)
            else:
                content = await self._crawl_with_requests(url)

            processing_time = time.time() - start_time

            result = CrawlResult(
                url=url,
                content=content.get("text", ""),
                title=content.get("title", ""),
                links=content.get("links", []),
                metadata=content.get("metadata", {}),
                processing_time=processing_time,
                success=True,
            )

            self.processing_stats["total_crawled"] += 1
            self._update_average_time("crawl", processing_time)

            logger.info(f"✅ Crawl completed: {processing_time:.2f}s")
            return result

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Crawl failed: {e}")

            return CrawlResult(
                url=url,
                content="",
                title="",
                links=[],
                metadata={"error": str(e)},
                processing_time=processing_time,
                success=False,
            )

    async def _crawl_with_crawl4ai(self, url: str, mode: CrawlMode) -> dict[str, Any]:
        """Crawl using Crawl4AI."""
        try:
            async with AsyncWebCrawler() as crawler:
                config = {
                    "timeout": self.config.crawl_timeout,
                    "user_agent": self.config.user_agent,
                }

                if mode == CrawlMode.DEEP:
                    config.update({"max_pages": 10, "follow_links": True})

                result = await crawler.arun(url=url, config=config)

                return {
                    "text": result.markdown if hasattr(result, "markdown") else "",
                    "title": result.title if hasattr(result, "title") else "",
                    "links": result.links if hasattr(result, "links") else [],
                    "metadata": {
                        "status_code": result.status_code
                        if hasattr(result, "status_code")
                        else 200,
                        "content_type": result.content_type
                        if hasattr(result, "content_type")
                        else "text/html",
                    },
                }

        except Exception as e:
            logger.warning(f"Crawl4AI failed, falling back to requests: {e}")
            return await self._crawl_with_requests(url)

    async def _crawl_with_requests(self, url: str) -> dict[str, Any]:
        """Fallback crawling using requests."""
        try:
            headers = {"User-Agent": self.config.user_agent}
            response = requests.get(
                url, headers=headers, timeout=self.config.crawl_timeout
            )
            response.raise_for_status()

            # Simple HTML parsing
            text = self._extract_text_from_html(response.text)
            title = self._extract_title_from_html(response.text)
            links = self._extract_links_from_html(response.text, url)

            return {
                "text": text,
                "title": title,
                "links": links,
                "metadata": {
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", "text/html"),
                },
            }

        except Exception as e:
            logger.error(f"Requests fallback failed: {e}")
            return {"text": "", "title": "", "links": [], "metadata": {"error": str(e)}}

    def _extract_text_from_html(self, html: str) -> str:
        """Simple HTML text extraction."""
        # Remove scripts and styles
        html = re.sub(
            r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
        )
        html = re.sub(
            r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE
        )

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", html)

        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _extract_title_from_html(self, html: str) -> str:
        """Extract title from HTML."""
        title_match = re.search(
            r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL
        )
        return title_match.group(1).strip() if title_match else ""

    def _extract_links_from_html(self, html: str, base_url: str) -> list[str]:
        """Extract links from HTML."""
        links = []
        link_pattern = re.compile(
            r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE
        )

        for match in link_pattern.finditer(html):
            link = match.group(1)
            # Convert relative URLs to absolute
            if link.startswith("/"):
                from urllib.parse import urljoin

                link = urljoin(base_url, link)
            elif not link.startswith(("http://", "https://")):
                link = urljoin(base_url, link)

            if link not in links:
                links.append(link)

        return links[:50]  # Limit links

    def _is_valid_url(self, url: str) -> bool:
        """Validate URL format."""
        url_pattern = re.compile(
            r"^https?://"  # http:// or https://
            r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
            r"localhost|"  # localhost...
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
            r"(?::\d+)?"  # optional port
            r"(?:/?|[/?]\S+)$",
            re.IGNORECASE,
        )

        return url_pattern.match(url) is not None

    async def analyze_sentiment(self, text: str) -> AnalysisResult:
        """
        Analyze sentiment in text using BERT model.

        Args:
            text: Text to analyze

        Returns:
            AnalysisResult with sentiment classification
        """
        start_time = time.time()
        logger.info(f"😊 Analyzing sentiment for text ({len(text)} chars)")

        try:
            if not text or not text.strip():
                raise ValueError("Empty text provided")

            if self.pipelines.get("sentiment"):
                # Use transformer pipeline
                results = self.pipelines["sentiment"](text)

                # Process results
                if isinstance(results[0], list):
                    results = results[0]

                # Find highest confidence result
                best_result = max(results, key=lambda x: x["score"])
                sentiment = best_result["label"]
                confidence = best_result["score"]

                # Normalize sentiment labels
                sentiment = self._normalize_sentiment_label(sentiment)

            else:
                # Fallback: simple rule-based analysis
                sentiment, confidence = self._fallback_sentiment_analysis(text)

            processing_time = time.time() - start_time

            result = AnalysisResult(
                text=text,
                result=sentiment,
                confidence=confidence,
                processing_time=processing_time,
                model_used=self.config.bert_model
                if self.pipelines.get("sentiment")
                else "fallback",
            )

            self.processing_stats["total_analyzed"] += 1
            self._update_average_time("analysis", processing_time)

            logger.info(
                f"✅ Sentiment analysis completed: {sentiment} ({confidence:.2f})"
            )
            return result

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Sentiment analysis failed: {e}")

            return AnalysisResult(
                text=text,
                result="neutral",
                confidence=0.0,
                processing_time=processing_time,
                model_used="error",
            )

    def _normalize_sentiment_label(self, label: str) -> str:
        """Normalize sentiment labels to standard format."""
        label = label.lower()

        if "positive" in label or "pos" in label or "4" in label or "5" in label:
            return "positive"
        elif "negative" in label or "neg" in label or "1" in label or "2" in label:
            return "negative"
        else:
            return "neutral"

    def _fallback_sentiment_analysis(self, text: str) -> tuple[str, float]:
        """Simple rule-based sentiment analysis fallback."""
        positive_words = [
            "good",
            "great",
            "excellent",
            "amazing",
            "wonderful",
            "fantastic",
            "love",
            "like",
            "best",
        ]
        negative_words = [
            "bad",
            "terrible",
            "awful",
            "horrible",
            "hate",
            "worst",
            "disappointing",
            "poor",
        ]

        text_lower = text.lower()
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)

        if positive_count > negative_count:
            return "positive", 0.6
        elif negative_count > positive_count:
            return "negative", 0.6
        else:
            return "neutral", 0.5

    async def detect_bias(self, text: str) -> AnalysisResult:
        """
        Detect bias in text using RoBERTa model.

        Args:
            text: Text to analyze for bias

        Returns:
            AnalysisResult with bias assessment
        """
        start_time = time.time()
        logger.info(f"⚖️ Detecting bias for text ({len(text)} chars)")

        try:
            if not text or not text.strip():
                raise ValueError("Empty text provided")

            if self.pipelines.get("bias"):
                # Use transformer pipeline
                results = self.pipelines["bias"](text)

                # Process results - bias detection typically gives confidence scores
                if isinstance(results, list) and results:
                    result = results[0]
                    bias_score = (
                        1.0 - result["score"]
                        if result["label"].lower() == "neutral"
                        else result["score"]
                    )
                    bias_type = "political" if bias_score > 0.7 else "minimal"
                else:
                    bias_score = 0.5
                    bias_type = "unknown"

            else:
                # Fallback: simple bias detection
                bias_score, bias_type = self._fallback_bias_detection(text)

            processing_time = time.time() - start_time

            result = AnalysisResult(
                text=text,
                result={"bias_score": bias_score, "bias_type": bias_type},
                confidence=bias_score,
                processing_time=processing_time,
                model_used=self.config.roberta_model
                if self.pipelines.get("bias")
                else "fallback",
            )

            self.processing_stats["total_analyzed"] += 1
            self._update_average_time("analysis", processing_time)

            logger.info(f"✅ Bias detection completed: {bias_type} ({bias_score:.2f})")
            return result

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Bias detection failed: {e}")

            return AnalysisResult(
                text=text,
                result={"bias_score": 0.0, "bias_type": "unknown"},
                confidence=0.0,
                processing_time=processing_time,
                model_used="error",
            )

    def _fallback_bias_detection(self, text: str) -> tuple[float, str]:
        """Simple rule-based bias detection fallback."""
        bias_indicators = [
            "fake news",
            "liberal",
            "conservative",
            "left-wing",
            "right-wing",
            "propaganda",
            "biased",
            "agenda",
            "spin",
            "manipulated",
        ]

        text_lower = text.lower()
        bias_count = sum(1 for indicator in bias_indicators if indicator in text_lower)

        if bias_count > 2:
            return 0.8, "high_bias"
        elif bias_count > 0:
            return 0.6, "moderate_bias"
        else:
            return 0.2, "minimal_bias"

    async def discover_sources(
        self, domains: list[str] | None = None, max_sources: int = 10
    ) -> list[dict[str, Any]]:
        """
        Discover news sources using intelligent algorithms.

        Args:
            domains: Specific domains to search (optional)
            max_sources: Maximum sources to discover

        Returns:
            List of discovered sources
        """
        logger.info(
            f"🔍 Discovering sources: domains={domains}, max_sources={max_sources}"
        )

        sources = []

        try:
            # Use predefined news domains if none specified
            if not domains:
                domains = [
                    "bbc.com",
                    "cnn.com",
                    "reuters.com",
                    "apnews.com",
                    "nytimes.com",
                    "washingtonpost.com",
                    "theguardian.com",
                ]

            # Crawl each domain for sources
            for domain in domains[:max_sources]:
                try:
                    url = f"https://{domain}"
                    crawl_result = await self.crawl_url(url, CrawlMode.FAST)

                    if crawl_result.success:
                        source_info = {
                            "domain": domain,
                            "url": url,
                            "title": crawl_result.title,
                            "content_preview": crawl_result.content[:200] + "..."
                            if len(crawl_result.content) > 200
                            else crawl_result.content,
                            "links_found": len(crawl_result.links),
                            "discovered_at": datetime.now(timezone.utc).isoformat(),
                        }
                        sources.append(source_info)

                except Exception as e:
                    logger.warning(f"Failed to discover source {domain}: {e}")
                    continue

            logger.info(f"✅ Source discovery completed: {len(sources)} sources found")
            return sources

        except Exception as e:
            logger.error(f"❌ Source discovery failed: {e}")
            return []

    async def deep_crawl_site(
        self, site_url: str, max_pages: int = 50
    ) -> dict[str, Any]:
        """
        Perform deep crawling of a website.

        Args:
            site_url: Site URL to crawl
            max_pages: Maximum pages to crawl

        Returns:
            Deep crawl results
        """
        logger.info(f"🔬 Deep crawling site: {site_url} (max_pages: {max_pages})")

        try:
            crawled_pages = []
            visited_urls = set()
            to_visit = [site_url]

            pages_crawled = 0

            while to_visit and pages_crawled < max_pages:
                current_url = to_visit.pop(0)

                if current_url in visited_urls:
                    continue

                visited_urls.add(current_url)

                try:
                    crawl_result = await self.crawl_url(current_url, CrawlMode.STANDARD)

                    if crawl_result.success:
                        page_info = {
                            "url": current_url,
                            "title": crawl_result.title,
                            "content_length": len(crawl_result.content),
                            "links_found": len(crawl_result.links),
                        }
                        crawled_pages.append(page_info)
                        pages_crawled += 1

                        # Add new internal links to visit queue
                        for link in crawl_result.links:
                            if (
                                link not in visited_urls
                                and link.startswith(site_url)
                                and len(to_visit) < max_pages * 2
                            ):  # Limit queue size
                                to_visit.append(link)

                except Exception as e:
                    logger.warning(f"Failed to crawl {current_url}: {e}")
                    continue

            result = {
                "site_url": site_url,
                "pages_crawled": pages_crawled,
                "total_urls_visited": len(visited_urls),
                "articles_found": crawled_pages,
                "success": True,
            }

            logger.info(f"✅ Deep crawl completed: {pages_crawled} pages")
            return result

        except Exception as e:
            logger.error(f"❌ Deep crawl failed: {e}")
            return {
                "site_url": site_url,
                "pages_crawled": 0,
                "articles_found": [],
                "success": False,
                "error": str(e),
            }

    def _update_average_time(self, operation: str, processing_time: float):
        """Update average processing time statistics."""
        if operation == "crawl":
            key = "average_crawl_time"
        elif operation == "analysis":
            key = "average_analysis_time"
        else:
            return

        current_avg = self.processing_stats[key]
        total_count = (
            self.processing_stats["total_crawled"]
            if operation == "crawl"
            else self.processing_stats["total_analyzed"]
        )

        if total_count > 0:
            self.processing_stats[key] = (
                current_avg * (total_count - 1) + processing_time
            ) / total_count

    def get_model_info(self) -> dict[str, Any]:
        """Get information about loaded models."""
        return {
            "sentiment_model": {
                "loaded": self.pipelines.get("sentiment") is not None,
                "model_name": self.config.bert_model,
            },
            "bias_model": {
                "loaded": self.pipelines.get("bias") is not None,
                "model_name": self.config.roberta_model,
            },
            "crawl4ai_available": CRAWL4AI_AVAILABLE,
        }

    def get_processing_stats(self) -> dict[str, Any]:
        """Get processing statistics."""
        return self.processing_stats.copy()

    def cleanup(self):
        """Cleanup resources and GPU memory."""
        logger.info("🧹 Cleaning up Scout Engine...")

        try:
            # Clear model cache
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Clear pipelines
            self.pipelines.clear()
            self.models.clear()
            self.tokenizers.clear()

            logger.info("✅ Scout Engine cleanup completed")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


# Export main components
__all__ = [
    "ScoutEngine",
    "ScoutConfig",
    "CrawlMode",
    "ContentType",
    "CrawlResult",
    "AnalysisResult",
]
