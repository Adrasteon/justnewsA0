"""Utility to compare Crawl4AI profile variants for a single domain.

This script replays the manual experiment we just ran in the REPL: it loads the
configured Crawl4AI profile for a given domain, synthesises a few variant
configurations (adaptive defaults, adaptive with relaxed thresholds, link
preview only, and single-page only), and executes each variant via
``crawl_site_with_crawl4ai`` while requesting up to ``--max-articles`` results.

Usage:
    python scripts/dev/crawl4ai_profile_variants_probe.py --domain bbc.co.uk \
        --max-articles 10
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
from pathlib import Path
from typing import Any

from agents.crawler.crawl4ai_adapter import crawl_site_with_crawl4ai
from agents.crawler_control.crawl_profiles import load_crawl_profiles
from agents.sites.generic_site_crawler import SiteConfig


def _build_variants(base_profile: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return the profile variants we want to probe."""
    variants: list[tuple[str, dict[str, Any]]] = []

    # Variant 1: baseline adaptive profile
    variants.append(("adaptive_default", copy.deepcopy(base_profile)))

    # Variant 2: adaptive with looser thresholds and higher depth/budget
    adaptive_deep = copy.deepcopy(base_profile)
    adaptive_block = adaptive_deep.setdefault("adaptive", {})
    # Loosen the scoring thresholds to encourage deeper traversal
    adaptive_block["confidence_threshold"] = min(
        0.3, adaptive_block.get("confidence_threshold", 0.5)
    )
    adaptive_block["max_depth"] = max(6, adaptive_block.get("max_depth", 5) or 5)
    adaptive_block["max_pages"] = max(60, adaptive_block.get("max_pages", 20) or 20)
    adaptive_block["top_k_links"] = max(15, adaptive_block.get("top_k_links", 10) or 10)
    adaptive_block["min_gain_threshold"] = 0.005
    adaptive_deep["max_pages"] = max(80, adaptive_deep.get("max_pages", 0) or 0)
    variants.append(("adaptive_deep", adaptive_deep))

    # Variant 3: strip adaptive config, rely on link preview scoring only
    link_preview_only = copy.deepcopy(base_profile)
    link_preview_only.pop("adaptive", None)
    link_preview_only.setdefault("extra", {}).pop("query", None)
    link_preview_only["mode"] = "link_preview"
    link_preview_only["max_pages"] = max(80, link_preview_only.get("max_pages", 0) or 0)
    link_preview = link_preview_only.setdefault("link_preview", {})
    link_preview["score_threshold"] = 0.0
    link_preview["max_links"] = max(50, link_preview.get("max_links", 0) or 0)
    variants.append(("link_preview_only", link_preview_only))

    # Variant 4: single-page fetch with traversal disabled
    single_page = copy.deepcopy(base_profile)
    single_page.pop("adaptive", None)
    single_page["follow_internal_links"] = False
    single_page["link_preview"] = {}
    single_page.setdefault("extra", {}).pop("query", None)
    single_page["mode"] = "single_page"
    single_page["max_pages"] = min(10, single_page.get("max_pages", 10) or 10)
    variants.append(("single_page", single_page))

    return variants


async def _run_variant(
    variant_name: str,
    profile: dict[str, Any],
    site_config: SiteConfig,
    max_articles: int,
    follow_external: bool | None = None,
) -> dict[str, Any]:
    try:
        articles = await crawl_site_with_crawl4ai(
            site_config,
            profile,
            max_articles=max_articles,
            follow_external=follow_external,
        )
    except Exception as exc:  # noqa: BLE001 - keep probe resilient
        return {"error": str(exc)}

    summary = {
        "count": len(articles),
        "sample_urls": [article.get("url") for article in articles[:3]],
        "titles": [article.get("title") for article in articles[:3]],
    }
    return summary


async def _run_probe(args: argparse.Namespace) -> dict[str, Any]:
    registry = load_crawl_profiles(args.profiles)
    base_profile_obj = registry.for_domain(args.domain)
    if base_profile_obj is None:
        raise SystemExit(f"No crawl profile found for domain: {args.domain}")

    base_payload = base_profile_obj.payload_for_domain(args.domain)
    variants = _build_variants(base_payload)

    site_config = SiteConfig(
        {
            "domain": args.domain,
            "url": base_payload.get("start_urls", [f"https://{args.domain}"])[0],
            "name": args.domain,
        }
    )

    results: dict[str, Any] = {}
    # Interpret CLI NoFollow (string 'true'/'false') into follow_external boolean
    if args.NoFollow is None:
        follow_external_override = None
    else:
        follow_external_override = str(args.NoFollow).lower() not in (
            "1",
            "true",
            "yes",
        )

    for name, profile in variants:
        print(f"Running variant {name}...")
        result = await _run_variant(
            name,
            profile,
            site_config,
            args.max_articles,
            follow_external=follow_external_override,
        )
        print(f"Variant {name} result: {result}\n")
        results[name] = result

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe Crawl4AI profile variants for a domain"
    )
    parser.add_argument(
        "--domain", default="bbc.co.uk", help="Domain to test (default: bbc.co.uk)"
    )
    parser.add_argument(
        "--profiles",
        type=Path,
        default=Path("config/crawl_profiles"),
        help="Path to crawl profiles directory or YAML file",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=10,
        help="Maximum articles to request per variant (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the JSON summary",
    )
    parser.add_argument(
        "--NoFollow",
        choices=("true", "false"),
        default=None,
        help="Explicitly disable following external links for the probe variants (true|false). If omitted then profile/env defaults apply",
    )
    args = parser.parse_args()

    results = asyncio.run(_run_probe(args))

    print("=== Summary ===")
    print(json.dumps(results, indent=2))

    if args.output:
        args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Summary written to {args.output}")


if __name__ == "__main__":
    main()
