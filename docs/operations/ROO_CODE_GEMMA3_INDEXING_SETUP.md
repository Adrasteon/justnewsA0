# Roo Code Gemma 3 + Indexing Setup Guide

This guide documents the full setup used to run Roo Code with LM Studio for chat and embeddings, plus Qdrant for workspace indexing, from inside a dev-container.

## 1. Architecture and Networking

In this repository, VS Code runs against a dev-container. That means:

- `localhost` inside the container points to the container itself.
- Host services must be reached through `host.docker.internal`.

Target topology:

- LM Studio (host): `http://host.docker.internal:1234/v1`
- Ollama Desktop (host, optional): `http://host.docker.internal:11434`
- Qdrant (container published to host): `http://host.docker.internal:6333`

## 2. Prerequisites

Required:

1. LM Studio running on host with OpenAI-compatible server enabled on port 1234.
2. Chat model loaded in LM Studio: `google/gemma-3-12b`.
3. Embedding model loaded in LM Studio: `text-embedding-nomic-embed-text-v1.5`.
4. Docker available in dev-container for Qdrant lifecycle operations.

Optional:

1. Ollama Desktop on host for alternate profile usage.

## 3. Start Qdrant Backend

Use the helper script:

```bash
bash scripts/roo_qdrant.sh start
```

Check status:

```bash
bash scripts/roo_qdrant.sh status
```

## 4. Roo Workspace Settings

Workspace configuration lives in `.roo-code-settings.json`.

### Provider profile (chat)

Roo should use the OpenAI-compatible LM Studio profile:

```json
"providerProfiles": {
  "currentApiConfigName": "desktop-openai-lmstudio-gemma",
  "apiConfigs": {
    "desktop-openai-lmstudio-gemma": {
      "apiProvider": "openai",
      "openAiBaseUrl": "http://host.docker.internal:1234/v1",
      "openAiApiKey": "lm-studio",
      "openAiModelId": "google/gemma-3-12b"
    }
  }
}
```

### Codebase indexing configuration

Use openai-compatible embeddings and host-bridge Qdrant URL:

```json
"codebaseIndexConfig": {
  "codebaseIndexEnabled": true,
  "codebaseIndexQdrantUrl": "http://host.docker.internal:6333",
  "codebaseIndexEmbedderProvider": "openai-compatible",
  "codebaseIndexEmbedderBaseUrl": "http://host.docker.internal:1234/v1",
  "codebaseIndexOpenAiCompatibleBaseUrl": "http://host.docker.internal:1234/v1",
  "codebaseIndexEmbedderModelId": "text-embedding-nomic-embed-text-v1.5",
  "codebaseIndexEmbedderModelDimension": 768
}
```

Note:

- Keep both base URL fields set (`codebaseIndexEmbedderBaseUrl` and `codebaseIndexOpenAiCompatibleBaseUrl`) to avoid provider fallback edge cases.

## 5. Auto-Import for Startup Consistency

Machine-level VS Code setting should include:

```json
"roo-cline.autoImportSettingsPath": "/app/.roo-code-settings.json"
```

This helps Roo import the workspace settings at startup.

## 6. Verify End-to-End Connectivity

Run the preflight checker:

```bash
bash scripts/verify_roo_index_setup.sh
```

It validates:

1. LM Studio `/models` reachability.
2. Presence of chat and embedding model IDs.
3. LM Studio `/embeddings` request success.
4. Qdrant `/collections` health (`status: ok`).

## 7. Trigger Indexing

After settings are imported and preflight passes:

1. Open Roo advanced settings and verify the index values match this guide.
2. Save settings.
3. Trigger workspace indexing from Roo UI.

If indexing was previously stuck, a reload of the VS Code window may help the extension pick up fresh state.

## 8. Troubleshooting

### Symptom: Failed during initial scan: fetch failed

Most common causes:

1. Qdrant not running on `host.docker.internal:6333`.
2. LM Studio embeddings server not available on `host.docker.internal:1234/v1`.
3. Settings still pointing to `localhost` instead of host bridge address.

What to do:

1. Run `bash scripts/roo_qdrant.sh status`.
2. Run `bash scripts/verify_roo_index_setup.sh`.
3. Confirm `.roo-code-settings.json` matches Section 4.

### Symptom: Failed to process batch after 3 attempts: Bad Request

Most common cause:

1. Qdrant collection was created earlier with a different vector size than the current embedding model.

Example mismatch:

1. Collection vector size is `1536`.
2. Current embedding model returns `768` dimensions.

What to do:

1. Verify embedding dimension from LM Studio `/v1/embeddings`.
2. Inspect Qdrant collection schema (`/collections/<name>`) for vector size.
3. Delete the stale Roo collection.
4. Clear Roo index cache files (`roo-index-cache-*.json`).
5. Rerun indexing so Roo recreates the collection with the correct size.

### Symptom: Roo still shows old Ollama variant

Most common causes:

1. Stale extension state loaded before settings import.
2. UI still reflecting previous profile until settings save/reload.

What to do:

1. Verify `providerProfiles.currentApiConfigName` is set to `desktop-openai-lmstudio-gemma`.
2. Ensure auto-import path is configured.
3. Save advanced settings again and reload the VS Code window.

### Symptom: Indexing failed: memory access out of bounds

This is a parser/runtime crash inside the indexer on specific files.

Workaround:

1. Add a workspace `.rooignore` file if missing.
2. Exclude the crashing file path(s), for example:

```text
AGENT_MODEL_RECOMMENDED.json
AGENT_MODEL_MAP.json
```

3. Reload VS Code window and rerun indexing.

## 9. Operational Commands

Qdrant lifecycle:

```bash
bash scripts/roo_qdrant.sh start
bash scripts/roo_qdrant.sh status
bash scripts/roo_qdrant.sh logs
bash scripts/roo_qdrant.sh stop
```

Preflight with custom model IDs:

```bash
CHAT_MODEL_ID=google/gemma-3-12b \
EMBED_MODEL_ID=text-embedding-nomic-embed-text-v1.5 \
bash scripts/verify_roo_index_setup.sh
```

## 10. Known Good Reference Values

- Chat base URL: `http://host.docker.internal:1234/v1`
- Chat model ID: `google/gemma-3-12b`
- Embed provider: `openai-compatible`
- Embed model ID: `text-embedding-nomic-embed-text-v1.5`
- Embed dimension: `768`
- Qdrant URL: `http://host.docker.internal:6333`

When these values are present and preflight passes, Roo indexing should run successfully in this dev-container setup.