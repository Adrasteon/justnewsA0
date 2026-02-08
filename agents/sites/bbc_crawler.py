"""Placeholder for the specialised BBC crawler.

The original implementation used a handcrafted parser for the BBC domain.  This
stub keeps the call site working while signalling to operators that the
optimised path is inactive.  When invoked it simply raises ``NotImplementedError``
so the generic crawler path can take over.
"""

from __future__ import annotations

from typing import Any


class UltraFastBBCCrawler:
    async def run_ultra_fast_crawl(
        self, max_articles: int, *, skip_ingestion: bool = False
    ) -> dict[str, Any]:
        raise NotImplementedError("UltraFastBBCCrawler is currently not implemented")
