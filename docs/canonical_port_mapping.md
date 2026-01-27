# Canonical Port Mapping — JustNews Infrastructure

**STATUS: SINGLE SOURCE OF TRUTH**
*Last Updated: 2026-01-27*

This document serves as the absolute reference for port allocations within the JustNews ecosystem. All service configurations, container definitions, and environment variables must adhere to this registry to prevent collision and ensure service discovery.

## 1. Core Services & Agents (8000 - 8019)

| Port | Service Identifier | Configuration Key | Description |
| :--- | :--- | :--- | :--- |
| **8000** | `mcp-bus` | `MCP_BUS_PORT` | **MCP Bus Service**. Central message broker and discovery. |
| **8001** | `chief-editor` | `CHIEF_EDITOR_AGENT_PORT` | **Chief Editor**. Orchestrates the editorial workflow. |
| **8002** | `scout` | `SCOUT_AGENT_PORT` | **Scout Agent**. Discovery and initial content filtering. |
| **8003** | `fact-checker` | `FACT_CHECKER_AGENT_PORT` | **Fact Checker**. Verifies claims against knowledge base. |
| **8004** | `analyst` | `ANALYST_AGENT_PORT` | **Analyst Agent**. Deep dive content analysis. |
| **8005** | `synthesizer` | `SYNTHESIZER_AGENT_PORT` | **Synthesizer**. Content generation and drafting. |
| **8006** | `critic` | `CRITIC_AGENT_PORT` | **Critic Agent**. Quality assurance and review. |
| **8007** | `memory` | `MEMORY_AGENT_PORT` | **Memory Service**. Long-term context and recall. |
| **8008** | `reasoning` | `REASONING_AGENT_PORT` | **Reasoning Agent**. Complex query processing. |
| **8009** | `newsreader` | `NEWSREADER_PORT` | **Newsreader**. Content ingestion and parsing. |
| **8010** | `vllm-service` | `MISTRAL_API_PORT` | **VLLM / Mistral**. Local LLM inference server. |
| **8011** | `analytics` | `ANALYTICS_AGENT_PORT` | **Analytics Agent**. Performance tracking and metrics. |
| **8012** | `archive` | `ARCHIVE_AGENT_PORT` | **Archive Service**. Historical record storage. |
| **8013** | `dashboard` | `DASHBOARD_PORT` | **Main Dashboard**. User interface for operations. |
| **8014** | `gpu-orchestrator`| `GPU_ORCHESTRATOR_PORT` | **GPU Orchestrator**. Resource allocation for inference. |
| **8015** | `crawler-worker` | `CRAWLER_AGENT_PORT` | **Crawler Worker**. Heavy lifting web extraction. |
| **8016** | `crawler-control` | `CRAWLER_CONTROL_AGENT_PORT`| **Crawler Control**. Orchestration of crawl jobs. |
| **8017** | `journalist` | `JOURNALIST_PORT` | **Journalist Agent**. Final article composition. |
| **8018** | `auth-service` | `AUTH_SERVICE_PORT` | **Auth Service**. Authentication and Identity. |
| **8019** | `hitl-service` | `HITL_SERVICE_PORT` | **Human-in-the-Loop**. Manual intervention interface. |

## 2. Infrastructure & Data (Standard Ports)

| Port | Service Identifier | Configuration Key | Description |
| :--- | :--- | :--- | :--- |
| **3000** | `grafana` | `GRAFANA_URL` | **Grafana**. Observability visualization. |
| **3306** | `mariadb` | `DB_PORT` | **MariaDB/MySQL**. Relational database. |
| **3307** | `chromadb` | `CHROMA_PORT` | **ChromaDB**. Vector database (Alternate port to avoid 8000). |
| **6379** | `redis` | `REDIS_PORT` | **Redis**. Caching and Pub/Sub. |
| **9090** | `prometheus` | `PROMETHEUS_PORT` | **Prometheus**. Metrics aggregation (Planned). |

## 3. Legacy & Deprecated

| Port | Service Identifier | Status | Notes |
| :--- | :--- | :--- | :--- |
| **8040** | `hitl-legacy` | **Moved** | Moved to 8019 for block consistency. |
| **8090** | `encoder-service` | **Retired** | Legacy embedding service. |
