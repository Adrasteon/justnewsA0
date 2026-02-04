#!/usr/bin/env python3
"""
Crawler Enhancements Demo Script

This script demonstrates how to use the crawler enhancements package
to improve resilience against anti-scraping measures.
"""

import asyncio
import json
import os
from pathlib import Path

from agents.crawler.enhancements import (
    ModalHandler,
    PaywallDetector,
    PIASocks5Manager,
    ProxyManager,
    StealthBrowserFactory,
)
from agents.crawler.enhancements.proxy_manager import ProxyDefinition
from agents.crawler.enhancements.ua_rotation import UserAgentConfig, UserAgentProvider


def load_global_env():
    """Load environment variables from global.env file."""
    global_env_path = Path(__file__).parent.parent.parent.parent / "global.env"
    if global_env_path.exists():
        print(f"Loading environment variables from {global_env_path}")
        with open(global_env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key] = value
                        print(
                            f"  Set {key}={value[:10]}{'...' if len(value) > 10 else ''}"
                        )
    else:
        print(f"Warning: global.env not found at {global_env_path}")


def demo_modal_handler():
    """Demonstrate modal handler functionality."""
    print("=== Modal Handler Demo ===")

    # Sample HTML with a consent modal
    html_with_modal = """
    <html>
    <body>
        <div id="consent-modal" class="modal-overlay">
            <div class="modal-content">
                <p>We use cookies to improve your experience.</p>
                <button id="accept-cookies">Accept All</button>
            </div>
        </div>
        <article>
            <h1>Breaking News: Important Article</h1>
            <p>This is the main content of the article.</p>
        </article>
    </body>
    </html>
    """

    handler = ModalHandler(
        consent_cookie_name="cookie_consent", consent_cookie_value="accepted"
    )
    result = handler.process(html_with_modal)

    print(f"Modal detected: {result.modals_detected}")
    print(f"Cleaned HTML length: {len(result.cleaned_html)}")
    print(f"Applied cookies: {result.applied_cookies}")
    print()


def demo_user_agent_rotation():
    """Demonstrate user agent rotation."""
    print("=== User Agent Rotation Demo ===")

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    ]

    per_domain = {
        "bbc.co.uk": ["BBC News App/1.0 (iOS)"],
        "nytimes.com": [
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15"
        ],
    }

    provider = UserAgentProvider(
        config=UserAgentConfig(pool=user_agents, per_domain_overrides=per_domain)
    )

    print("General rotation:")
    for i in range(3):
        ua = provider.choose()
        print(f"  {i + 1}. {ua}")

    print("\nDomain-specific:")
    for domain in ["bbc.co.uk", "nytimes.com", "example.com"]:
        ua = provider.choose(domain=domain)
        print(f"  {domain}: {ua}")
    print()


def demo_proxy_manager():
    """Demonstrate proxy manager functionality."""
    print("=== Proxy Manager Demo ===")

    proxies = [
        ProxyDefinition(url="http://proxy1.example.com:8080"),
        ProxyDefinition(url="http://proxy2.example.com:8080"),
        ProxyDefinition(url="http://proxy3.example.com:8080"),
    ]

    manager = ProxyManager(proxies)

    print("Proxy rotation:")
    for i in range(5):
        proxy = manager.next_proxy()
        print(f"  {i + 1}. {proxy.url}")
    print()


def demo_pia_socks5():
    """Demonstrate PIA SOCKS5 proxy functionality."""
    print("=== PIA SOCKS5 Proxy Demo ===")

    try:
        # Check if PIA credentials are available
        if not PIASocks5Manager.is_available():
            print("❌ PIA SOCKS5 credentials not found in environment variables")
            print("   Set PIA_SOCKS5_USERNAME and PIA_SOCKS5_PASSWORD to test")
            return

        manager = PIASocks5Manager()
        proxy = manager.get_proxy()

        print("✅ PIA SOCKS5 proxy initialized")
        print(f"   URL: {proxy.url}")
        print(f"   Provider: {proxy.metadata.get('provider', 'unknown')}")
        print(f"   Host: {proxy.metadata.get('host', 'unknown')}")
        print(f"   Speed: {proxy.metadata.get('speed', 'unknown')}")

        # Test proxy URL generation
        url = manager.get_proxy_url()
        print(f"   Full proxy URL: {url}")

    except Exception as e:
        print(f"❌ PIA SOCKS5 initialization failed: {e}")
    print()


