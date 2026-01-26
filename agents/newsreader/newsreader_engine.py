"""
DEPRECATED: This module is deprecated. Use common.web_capture or Investigator instead.
"""
"""
NewsReader Engine - Simplified Multi-Modal Vision Processing

Core functionality: Screenshot-based webpage processing using LLaVA vision-language model.
This engine captures webpage screenshots and analyzes them with LLaVA to extract news content.

Features:
- Playwright screenshot capture with optimizations
- LLaVA vision-language analysis for content extraction
- GPU acceleration with CPU fallbacks
- Lazy loading of heavy models for fast startup
- Comprehensive error handling and memory management
- Production-ready with robust fallbacks

Architecture: Streamlined for LLaVA-first approach, removing redundant OCR/Layout/CLIP components.
"""

from __future__ import annotations

import os
import time
import warnings
from dataclasses import dataclass
from enum import Enum
from typing import Any

try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False

from PIL import Image

try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    async_playwright = None
    PLAYWRIGHT_AVAILABLE = False

from common.observability import get_logger

# Model imports with fallbacks
try:
    from transformers import (
        BitsAndBytesConfig,
        LlavaOnevisionForConditionalGeneration,
        LlavaOnevisionProcessor,
    )

    LLAVA_AVAILABLE = True
except ImportError:
    BitsAndBytesConfig = None
    LlavaOnevisionForConditionalGeneration = None
    LlavaOnevisionProcessor = None
    LLAVA_AVAILABLE = False

# Suppress transformers warnings in production, but not during tests.
if os.environ.get("PYTEST_RUNNING") != "1":
    warnings.filterwarnings("ignore", message=".*use_fast.*slow processor.*")
    warnings.filterwarnings("ignore", message=".*slow image processor.*")

logger = get_logger(__name__)


class ContentType(Enum):
    """Content type enumeration for processing classification."""

    ARTICLE = "article"
    IMAGE = "image"
    WEBPAGE = "webpage"


class ProcessingMode(Enum):
    """Processing mode enumeration for different analysis depths."""

    FAST = "fast"
    COMPREHENSIVE = "comprehensive"


@dataclass
class ProcessingResult:
    """Result container for content processing operations."""

    content_type: ContentType
    extracted_text: str
    visual_description: str
    confidence_score: float
    processing_time: float
    model_outputs: dict[str, Any]
    metadata: dict[str, Any]
    screenshot_path: str | None = None


@dataclass
class NewsReaderConfig:
    """Configuration for NewsReader Engine."""

    llava_model: str = "llava-hf/llava-onevision-qwen2-0.5b-ov-hf"
    cache_dir: str = "./model_cache"
    use_quantization: bool = True
    quantization_type: str = "int8"
    quantization_compute_dtype: str = "float16"
    screenshot_timeout: int = 30000
    screenshot_quality: str = "high"
    headless: bool = True
    default_mode: ProcessingMode = ProcessingMode.COMPREHENSIVE
    max_image_size: int = 1024
    max_sequence_length: int = 2048
    max_new_tokens: int = 512
    device: str = "auto"
    min_confidence_threshold: float = 0.7


