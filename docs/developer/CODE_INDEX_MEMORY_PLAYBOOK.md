# Code Index + Memory Playbook

This playbook implements a practical retrieval workflow for this repository with two goals:

1. Higher edit accuracy by narrowing context before code changes.
2. Lower token usage by reading targeted snippets instead of whole files.

## What Is Implemented

The repository now includes local tooling in `scripts/indexing/`:

1. `build_code_index.py`
- Builds an incremental index of tracked and local untracked indexable source files.
- Stores artifacts in `.cache/code_index/`.
- Reuses unchanged files using per-file SHA-1 metadata.
- Extracts both text chunks and Python symbols (`class`, `function`, `async function`).

2. `query_code_index.py`
- Performs two-stage retrieval.
- Stage A: lexical recall from index entries.
- Stage B: precise file-window snippets around best hits.
- Automatically refreshes index artifacts when stale, missing, or when tracked files change.

3. `autonomous_index_update.py`
- Timer-safe wrapper for periodic index refresh.
- Used by systemd user timer for hands-off maintenance.

The `Makefile` includes helper targets:

1. `make index-build`
2. `make index-build-full`
3. `make index-query QUERY='your phrase here'`
4. `make index-auto-install`
5. `make index-auto-enable`
6. `make index-auto-status`
7. `make index-auto-disable`
8. `make index-telemetry-summary`
9. `make index-bootstrap`
10. `make index-bootstrap-json`

## Recommended Workflow Per Task

0. Optional fresh-chat bootstrap.
```bash
make index-bootstrap
make index-bootstrap-json
```

1. Refresh index incrementally.
```bash
make index-build
```

2. Query intent, API, or symptom.
```bash
make index-query QUERY='datetime timezone utc publication metadata'
```

3. Read only returned file windows.
- Use snippets as candidate context.
- Open exact files/lines for edits.

4. Re-verify after edits.
- Re-run focused index queries.
- Run targeted tests.

Note: `index-query` performs autonomous staleness checks and refreshes by default.

## Why This Reduces Token Use

1. Avoids full-file reads for initial discovery.
2. Reuses index artifacts between tasks.
3. Forces precision reads in Stage B before editing.

## Lightweight Telemetry

Telemetry is intentionally low-overhead and file-based.

1. Event log path
- Default is `run/indexing_telemetry.jsonl`.
- Override with `TELEMETRY_PATH=...` when using Make targets.

2. Event types
- `index_build`: emitted by `build_code_index.py`.
- `index_query`: emitted by `query_code_index.py`.
- `index_autoupdate`: emitted by `autonomous_index_update.py`.

3. Quick metrics
```bash
make index-telemetry-summary
```

4. Custom window
```bash
python scripts/indexing/telemetry_summary.py --path run/indexing_telemetry.jsonl --last 1000
```

5. Disable telemetry for one command
```bash
python scripts/indexing/query_code_index.py "your query" --root . --index-dir .cache/code_index --no-telemetry
```

## Persistent Memory Strategy

Use three scopes intentionally:

1. User memory (`/memories/`)
- Stable preferences and interaction defaults.
- Keep entries short and durable.

2. Repo memory (`/memories/repo/`)
- Operational facts and verified repo conventions.
- Example: startup command quirks, test runner path, indexing pitfalls.

3. Session memory (`/memories/session/`)
- Temporary plan state and active hypotheses.
- Clear at session end.

## Memory Entry Format (High Signal)

Use concise bullet points with this shape:

- Fact: One verified behavior or rule.
- Evidence: Where it came from (file, command, test result).
- Action: How to use it next time.

Example:

- Fact: `pytest` may be unavailable on system Python in dev-container.
- Evidence: command `pytest -q ...` returned `command not found`.
- Action: use `/app/.venv/bin/python -m pytest` for validation.

## Index Maintenance Cadence

1. Enable periodic updater once per environment.
```bash
make index-auto-install
make index-auto-enable
```

If systemd user bus is unavailable, `index-auto-enable` starts a daemon fallback
(`scripts/indexing/index_autoupdate_daemon.sh`) with the same periodic intent.

2. Run `make index-build` when you want an immediate manual refresh.

3. Run `make index-build-full` only when:
- Index artifacts were deleted.
- Large refactors moved many files.
- Retrieval quality degrades unexpectedly.

4. Keep `.cache/code_index/` untracked (already ignored in `.gitignore`).

## Troubleshooting

1. "No index entries found"
- Build index first: `make index-build`.

2. Results look stale
- Force rebuild: `make index-build-full`.

3. Query too broad
- Add symbol names, endpoint names, or env vars to query text.

## Optional Extensions

1. Add per-language symbol extraction (SQL DDL names, shell functions).
2. Add recency bias using `git log` to prioritize recently changed files.
3. Add lightweight command that writes top retrieval hits into session memory.
