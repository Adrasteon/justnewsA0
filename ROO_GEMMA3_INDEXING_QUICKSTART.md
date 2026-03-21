# Roo Gemma 3 Indexing Quickstart

This is the fastest path to get Roo Code chat and workspace indexing working with LM Studio + Qdrant inside this dev-container.

For full details, see [docs/operations/ROO_CODE_GEMMA3_INDEXING_SETUP.md](docs/operations/ROO_CODE_GEMMA3_INDEXING_SETUP.md).

## 1. Start Dependencies

Start Qdrant:

```bash
bash scripts/roo_qdrant.sh start
```

Ensure LM Studio server is running on host:

- Base URL: `http://host.docker.internal:1234/v1`
- Chat model loaded: `google/gemma-3-12b`
- Embedding model loaded: `text-embedding-nomic-embed-text-v1.5`

## 2. Apply Roo Settings

Use [/.roo-code-settings.json](.roo-code-settings.json) as the source of truth.

Critical values:

- `providerProfiles.currentApiConfigName`: `desktop-openai-lmstudio-gemma`
- `openAiBaseUrl`: `http://host.docker.internal:1234/v1`
- `openAiModelId`: `google/gemma-3-12b`
- `codebaseIndexQdrantUrl`: `http://host.docker.internal:6333`
- `codebaseIndexEmbedderProvider`: `openai-compatible`
- `codebaseIndexEmbedderModelId`: `text-embedding-nomic-embed-text-v1.5`

## 3. Verify End-to-End

Run preflight:

```bash
bash scripts/verify_roo_index_setup.sh
```

Expected result:

- LM Studio models reachable
- Chat model found
- Embedding model found
- Embeddings request succeeds
- Qdrant health check returns ok

## 4. Trigger Indexing in Roo

1. Open Roo advanced settings and confirm values match [/.roo-code-settings.json](.roo-code-settings.json).
2. Save settings.
3. Start workspace indexing.

## 5. If It Fails

Run:

```bash
bash scripts/roo_qdrant.sh status
bash scripts/verify_roo_index_setup.sh
```

Then check these common causes:

1. A `localhost` URL is still present in Roo settings (should use `host.docker.internal`).
2. LM Studio embedding model is not loaded.
3. Qdrant container is not running.