class NewsReaderEngine:
    """
    NewsReader Engine - Core vision-language processing for news content.

    This engine specializes in screenshot-based webpage analysis using LLaVA
    to extract and understand news content from visual representations.

    Key Features:
    - Screenshot capture with Playwright
    - LLaVA vision-language model for content analysis
    - GPU acceleration with memory management
    - Robust error handling and fallbacks
    - Production-ready performance monitoring
    """

    def __init__(self, config: NewsReaderConfig | None = None):
        """Initialize the NewsReader engine with configuration."""
        self.config = config or NewsReaderConfig()
        self.device = self._setup_device()
        self._enable_cuda_optimizations()

        # Model storage
        self.models = {}
        self.processors = {}

        # Processing stats
        self.processing_stats = {
            "total_processed": 0,
            "success_rate": 0.0,
            "average_processing_time": 0.0,
        }

        # Initialize components
        self._initialize_screenshot_system()
        # LLaVA model is loaded lazily on first request
        logger.info("✅ NewsReader Engine initialized (LLaVA model will lazy-load)")

    def __enter__(self) -> NewsReaderEngine:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self._cleanup_gpu_memory()
        if exc_type is not None:
            logger.error(
                f"NewsReader Engine exited with error: {exc_type.__name__}: {exc_val}"
            )
        return False

    async def __aenter__(self) -> NewsReaderEngine:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""
        self._cleanup_gpu_memory()
        if exc_type is not None:
            logger.error(
                f"NewsReader Engine async exited with error: {exc_type.__name__}: {exc_val}"
            )
        return False

    def _setup_device(self):
        """Setup optimal compute device."""
        if (
            TORCH_AVAILABLE
            and torch.cuda.is_available()
            and self.config.device in ["auto", "cuda"]
        ):
            device = torch.device("cuda:0")
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1e9
            logger.info(f"✅ GPU acceleration enabled: {gpu_name} ({gpu_memory:.1f}GB)")
            return device
        else:
            device = (
                torch.device("cpu")
                if TORCH_AVAILABLE
                else type("obj", (object,), {"type": "cpu"})()
            )
            logger.info("✅ CPU processing mode")
            return device

    def _enable_cuda_optimizations(self):
        """Enable CUDA optimizations for performance."""
        if TORCH_AVAILABLE and getattr(self.device, "type", None) == "cuda":
            torch.backends.cudnn.benchmark = True
            torch.backends.cudnn.deterministic = False
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            logger.info("✅ CUDA optimizations enabled")

    def _ensure_llava_model_loaded(self):
        """Ensure LLaVA model is loaded (lazy loading)."""
        if self.models.get("llava") is not None:
            return

        logger.info("⏳ Lazy-loading LLaVA model...")
        try:
            self._load_llava_model()
            logger.info("✅ LLaVA model loaded successfully (lazy load)")
        except Exception as e:
            logger.error(f"Error lazy-loading models: {e}")
            self._initialize_fallback_systems()

    def _load_llava_model(self):
        """Load LLaVA model for vision-language processing."""
        if self.models.get("llava") is not None:
            return

        if not LLAVA_AVAILABLE:
            logger.warning("LLaVA not available - using fallback processing")
            self.models["llava"] = None
            self.processors["llava"] = None
            return

        try:
            # Setup quantization
            quantization_config = None
            if self.config.use_quantization and self.config.quantization_type != "none":
                logger.info(
                    f"🔧 Setting up {self.config.quantization_type.upper()} quantization"
                )
                if self.config.quantization_type == "int8":
                    quantization_config = BitsAndBytesConfig(
                        load_in_8bit=True,
                        bnb_8bit_compute_dtype=getattr(
                            torch, self.config.quantization_compute_dtype
                        ),
                        bnb_8bit_use_double_quant=True,
                    )

            # Load processor
            self.processors["llava"] = LlavaOnevisionProcessor.from_pretrained(
                self.config.llava_model,
                use_fast=False,
                trust_remote_code=True,
                cache_dir=self.config.cache_dir,
            )

            # Load model with memory optimization
            model_kwargs = {
                "dtype": torch.float16 if self.device.type == "cuda" else torch.float32,
                "device_map": "auto",
                "low_cpu_mem_usage": True,
                "max_memory": {0: "2GB"} if self.device.type == "cuda" else None,
                "cache_dir": self.config.cache_dir,
                "trust_remote_code": True,
            }

            if quantization_config:
                model_kwargs["quantization_config"] = quantization_config

            self.models["llava"] = (
                LlavaOnevisionForConditionalGeneration.from_pretrained(
                    self.config.llava_model, **model_kwargs
                )
            )

            # Move to device if not quantized
            if self.device.type == "cuda" and quantization_config is None:
                if not any(
                    "cuda" in str(param.device)
                    for param in self.models["llava"].parameters()
                ):
                    self.models["llava"] = self.models["llava"].to(self.device)

            logger.info("✅ LLaVA model loaded successfully")

        except Exception as e:
            logger.error(f"Error loading LLaVA model: {e}")
            self.models["llava"] = None

    def _initialize_screenshot_system(self):
        """Initialize Playwright screenshot capture system."""
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not available - screenshot capture disabled")
            self.models["screenshot_system"] = None
            return

        self.models["screenshot_system"] = {
            "headless": self.config.headless,
            "timeout": self.config.screenshot_timeout,
            "quality": self.config.screenshot_quality,
            "browser_args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
            ],
        }
        logger.info("✅ Screenshot system initialized")

    def _initialize_fallback_systems(self):
        """Initialize fallback processing systems."""
        logger.info("Initializing fallback processing systems...")
        self.models["fallback"] = True

    def _cleanup_gpu_memory(self):
        """Aggressive GPU memory cleanup."""
        logger.info("🧹 Starting GPU memory cleanup...")

        if TORCH_AVAILABLE and self.device.type == "cuda" and torch.cuda.is_available():
            import gc

            gc.collect()
            for _ in range(3):
                torch.cuda.empty_cache()
                torch.cuda.synchronize()

            allocated_mb = torch.cuda.memory_allocated() / 1e6
            logger.info(f"🧹 GPU memory after cleanup: {allocated_mb:.1f}MB allocated")

    def is_llava_available(self) -> bool:
        """Check if LLaVA runtime is available (even if model is not loaded yet)."""
        return LLAVA_AVAILABLE

    async def capture_webpage_screenshot(
        self, url: str, screenshot_path: str = "page.png"
    ) -> str:
        """
        Capture screenshot of webpage for analysis.

        Args:
            url: Webpage URL to capture
            screenshot_path: Path to save screenshot

        Returns:
            Path to saved screenshot

        Raises:
            RuntimeError: If screenshot capture fails
            ValueError: If URL is invalid
        """
        logger.info(f"📸 Capturing screenshot for URL: {url}")

        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not available for screenshot capture")

        if not isinstance(url, str) or not url.lower().startswith(
            ("http://", "https://")
        ):
            raise ValueError(f"Invalid URL: {url}")

        os.makedirs(os.path.dirname(screenshot_path) or ".", exist_ok=True)

        browser = None
        page = None

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.config.headless,
                    args=self.models["screenshot_system"]["browser_args"],
                )

                page = await browser.new_page()
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.config.screenshot_timeout,
                )
                await page.wait_for_timeout(2000)

                await page.screenshot(path=screenshot_path, full_page=False)
                logger.info(f"✅ Screenshot saved: {screenshot_path}")
                return screenshot_path

        except Exception as e:
            logger.error(f"❌ Screenshot capture failed for {url}: {e}")
            raise
        finally:
            try:
                if page:
                    await page.close()
            except Exception:
                pass
            try:
                if browser:
                    await browser.close()
            except Exception:
                pass

    def analyze_screenshot_with_llava(
        self, screenshot_path: str, custom_prompt: str | None = None
    ) -> dict[str, Any]:
        """
        Analyze screenshot using LLaVA vision-language model.

        Args:
            screenshot_path: Path to screenshot image
            custom_prompt: Custom analysis prompt (optional)

        Returns:
            Analysis results with extracted content
        """
        # Ensure model is strictly loaded only when requested
        self._ensure_llava_model_loaded()

        if self.models.get("llava") is None:
            return {
                "success": False,
                "error": "LLaVA model failed to load",
                "screenshot_path": screenshot_path,
            }

        if not custom_prompt:
            custom_prompt = """
            Analyze this webpage screenshot for news content.

            Please extract:
            1. The main headline (if visible)
            2. The main news article content (if visible)
            3. Any other relevant news text

            Format your response as:
            HEADLINE: [extracted headline]
            ARTICLE: [extracted article content]
            """

        try:
            with Image.open(screenshot_path) as img:
                image = img.convert("RGB")

            conversation = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image"},
                        {"type": "text", "text": custom_prompt},
                    ],
                }
            ]

            prompt_text = self.processors["llava"].apply_chat_template(
                conversation, add_generation_prompt=True
            )

            # Limit text length
            max_chars = self.config.max_sequence_length * 4
            if len(prompt_text) > max_chars:
                prefix_len = max_chars // 3
                suffix_len = max_chars // 3
                prompt_text = (
                    prompt_text[:prefix_len]
                    + "...[truncated]..."
                    + prompt_text[-suffix_len:]
                )

            inputs = self.processors["llava"](
                images=image, text=prompt_text, return_tensors="pt", padding=True
            )

            if TORCH_AVAILABLE and hasattr(inputs, "to"):
                inputs = inputs.to(self.device)

            with torch.no_grad():
                output = self.models["llava"].generate(
                    **inputs,
                    max_new_tokens=self.config.max_new_tokens,
                    do_sample=True,
                    temperature=0.7,
                    top_p=0.9,
                    pad_token_id=self.processors["llava"].tokenizer.eos_token_id,
                )

            new_token_ids = output[0][len(inputs.input_ids[0]) :]
            if TORCH_AVAILABLE and hasattr(new_token_ids, "detach"):
                new_token_ids = new_token_ids.detach().cpu().tolist()
            generated_text = self.processors["llava"].tokenizer.decode(
                new_token_ids, skip_special_tokens=True
            )

            parsed_content = self._parse_llava_response(generated_text)

            if (
                TORCH_AVAILABLE
                and self.device.type == "cuda"
                and torch.cuda.is_available()
            ):
                torch.cuda.empty_cache()

            return {
                "success": True,
                "raw_analysis": generated_text.strip(),
                "parsed_content": parsed_content,
                "screenshot_path": screenshot_path,
                "model_used": self.config.llava_model,
            }

        except Exception as e:
            logger.error(f"❌ LLaVA analysis failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "screenshot_path": screenshot_path,
            }

    def _parse_llava_response(self, response: str) -> dict[str, str]:
        """Parse LLaVA response to extract structured content."""
        parsed = {"headline": "", "article": "", "additional_content": ""}

        try:
            lines = response.split("\n")
            current_section = None

            for line in lines:
                line = line.strip()
                if line.startswith("HEADLINE:"):
                    current_section = "headline"
                    parsed["headline"] = line.replace("HEADLINE:", "").strip()
                elif line.startswith("ARTICLE:"):
                    current_section = "article"
                    parsed["article"] = line.replace("ARTICLE:", "").strip()
                elif current_section and line:
                    parsed[current_section] += " " + line

            if not parsed["headline"] and not parsed["article"]:
                parsed["additional_content"] = response.strip()

        except Exception as e:
            logger.warning(f"Failed to parse LLaVA response: {e}")
            parsed["additional_content"] = response.strip()

        return parsed

    async def process_news_url(
        self,
        url: str,
        screenshot_path: str | None = None,
        mode: ProcessingMode = ProcessingMode.COMPREHENSIVE,
    ) -> ProcessingResult:
        """
        Process news URL with screenshot-based LLaVA analysis.

        Args:
            url: News article URL to process
            screenshot_path: Optional path for screenshot
            mode: Processing mode (fast or comprehensive)

        Returns:
            ProcessingResult with extracted content
        """
        start_time = time.time()
        logger.info(f"🔍 Processing news URL: {url}")

        try:
            if not isinstance(url, str) or not url.lower().startswith(
                ("http://", "https://")
            ):
                raise ValueError(f"Invalid URL: {url}")

            if not screenshot_path:
                screenshot_path = f"screenshot_{int(time.time())}.png"

            screenshot_path = await self.capture_webpage_screenshot(
                url, screenshot_path
            )
            llava_result = self.analyze_screenshot_with_llava(screenshot_path)

            if not llava_result["success"]:
                raise RuntimeError(
                    f"LLaVA analysis failed: {llava_result.get('error', 'Unknown error')}"
                )

            parsed_content = llava_result["parsed_content"]
            processing_time = time.time() - start_time

            result = ProcessingResult(
                content_type=ContentType.WEBPAGE,
                extracted_text=f"HEADLINE: {parsed_content.get('headline', '')}\n\nARTICLE: {parsed_content.get('article', '')}\n\nADDITIONAL: {parsed_content.get('additional_content', '')}",
                visual_description=llava_result["raw_analysis"],
                confidence_score=0.85 if llava_result["success"] else 0.0,
                processing_time=processing_time,
                model_outputs={"llava": llava_result},
                metadata={
                    "url": url,
                    "screenshot_path": screenshot_path,
                    "processing_mode": mode.value,
                    "models_used": ["llava"],
                },
                screenshot_path=screenshot_path,
            )

            logger.info(f"✅ Processing completed: {processing_time:.2f}s")
            return result

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Processing failed: {e}")

            return ProcessingResult(
                content_type=ContentType.WEBPAGE,
                extracted_text=f"Processing failed: {str(e)}",
                visual_description=f"Error processing URL: {url}",
                confidence_score=0.0,
                processing_time=processing_time,
                model_outputs={"error": str(e)},
                metadata={"url": url, "error": str(e)},
                screenshot_path=screenshot_path,
            )


# Export main components
__all__ = [
    "NewsReaderEngine",
    "NewsReaderConfig",
    "ContentType",
    "ProcessingMode",
    "ProcessingResult",
]
