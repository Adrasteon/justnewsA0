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
