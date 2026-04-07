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
make index-hermes-daily
make index-telemetry-summary
make index-status-report
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

Run the full daily Hermes refresh workflow:

```bash
make index-hermes-daily
bash scripts/indexing/daily_hermes_refresh.sh
```

This workflow runs session init bootstrap, incremental index refresh, bootstrap JSON snapshot,
and a telemetry summary in one pass.

## Lightweight Telemetry

All indexing scripts can write newline-delimited JSON events.

- Default log file: `run/indexing_telemetry.jsonl`
- Event types: `index_build`, `index_query`, `index_autoupdate`
- `index_query` events now include estimated token savings fields:
  - `tokenizer_model` (resolved from selected Copilot chat model by default)
  - `tokenizer_model_source`
  - `tokenizer_backend` (`tiktoken:model`, `tiktoken:encoding`, or `chars_per_token` fallback)
  - `tokenizer_encoding`
  - `exact_token_counting`
  - `indexed_snippet_tokens`
  - `baseline_snippet_tokens`
  - `token_savings`
  - `token_savings_pct`
  - legacy-compatible mirrors are still emitted:
  - `indexed_snippet_tokens_estimate`
  - `baseline_snippet_tokens_estimate`
  - `estimated_token_savings`
  - `estimated_token_savings_pct`
  - Uses selected Copilot chat model tokenization when `tiktoken` is available.
  - Falls back to `chars_per_token` estimator (default `4.0`) when exact tokenizer resolution is unavailable.
  - Session init persists a deterministic model binding in `run/copilot_chat_model.env`.
    - `query_code_index.py` reads this binding when runtime env vars are absent.

Examples:

```bash
python scripts/indexing/build_code_index.py --root . --index-dir .cache/code_index --telemetry-path run/indexing_telemetry.jsonl
python scripts/indexing/query_code_index.py "publish republish taxonomy" --root . --index-dir .cache/code_index --telemetry-path run/indexing_telemetry.jsonl
python scripts/indexing/autonomous_index_update.py --root . --index-dir .cache/code_index --telemetry-path run/indexing_telemetry.jsonl

# optional: tune token estimator ratio
python scripts/indexing/query_code_index.py "publish republish taxonomy" --root . --index-dir .cache/code_index --chars-per-token 4.0

# optional: force a specific tokenizer model or encoding fallback
python scripts/indexing/query_code_index.py "publish republish taxonomy" --root . --index-dir .cache/code_index --tokenizer-model gpt-5.3-codex --tokenizer-fallback-encoding o200k_base

# default behavior reads selected chat model env vars, then persisted binding file, then default
python scripts/indexing/session_chat_init.sh
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

Report token reduction trend and explicit health confirmation:

```bash
make index-status-report
python scripts/indexing/token_health_report.py --telemetry-path run/indexing_telemetry.jsonl --index-dir .cache/code_index --daemon-script scripts/indexing/index_autoupdate_daemon.sh
```

The report includes direct confirmation lines for:
- `DAEMON_ACTIVE: YES|NO`
- `INDEX_HEALTHY: YES|NO`
- `TOKEN_REDUCTION_ACTIVE: YES|NO`

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
