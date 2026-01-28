# Qwen 2.5 14B vLLM Integration Guide

> **Standardization Node (2026-01-28):** JustNews has standardized on **Qwen 2.5 14B AWQ** as the primary intelligence backend. All legacy local model paths (Mistral/Llama) have been deprecated and removed.

## Overview

This guide covers the integration of the Qwen 2.5 14B model served via vLLM. This model offers superior reasoning capabilities compared to previous 7B models while remaining efficient enough for single RTX 3090/4090 deployment (24GB VRAM) using AWQ quantization.

- **Base model**: `Qwen/Qwen2.5-14B-Instruct-AWQ`
- **Serving Engine**: vLLM
- **Port**: 8010 (Canonical)

## Quick Start

### 1. Install vLLM

```bash
conda activate justnews-py312
pip install vllm
```

### 2. Launch vLLM Server

Use the systemd service (recommended) or manual launch:

```bash
# Manual launch (for testing)
vllm serve Qwen/Qwen2.5-14B-Instruct-AWQ \
  --port 8010 \
  --dtype auto \
  --quantization awq \
  --gpu-memory-utilization 0.85 \
  --max-model-len 32768 \
  --api-key unused
```

Key Settings:
- **Quantization**: AWQ (4-bit) for VRAM efficiency.
- **Max Context**: 32k tokens (supports long-form document analysis).
- **Port**: 8010 (Shared centralized endpoint).

### 3. Service Configuration

Ensure your `global.env` points to this service:

```bash
# /etc/justnews/global.env

VLLM_BASE_URL=http://127.0.0.1:8010/v1
VLLM_MODEL=Qwen/Qwen2.5-14B-Instruct-AWQ
VLLM_API_KEY=unused
```

### 4. Agent Integration

All agents (`journalist`, `fact_checker`, `synthesizer`, etc.) are pre-configured to use the `agents.common.openai_adapter.OpenAIAdapter` class which automatically reads `VLLM_BASE_URL` and `VLLM_MODEL` from your environment.

## Troubleshooting

### "Model not found" or Download loops
Ensure you have access to Hugging Face (no token required for Qwen usually, but check network).
CACHE_DIR is typically `~/.cache/huggingface`.

### OOM Errors
If you run out of memory, try reducing `--gpu-memory-utilization` to `0.7` or `0.6` to leave room for other processes (like Chrome Crawler).

```bash
--gpu-memory-utilization 0.6
```

### Fallback
There is no longer a local CPU fallback for inference. The system requires a running vLLM compatible endpoint.
