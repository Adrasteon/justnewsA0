# Crawler Control — Advanced Crawl4AI Options

This guide describes how to drive crawl depth and advanced Crawl4AI behavior through `crawler_control` on port `8016`.

## Endpoints

- Manual/API: `POST /api/crawl/start`
- Programmatic (MCP tool): `POST /start_crawl`
- Option discovery: `GET /api/crawl/options`

## Request Pattern

`crawler_control` now accepts a `crawl4ai` object and translates it into crawler `profile_overrides` per target domain.

Example (`/api/crawl/start`):

```json
{
  "domains": "sources 25",
  "max_articles_per_site": 8,
  "concurrent_sites": 3,
  "crawl4ai": {
    "crawl_depth": 2,
    "max_pages": 30,
    "follow_internal_links": true,
    "follow_external": false,
    "run_config": {
      "cache_mode": "bypass",
      "word_count_threshold": 120,
      "score_links": true
    },
    "browser_config": {
      "headless": true,
      "ignore_https_errors": true
    },
    "link_preview": {
      "include_patterns": ["/news", "/world"],
      "exclude_patterns": ["/live", "/video"],
      "max_links": 25
    }
  }
}
```

## Most Useful Parameters for JustNews

### 1) Crawl scope & depth

- `crawl4ai.crawl_depth` (new): max link-hop depth from each seed URL.
  - `0` = seed page only
  - `1` = seed + one level of internal links
- `crawl4ai.max_pages`: hard page budget per domain profile.
- `crawl4ai.follow_internal_links`: enables/disables link expansion.
- `crawl4ai.follow_external`: allow/disallow crossing to external domains.

### 2) Extraction quality controls (`crawl4ai.run_config`)

- `word_count_threshold`: reduce short/noisy pages.
- `excluded_tags` / `target_elements`: steer extraction to article content.
- `remove_overlay_elements`: remove popups/cookie overlays.
- `process_iframes`: include iframe content when needed.
- `wait_for` / `wait_for_timeout`: stabilize JS-heavy pages.
- `js_code`: scripted interaction before extraction.
- `score_links`: prioritize promising links.
- `cache_mode`: control Crawl4AI cache behavior.

### 3) Link prioritization (`crawl4ai.link_preview`)

- `include_patterns`: bias to article sections (`/news`, `/world`, etc.).
- `exclude_patterns`: skip noisy paths (`/live`, `/video`, `/sport`, etc.).
- `max_links`: cap fan-out per page.
- `score_threshold`: minimum score for link expansion.

### 4) Browser/runtime behavior (`crawl4ai.browser_config`)

- `headless`: default for server runs.
- `user_agent`: domain-specific identity tuning.
- `proxy`: geography/routing control for source access.
- `ignore_https_errors`: resilience for problematic TLS endpoints.
- `extra_args`: browser process hardening/tuning.

### 5) Adaptive crawling (`crawl4ai.adaptive`)

- Use for query-driven discovery and better recall on broad topic pages.
- Works best with tuned `link_preview` and `run_config` constraints.

## Programmatic Usage

For MCP-style calls to `/start_crawl`, pass:

- `args[0]` as domains string/list style used today, or
- `kwargs.domains` for direct programmatic invocation,
- optional `kwargs.crawl4ai` and/or `kwargs.profile_overrides`.

`crawler_control` merges generated profile defaults from `crawl4ai` and domain-specific entries in `profile_overrides`.

## Runtime Yield Tuning (Dedupe Replacement)

UI and API controls define crawl scope and candidate quality, but final new-article yield is also affected by ingestion dedupe. To improve chance of hitting requested new-article targets:

- `UNIFIED_CRAWLER_DEDUPE_REPLACEMENT_FACTOR` (default `3`)
  - Increases candidate oversampling so replacements are available when early candidates dedupe.
- `UNIFIED_CRAWLER_MAX_REQUEST_CAP` (default `150`)
  - Caps per-batch candidate request size to avoid excessive fetches.

Practical guidance:

- If jobs under-deliver due to duplicates, increase replacement factor gradually (`3 -> 4 -> 5`).
- If crawl cost/latency grows too high, lower replacement factor or lower request cap.
