"""
Web Capture Utilities.

Provides robust screenshot capture capabilities using Playwright.
Extracted from legacy NewsReader agent for common usage.
"""
from __future__ import annotations
import os
import logging
from dataclasses import dataclass, field
from typing import List, Optional

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    async_playwright = None
    PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger(__name__)

@dataclass
class ScreenshotConfig:
    headless: bool = True
    timeout: int = 30000
    browser_args: List[str] = field(default_factory=lambda: [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
    ])

class WebCaptureService:
    def __init__(self, config: Optional[ScreenshotConfig] = None):
        self.config = config or ScreenshotConfig()
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not installed. WebCaptureService will fail.")

    async def capture_screenshot(self, url: str, save_path: str) -> str:
        """
        Capture a screenshot of a webpage.
        
        Args:
            url: The URL to capture.
            save_path: The file path to save the screenshot to.
            
        Returns:
            The absolute path to the saved screenshot.
        """
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not available")

        if not url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL: {url}")

        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        
        logger.info(f"📸 Capturing screenshot: {url}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.config.headless,
                args=self.config.browser_args
            )
            page = None
            try:
                page = await browser.new_page()
                await page.goto(
                    url, 
                    wait_until="domcontentloaded", 
                    timeout=self.config.timeout
                )
                # Brief wait for dynamic content
                await page.wait_for_timeout(2000)
                
                await page.screenshot(path=save_path, full_page=False)
                logger.info(f"✅ Screenshot saved: {save_path}")
                return save_path
                
            except Exception as e:
                logger.error(f"❌ Screenshot failed: {e}")
                raise
            finally:
                if page:
                    await page.close()
                if browser:
                    await browser.close()
