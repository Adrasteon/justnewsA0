# Canonical Port Mapping — JustNews Infrastructure

**STATUS: SINGLE SOURCE OF TRUTH**
*Last Updated: 2026-02-08*

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
| **8010** | `vllm-service` | `VLLM_SERVICE_PORT` | **VLLM / Qwen 2.5** API. *Note: Dev container uses 8001 for vLLM; production uses 8010.* |
| **8011** | `analytics` | `ANALYTICS_AGENT_PORT` | **Analytics Agent**. Performance tracking and metrics. |
| **8012** | `archive` | `ARCHIVE_AGENT_PORT` | **Archive Service**. Historical record storage. |
| **8013** | `dashboard` | `DASHBOARD_PORT` | **Main Dashboard**. User interface for operations. |
| **8014** | `gpu-orchestrator`| `GPU_ORCHESTRATOR_PORT` | **GPU Orchestrator**. Resource allocation for inference. |
| **8015** | `crawler-worker` | `CRAWLER_AGENT_PORT` | **Crawler Worker**. Heavy lifting web extraction. |
| **8016** | `crawler-control` | `CRAWLER_CONTROL_AGENT_PORT`| **Crawler Control**. Orchestration of crawl jobs. |
| **8017** | `journalist` | `JOURNALIST_PORT` | **Journalist Agent**. Final article composition. |
| **8018** | `auth-service` | `AUTH_SERVICE_PORT` | **Auth Service**. Authentication and Identity. |
| **8019** | `hitl-service` | `HITL_SERVICE_PORT` | **Human-in-the-Loop**. Manual intervention interface. |
| **8020** | `workflow-orchestrator` | `WORKFLOW_ORCHESTRATOR_PORT` | **Workflow Orchestrator**. Job scheduling and pipeline management. |
| **8100** | `publisher-website` | `PUBLISHER_PORT` | **Django Publisher**. Public-facing news website (development server). |

## 2. Infrastructure & Data (Standard Ports)

| Port | Service Identifier | Configuration Key | Description |
| :--- | :--- | :--- | :--- |
| **3000** | `grafana` | `GRAFANA_URL` | **Grafana**. Observability visualization. |
| **3100** | `loki` | `LOKI_PORT` | **Loki**. Log aggregation (telemetry stack). |
| **3306** | `mariadb` | `DB_PORT` | **MariaDB/MySQL**. Relational database. |
| **3307** | `chromadb` | `CHROMA_PORT` | **ChromaDB**. Vector database (Alternate port to avoid 8000). |
| **4317** | `otel-collector` | `OTEL_GRPC_PORT` | **OpenTelemetry Collector**. Metrics/traces ingest (gRPC). |
| **6379** | `redis` | `REDIS_PORT` | **Redis**. Caching and Pub/Sub. |
| **9090** | `prometheus` | `PROMETHEUS_PORT` | **Prometheus**. Metrics aggregation. |
| **9093** | `alertmanager` | `ALERTMANAGER_PORT` | **AlertManager**. Alert routing and management. |
| **9100** | `node-exporter` | `NODE_EXPORTER_PORT` | **Node Exporter**. Host metrics (internal). |
| **9411** | `tempo` | `TEMPO_PORT` | **Tempo (Jaeger)**. Distributed tracing visualization. |

## 3. Development Environment

| Port | Service Identifier | Configuration Key | Description |
| :--- | :--- | :--- | :--- |
| **8100** | `publisher-website-dev` | `PUBLISHER_PORT` | **Django Publisher Dev**. Local development server for the public-facing website. |
| **8200** | `vault` | `VAULT_ADDR` | **HashiCorp Vault**. Secrets management (default local address). |

## 4. Legacy & Deprecated

| Port | Service Identifier | Status | Notes |
| :--- | :--- | :--- | :--- |
| **8040** | `hitl-legacy` | **Moved** | Moved to 8019 for block consistency. |
| **8090** | `encoder-service` | **Retired** | Legacy embedding service. |
