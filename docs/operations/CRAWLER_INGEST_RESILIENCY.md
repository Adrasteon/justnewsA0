# Crawler Ingest Resiliency Runbook

## Purpose

This runbook documents the hardened ingest path used by `agents/crawler/crawler_engine.py` when downstream services (primarily `memory` via `mcp_bus`) are transiently unavailable.

## What changed

- Deferred ingest is now **disk-backed** instead of memory-only.
- Transient downstream failures are classified as `deferred` and written to a spool directory.
- Replay occurs in bounded batches on subsequent ingest cycles.
- Successful replay deletes the spooled item.
- Spool size is bounded with oldest-first pruning.

## Failure model

Requests are treated as transient/unavailable when one of the following occurs:

- HTTP status: `429`, `500`, `502`, `503`, `504`
- Known outage patterns in exception/body (connection refused, max retries exceeded, timeout, circuit open, temporary unavailable)

When transient:

1. article is marked deferred
2. spool item is written to disk
3. ingest route backoff window is applied

## Environment variables

### Core controls

- `UNIFIED_CRAWLER_INGEST_SPOOL_ENABLED` (default: `true`)
- `UNIFIED_CRAWLER_INGEST_SPOOL_DIR` (default inside crawler: `/tmp/justnews_ingest_spool`)
- `UNIFIED_CRAWLER_INGEST_SPOOL_MAX_ITEMS` (default: `2500`)
- `UNIFIED_CRAWLER_INGEST_SPOOL_REPLAY_BATCH` (default: `25`)
- `UNIFIED_CRAWLER_INGEST_MAX_INFLIGHT` (default: `6`)
- `UNIFIED_CRAWLER_INGEST_BACKOFF_SECONDS` (default: `8`)

### Memory-side load shedding (recommended during sustained pressure)

- `MEMORY_ESSENTIAL_MODE=true`

In essential mode, memory keeps core ingest behavior and skips optional heavy post-ingest work paths.

## Startup path defaults

The startup scripts now resolve persistent spool directories automatically for crawler:

1. explicit `UNIFIED_CRAWLER_INGEST_SPOOL_DIR` (if set)
2. `/media/adra/Data/justnews/spool/crawler_ingest`
3. `/media/adra/data/justnews/spool/crawler_ingest`
4. `/var/lib/justnews/spool/crawler_ingest` (if writable)
5. repo fallback (`/app/runtime/crawler_ingest_spool` for script-local paths)

## Operational checks

### Health

```bash
curl -sS http://localhost:8022/health
curl -sS http://localhost:8007/health
```

### Spool depth

```bash
find "$UNIFIED_CRAWLER_INGEST_SPOOL_DIR" -maxdepth 1 -name '*.json' | wc -l
```

### Inspect oldest deferred item

```bash
ls -1 "$UNIFIED_CRAWLER_INGEST_SPOOL_DIR"/*.json | sort | head -n 1 | xargs -r cat
```

## Recovery workflow

1. confirm memory and bus health
2. keep crawler running (replay is automatic)
3. monitor spool depth trend until stable decline
4. only if spool keeps growing, reduce ingest pressure:
   - lower `UNIFIED_CRAWLER_INGEST_MAX_INFLIGHT`
   - increase `UNIFIED_CRAWLER_INGEST_BACKOFF_SECONDS`
   - keep `MEMORY_ESSENTIAL_MODE=true`

## Guardrails

- Spool is bounded by `UNIFIED_CRAWLER_INGEST_SPOOL_MAX_ITEMS`.
- Oldest entries are pruned first when limit is exceeded.
- Disk-backed spool survives crawler process restarts.
- For host-reboot durability, use persistent volume-backed spool paths (not `/tmp`).