def demo_stealth_browser():
    """Demonstrate stealth browser profiles."""
    print("=== Stealth Browser Demo ===")

    profiles = [
        {
            "accept_language": "en-US,en;q=0.9",
            "accept_encoding": "gzip, deflate, br",
            "headers": {"DNT": "1", "Upgrade-Insecure-Requests": "1"},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
        {
            "accept_language": "en-GB,en;q=0.9",
            "accept_encoding": "gzip, deflate, br",
            "headers": {"DNT": "1", "Sec-Fetch-Site": "same-origin"},
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        },
    ]

    factory = StealthBrowserFactory(profiles=profiles)

    print("Random profile selection:")
    for i in range(3):
        profile = factory.random_profile()
        print(f"  Profile {i + 1}:")
        print(f"    User-Agent: {profile.user_agent}")
        print(f"    Accept-Language: {profile.accept_language}")
        print(f"    Headers: {dict(profile.headers)}")
        print()


async def demo_paywall_detector():
    """Demonstrate paywall detector functionality."""
    print("=== Paywall Detector Demo ===")

    # Sample paywalled content
    paywalled_html = """
    <html>
    <body>
        <div class="paywall-overlay">
            <h2>Subscribe to Continue Reading</h2>
            <p>You've reached your monthly article limit.</p>
        </div>
        <article>
            <h1>Exclusive: Breaking News Story</h1>
            <p class="paywall-content">This content is behind a paywall...</p>
        </article>
    </body>
    </html>
    """

    detector = PaywallDetector(enable_remote_analysis=False)

    result = await detector.analyze(
        url="https://example.com/premium-article",
        html=paywalled_html,
        text="Subscribe to Continue Reading You've reached your monthly article limit.",
    )

    print(f"Paywall detected: {result.is_paywall}")
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Should skip: {result.should_skip}")
    print(f"Reasons: {result.reasons}")
    print()


def demo_configuration():
    """Show example configuration."""
    print("=== Configuration Example ===")

    config = {
        "crawling": {
            "enhancements": {
                "enable_user_agent_rotation": True,
                "enable_proxy_pool": True,
                "enable_modal_handler": True,
                "enable_paywall_detector": True,
                "enable_stealth_headers": True,
                "user_agent_pool": [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                ],
                "per_domain_user_agents": {"bbc.co.uk": ["BBC News App/1.0"]},
                "proxy_pool": [
                    "http://proxy1.example.com:8080",
                    "http://proxy2.example.com:8080",
                ],
                "stealth_profiles": [
                    {
                        "accept_language": "en-US,en;q=0.9",
                        "accept_encoding": "gzip, deflate, br",
                        "headers": {"DNT": "1"},
                        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    }
                ],
                "consent_cookie": {"name": "cookie_consent", "value": "accepted"},
                "paywall_detector": {
                    "enable_remote_analysis": False,
                    "max_remote_chars": 6000,
                },
                "enable_pia_socks5": True,
                "pia_socks5_username": "${PIA_SOCKS5_USERNAME}",
                "pia_socks5_password": "${PIA_SOCKS5_PASSWORD}",
            }
        }
    }

    print("Example system_config.json snippet:")
    print(json.dumps(config, indent=2))
    print()


async def main():
    """Run all demonstrations."""
    print("Crawler Enhancements Demo")
    print("=" * 50)
    print()

    # Load environment variables from global.env
    load_global_env()
    print()

    demo_configuration()
    demo_user_agent_rotation()
    demo_proxy_manager()
    demo_pia_socks5()
    demo_stealth_browser()
    demo_modal_handler()
    await demo_paywall_detector()

    print("Demo completed!")


if __name__ == "__main__":
    asyncio.run(main())
