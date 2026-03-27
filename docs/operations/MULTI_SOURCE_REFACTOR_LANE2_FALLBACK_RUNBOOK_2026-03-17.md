# Multi-Source Refactor Lane 2 Crawl Fallback Runbook

> Historical context note: This document may describe legacy startup/orchestration flows captured at the time. Canonical runtime for JustNews is Docker-first. See `docs/operations/DOCKER_FIRST_STRATEGY.md` and `docs/operations/DOCKER_CANONICAL_COMMANDS.md`.


Date: 2026-03-17
Status: Active
Owner: Ops / Crawler

## Purpose

Ensure the two-lane crawl flow can recover when the primary lane produces zero new ingest.

Behavior added:
- If initial crawl pass returns zero newly ingested articles, crawler can trigger a secondary lane fallback domain set.
- Fallback is opt-in and controlled by environment flags.

## Code References

- Crawler fallback implementation: `agents/crawler/crawler_engine.py`
- Unit test coverage: `tests/agents/test_crawler_engine.py`

## Runtime Controls

Core toggle:
- `UNIFIED_CRAWLER_LANE2_FALLBACK_ENABLED=1`

Optional controls:
- `UNIFIED_CRAWLER_LANE2_FALLBACK_DOMAINS=reuters.com,apnews.com,aljazeera.com,cnn.com,nytimes.com,theguardian.com`
- `UNIFIED_CRAWLER_LANE2_MAX_SITES=4`
- `UNIFIED_CRAWLER_LANE2_MAX_ARTICLES_PER_SITE=6`
- `UNIFIED_CRAWLER_LANE2_SEED_ENABLED=1`
- `UNIFIED_CRAWLER_LANE2_SEED_FILE=/app/config/lane2_sources_seed_phase.json`

Publication lane controls (orchestrator policy):
- `MULTI_SOURCE_LANE1_ENABLED=true`
- `MULTI_SOURCE_LANE2_ENABLED=true`

## Enablement Procedure

1. Set lane publication flags in `global.env`:
- `MULTI_SOURCE_LANE1_ENABLED=true`
- `MULTI_SOURCE_LANE2_ENABLED=true`

2. Enable crawler fallback:
- `UNIFIED_CRAWLER_LANE2_FALLBACK_ENABLED=1`

3. Keep or adjust fallback domain budget:
- `UNIFIED_CRAWLER_LANE2_MAX_SITES`
- `UNIFIED_CRAWLER_LANE2_MAX_ARTICLES_PER_SITE`

4. Restart services:

```bash
cd /app
bash stop_all_services.sh
bash start_all_services.sh
```

## Verification

### Unit Test

```bash
cd /app
/app/.venv/bin/pytest -q tests/agents/test_crawler_engine.py -k lane2_fallback_after_zero_ingest --disable-warnings --maxfail=1
```

Expected: `1 passed`.

### Runtime Smoke

Run a constrained crawl where primary domains are likely to return duplicates/zero-new, then verify fallback activity in crawler logs.

Expected log markers:
- `Lane2 fallback triggered after zero-ingest lane1 run`
- `Lane2 fallback summary`

### Health Checks

```bash
cd /app
curl -sS http://127.0.0.1:8022/health
curl -sS http://127.0.0.1:8023/health
```

## Rollback

Disable fallback without code rollback:
- `UNIFIED_CRAWLER_LANE2_FALLBACK_ENABLED=0`

If needed, also force single-lane publication routing:
- `MULTI_SOURCE_LANE2_ENABLED=false`

Restart services after changes.

## Notes

- If `UNIFIED_CRAWLER_LANE2_SEED_FILE` is missing or empty, crawler uses `UNIFIED_CRAWLER_LANE2_FALLBACK_DOMAINS`.
- Fallback path is only attempted when initial crawl total ingest is zero.
