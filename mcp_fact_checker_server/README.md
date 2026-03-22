# MCP Fact Checker Server

A standalone, enterprise-grade generic fact-checking microservice provided as an **MCP (Model Context Protocol)** server.

## Features
- **Multi-Modal**: Supports text, image, and video evidence.
- **Model-Agnostic**: Configurable backends (Local CPU models + Remote GPU inference).
- **Scalable**: Async job processing and stateless design.
- **Secure**: API Key authentication.
- **Dependency-Complete**: Includes all system and local model dependencies.

## Quick Start

### 1. Build & Run
```bash
docker-compose up --build
```

### 2. Verify
```bash
curl -X POST http://localhost:8003/fact_check \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: dev_key_123" \
  -d '{"fact": "The sky is blue"}'
```

## Configuration
| Variable | Description | Default |
|----------|-------------|---------|
| `FACT_CHECKER_API_KEY` | Auth key for requests | None (Public) |
| `VLLM_BASE_URL` | URL for heavy inference | None |
| `MODEL_STORE_ROOT` | Root directory for shared model store lookup | unset |
| `MODEL_STORE_EMBEDDING_AGENT` | Agent namespace used for embedding lookup under model store | `fact_checker` |
| `MODEL_STORE_EMBEDDING_PATH` | Optional explicit relative path under model store to embedding payload | unset |
| `EMBEDDING_MODEL_PATH` | Optional absolute path override for embedding model payload | unset |
| `STRICT_MODEL_STORE` | If true, fail embedding init when model store resolution fails | `0` |

### Model Loading Behavior

- LLM verification requests route through vLLM using `VLLM_FACT_CHECKER_MODEL` (adapter-capable path).
- Embedding model loading now prefers central model-store resolution when `MODEL_STORE_ROOT` is configured.
- If no model-store path is resolved, service falls back to the configured embedding model ID (HF behavior) unless `STRICT_MODEL_STORE` is enabled.
- Docker build no longer pre-downloads Hugging Face models; model retrieval is runtime-driven via model-store or fallback.

### Pre-Start Model Store Bootstrap (Required When `STRICT_MODEL_STORE=1`)

Publish the embedding payload to model store before starting the service in strict mode:

```bash
mkdir -p model_store
MODEL_STORE_ROOT=$PWD/model_store \
  /app/.venv/bin/python scripts/publish_hf_to_model_store.py \
  --agent fact_checker \
  --model BAAI/bge-large-en-v1.5 \
  --version v_fact_checker_embedding_bge_large_en_v1_5
```

Optional: pin the exact relative model path using `MODEL_STORE_EMBEDDING_PATH`
after publish if you want deterministic path selection across versions.

### Model Store Root Scope Note

- Current devcontainer setup uses a workspace-scoped root at `/app/model_store`.
- Canonical host deployments may use a host-global root such as `${SERVICE_DIR}/model_store`.
- Both are the same model-store mechanism; only the root path scope differs.

Recommendations for later strict consistency:

- Align all agent services on one root-path convention per environment tier.
- Keep `STRICT_MODEL_STORE=1` enabled only after required payloads are published for every service.
- Add startup/preflight checks in deployment pipelines to verify required model-store artifacts before rollout.
