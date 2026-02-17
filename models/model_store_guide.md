# Model Store Guide

This guide consolidates the historical documentation from the `justnews/maint/cleanup` branch into a single reference
for designing, operating, and extending the shared model store that backs JustNews agents.

## Purpose

- Provide atomic, versioned delivery of per-agent model artifacts.

- Ensure readers never observe partially written models.

- Keep deployment and permissions simple enough for bare-metal and systemd based installations.

## Canonical Layout

```bash

MODEL_STORE_ROOT/
  <agent>/
    versions/
      <version>/              # Fully materialized model
      <version>.tmp/          # Temporary staging location
    current -> versions/<version>

```

- Default on-prem path: `/opt/justnews/models`.

- All operations must occur on the same filesystem to preserve atomic rename and symlink semantics.

- In legacy environments you may still encounter alias symlinks such as `news-cleaner-agent -> synthesizer`. Keep the
  canonical`<agent>/…` layout authoritative; if those aliases exist, treat them as read-only compatibility shims rather
  than the source of truth.

## Lifecycle

1. **Stage** – Writers obtain a temporary directory via `ModelStore.stage_new(agent, version)`and populate the full
   model payload inside`<version>.tmp`.

1. **Validate & Manifest** – `ModelStore.finalize(...)`computes a deterministic SHA-256 checksum, writes`manifest.json`,
   and renames the directory to`<version>`.

1. **Publish** – Finalize atomically updates the `current`symlink (`os.replace`) so running agents immediately see the
   new version.

1. **Read** – Consumers resolve the current version with `ModelStore.get_current(agent)` and load models directly from
   the returned directory.

### Manifest Structure (`versions/<version>/manifest.json`)

```json
{
  "version": "v2025-09-12",
  "checksum": "<sha256>",
  "metadata": { "commit": "<git sha>", "author": "<name>" }
}

```bash

Populate `metadata` with any training context that auditors might require.

## Permissions & Environment

- Ensure writers and readers share a Unix group (for example `justnews`).

- Recommended commands (run as root):

```bash mkdir -p /opt/justnews/models chgrp -R justnews /opt/justnews/models
chmod -R g+rwX /opt/justnews/models ```

- Set `MODEL_STORE_ROOT=/opt/justnews/models` in `/etc/justnews/global.env` (systemd guide).

- Set `STRICT_MODEL_STORE=1` to force agents to fail when the model store is unavailable.

## Operational Tasks

- **Backups** – Include the entire `MODEL_STORE_ROOT` in nightly rsync/backup jobs.

- **Restore** – `rsync -av <backup>/model_store/ /opt/justnews/models/` followed by service restart.

- **Retention** – Keep only a small number of historical versions (for example the latest 3) once new versions are validated.

## Helper Scripts & Tooling

Copies of the primary helpers are available in this repository under `models/`
for quick reference:

| Filename | Original Path | Summary |
| --- | --- | --- |
| `model_store.py` | `agents/common/model_store.py` | Core API for staging, finalizing, manifesting, and resolving model versions. |
| `model_loader.py` | `agents/common/model_loader.py` | Safe wrappers around `transformers` and `sentence-transformers` that prefer `MODEL_STORE_ROOT` when set. |
| `native_tensorrt_compiler.py` | `agents/analyst/native_tensorrt_compiler.py` | Publishing pipeline that stages TensorRT artifacts and pushes them into the store. |
| `build_engine.py` | `tools/build_engine/build_engine.py` | CLI orchestrator for fetching HF models, creating ONNX/TRT engines, and finalizing them into the store. |
| `create_toy_model_store.py` | `scripts/create_toy_model_store.py` | Utility for generating a miniature store layout for local testing and demos. |

Additional integration points worth reviewing (not copied here):

- `agents/common/embedding.py` – Loads sentence transformers with ModelStore fallbacks.

- `agents/synthesizer/tools.py` – Prefers the store when retrieving synthesizer artifacts.

- `deploy/systemd/examples/justnews.env.example` – Contains environment variable templates.

## Headline Adapter Conventions

The headline generation path is now a first-class ModelStore-backed adapter under the Chief Editor domain.

- Canonical adapter name: `qwen2_headline_v1`
- Canonical store path: `chief_editor/adapters/qwen2_headline_v1`
- Agent map entries: `AGENT_MODEL_MAP.json` under both `agents.chief_editor` and `vllm_agents.chief_editor`
- Runtime selector (optional override): `TITLE_HYBRID_ADAPTER_NAME` (fallback: `HEADLINE_ADAPTER_NAME`)

Runtime behavior:

- `agents/common/headline_adapter.py` resolves adapter metadata through
  `agents/common/model_loader.py:get_agent_model_metadata(...)`.
- When `STRICT_MODEL_STORE=1`, headline generation fails fast if the configured adapter path is missing.
- In LoRA-enabled vLLM mode, the adapter name is used as the served model selector to conform to the adapter routing pattern.

## Deployment Touchpoints

- **Systemd Native Deployment** (`markdown_docs/agent_documentation/systemd/DEPLOYMENT.md`): documents directory creation and environment configuration.

- **Backup & Recovery** (`markdown_docs/agent_documentation/deployment_procedures_guide.md`): includes a model store restore snippet.

- **GPU Action Plans** (`markdown_docs/development_reports/full_gpu_implementation_action_plan.md`): mandates storing ONNX/TRT engines via the ModelStore helpers.

## Onboarding Checklist

1. Export `MODEL_STORE_ROOT` and ensure permissions are correct.

1. Use `create_toy_model_store.py` to verify the process end-to-end on a staging machine.

1. Integrate training pipelines with `ModelStore.stage_new` / `finalize`.

1. Update agent configuration to enforce `STRICT_MODEL_STORE=1` in production.

1. Add the store to backup, monitoring, and capacity planning inventories.

## Quick Start Snippets

```python
from pathlib import Path

from models.model_store import ModelStore

store = ModelStore(Path("/opt/justnews/models"))
with store.stage_new("scout", "v2025-10-28") as tmp:
    # TODO: write weights/tokenizer files into tmp
    pass
store.finalize("scout", "v2025-10-28")

```

```python
from models.model_loader import load_sentence_transformer

model = load_sentence_transformer(
    "sentence-transformers/all-MiniLM-L6-v2",
    agent="memory",
    cache_folder="/var/lib/justnews/cache",
)

```

```bash

## Build and publish a TensorRT engine to the store

python models/build_engine.py \
  --agent analyst \
  --model-id meta-llama/Meta-Llama-3-8B-Instruct \
  --revision main \
  --precision fp16 \
  --output-version v2025-10-28

```

Use this guide as the single source of truth for future automation or
operational runbooks relating to model storage.
