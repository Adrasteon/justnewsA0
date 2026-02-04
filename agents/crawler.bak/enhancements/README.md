# Crawler Enhancements Package

This package provides modular, configurable enhancements for the JustNews crawler to improve resilience against anti-
scraping measures and access restricted content.

## Overview

The crawler enhancements include five main components:

1. **Modal Handler** - Detects and removes consent overlays, cookie banners, and sign-in modals

1. **Paywall Detector** - Identifies paywalled content and provides metadata for filtering

1. **User Agent Rotation** - Rotates user agents for browser fingerprinting evasion

1. **Proxy Manager** - Manages proxy pools for IP diversity and anti-detection

1. **Stealth Browser** - Applies stealth headers and browser simulation techniques

## Architecture

All enhancements are designed to be:

- **Optional**: Default to disabled for backward compatibility

- **Modular**: Independent components that can be used separately

- **Configurable**: Full configuration through the system config schema

- **Resilient**: Graceful error handling with fallback behavior

## Configuration

Enhancements are configured through the `crawling.enhancements`section of`config/system_config.json`:

```json
{
  "crawling": {
    "enhancements": {
      "enable_user_agent_rotation": false,
      "enable_proxy_pool": false,
      "enable_modal_handler": false,
      "enable_paywall_detector": false,
      "enable_stealth_headers": false,
      "user_agent_pool": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
      ],
      "per_domain_user_agents": {
        "bbc.co.uk": ["BBC News App/1.0"],
        "nytimes.com": ["Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15"]
      },
      "proxy_pool": [
        "http://proxy1.example.com:8080","http://proxy2.example.com:8080"
      ],
      "stealth_profiles": [
        {
          "accept_language": "en-US,en;q=0.9",
          "accept_encoding": "gzip, deflate, br",
          "headers": {
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1"
          },
          "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
      ],
      "consent_cookie": {
        "name": "justnews_cookie_consent",
        "value": "1"
      },
      "paywall_detector": {
        "enable_remote_analysis": false,
        "max_remote_chars": 6000
      }
    }
  }
}

```bash

## Components

### Modal Handler

**Purpose**: Detects and removes consent overlays, cookie banners, and sign-in modals that interfere with content
extraction.

**Features**:

- Pattern-based modal detection

- Synthetic consent cookie injection

- HTML cleaning before extraction

- Modal detection logging

**Usage**:

```python
from agents.crawler.enhancements import ModalHandler

handler = ModalHandler(consent_cookie={"name": "cookie_consent", "value": "accepted"})
result = handler.process(html_content)
clean_html = result.cleaned_html

## Apply cookies to session

session.cookies.update(result.applied_cookies)

```

### Paywall Detector

**Purpose**: Identifies paywalled content and provides metadata for filtering decisions.

**Features**:

- Heuristic paywall detection

- Optional MCP-based remote analysis

- Confidence scoring and reasoning

- Article metadata annotation

**Usage**:

```python
from agents.crawler.enhancements import PaywallDetector

detector = PaywallDetector(enable_remote=True, max_remote_chars=5000)
result = await detector.analyze(
    url="https://example.com/article",html="<html>...</html>",
    text="Article content..."
)

if result.should_skip:
    print(f"Skipping paywalled article: {result.reasons}")

```bash

### User Agent Rotation

**Purpose**: Rotates user agents to avoid browser fingerprinting detection.

**Features**:

- Domain-specific user agent pools

- Deterministic rotation strategies

- Configurable pool management

- Fallback to default user agents

**Usage**:

```python
from agents.crawler.enhancements import UserAgentProvider

provider = UserAgentProvider(
    pool=["UA1", "UA2", "UA3"],
    per_domain={"example.com": ["Special UA"]}
)

ua = provider.choose(domain="example.com")

```

### Proxy Manager

**Purpose**: Manages proxy pools for IP diversity and anti-detection.

**Features**:

- Round-robin proxy rotation

- Proxy health monitoring

- HTTP/HTTPS proxy support

- Automatic failure recovery

**Usage**:

```python
from agents.crawler.enhancements import ProxyManager

manager = ProxyManager(["http://proxy1:8080","http://proxy2:8080"])
proxy = manager.next_proxy()

## Use with requests

response = requests.get(url, proxies={"http": proxy.url, "https": proxy.url})

```bash

### Stealth Browser

**Purpose**: Applies stealth headers and browser simulation techniques.

**Features**:

- Configurable header profiles

- Accept-Language customization

- Browser fingerprinting evasion

- Profile-based header injection

**Usage**:

```python
from agents.crawler.enhancements import StealthBrowserFactory

factory = StealthBrowserFactory(profiles=[{
    "accept_language": "en-US,en;q=0.9",
    "accept_encoding": "gzip, deflate, br",
    "headers": {"DNT": "1"},
    "user_agent": "Custom UA"
}])

profile = factory.random_profile()

## Apply to request headers

headers = profile.headers.copy()
headers["User-Agent"] = profile.user_agent

```

## Integration

Enhancements are automatically integrated into the `CrawlerEngine`and`GenericSiteCrawler` when enabled in
configuration. The crawler engine instantiates helpers based on config and passes them to crawlers.

### Manual Integration

For custom crawler implementations:

```python
from agents.crawler.enhancements import (
    ModalHandler, PaywallDetector, ProxyManager,
    StealthBrowserFactory, UserAgentProvider
)
from config import get_crawling_config

config = get_crawling_config()
enhancements = config.enhancements

## Instantiate helpers conditionally

helpers = {}
if enhancements.enable_modal_handler:
    helpers['modal_handler'] = ModalHandler(consent_cookie=enhancements.consent_cookie)
if enhancements.enable_paywall_detector:
    helpers['paywall_detector'] = PaywallDetector(
        enable_remote=enhancements.paywall_detector.enable_remote_analysis,
        max_remote_chars=enhancements.paywall_detector.max_remote_chars
    )

## ... other helpers

## Use in crawler logic

if 'modal_handler' in helpers:
    result = helpers['modal_handler'].process(html)
    html = result.cleaned_html

```bash

## Error Handling

All enhancements include comprehensive error handling:

- Exceptions are logged but don't crash the crawler

- Features degrade gracefully when components fail

- Fallback behavior ensures crawler continues operating

- Optional features can be disabled individually

## Performance Considerations

- **Memory**: Minimal overhead when disabled, small memory footprint when enabled

- **Network**: Proxy rotation and remote paywall analysis add network requests

- **CPU**: Modal processing and paywall detection add minor CPU overhead

- **Configuration**: Enable only needed enhancements for optimal performance

## Testing

Run enhancement tests:

```bash
python -m pytest tests/agents/crawler/test_enhancements.py -v

```

Test crawler integration:

```bash
python -m pytest tests/agents/crawler/test_generic_site_crawler.py -v

```

## Troubleshooting

### Common Issues

1. **Modal handler not working**: Check consent cookie configuration matches site requirements

1. **Paywall detection false positives**: Adjust confidence thresholds or disable remote analysis

1. **Proxy failures**: Verify proxy URLs are accessible and properly formatted

1. **User agent issues**: Ensure user agents are current and site-compatible

### Debugging

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG

```

Check crawler logs for enhancement-specific messages:

```bash
tail -f agents/crawler/crawler_engine.log | grep -i enhancement

```</content>
<parameter name="filePath">/home/adra/JustNewsAgent- Clean/agents/crawler/enhancements/README.md
