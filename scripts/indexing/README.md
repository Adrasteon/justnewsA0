# Local Indexing Scripts

These scripts provide dependency-free local retrieval for the workspace.

## Scripts

1. `build_code_index.py`
- Builds an incremental index in `.cache/code_index/`.
- Tracks unchanged files by SHA-1 to avoid full rebuilds.

2. `query_code_index.py`
- Two-stage retrieval:
  - Stage A recall from index entries.
  - Stage B precision snippets from exact file windows.

3. `autonomous_index_update.py`
- Timer-friendly wrapper that refreshes the local index.
- Intended for periodic execution (systemd user timer).

## Usage

```bash
python scripts/indexing/build_code_index.py --root . --index-dir .cache/code_index
python scripts/indexing/query_code_index.py "workflow publish republish" --root . --index-dir .cache/code_index
```

Or via Makefile:

```bash
make index-build
make index-query QUERY='workflow publish republish'
make index-auto-install
make index-auto-enable
make index-bootstrap
make index-bootstrap-json
make index-telemetry-summary
```

Use bootstrap for fresh chats or handoffs. It reports index artifact status,
telemetry snapshot, daemon fallback status, and the first files to read.

```bash
make index-bootstrap
python scripts/indexing/bootstrap_context.py --root . --index-dir .cache/code_index --telemetry-path run/indexing_telemetry.jsonl --json
```

Write a JSON snapshot to file:

```bash
make index-bootstrap-json
BOOTSTRAP_JSON_PATH=run/custom_bootstrap.json make index-bootstrap-json
```

## Lightweight Telemetry

All indexing scripts can write newline-delimited JSON events.

- Default log file: `run/indexing_telemetry.jsonl`
- Event types: `index_build`, `index_query`, `index_autoupdate`

Examples:

```bash
python scripts/indexing/build_code_index.py --root . --index-dir .cache/code_index --telemetry-path run/indexing_telemetry.jsonl
python scripts/indexing/query_code_index.py "publish republish taxonomy" --root . --index-dir .cache/code_index --telemetry-path run/indexing_telemetry.jsonl
python scripts/indexing/autonomous_index_update.py --root . --index-dir .cache/code_index --telemetry-path run/indexing_telemetry.jsonl
```

Disable telemetry for a single run:

```bash
python scripts/indexing/query_code_index.py "your query" --root . --index-dir .cache/code_index --no-telemetry
```

Summarize recent telemetry:

```bash
make index-telemetry-summary
python scripts/indexing/telemetry_summary.py --path run/indexing_telemetry.jsonl --last 1000
```

## Autonomous Behavior

1. On-query auto-refresh:
- `query_code_index.py` now auto-refreshes when index artifacts are missing,
  stale by age, or tracked workspace files changed.
- Disable if needed with `--no-auto-refresh`.

2. Periodic refresh:
- Install and enable the user timer with `make index-auto-install` and
  `make index-auto-enable`.
- Defaults to every 15 minutes after boot.
- If systemd user bus is unavailable (common inside some containers), the Make
  target automatically falls back to a background daemon script:
  `scripts/indexing/index_autoupdate_daemon.sh`.
