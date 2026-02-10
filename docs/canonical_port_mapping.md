# Canonical Port Mapping — JustNews Infrastructure

**STATUS: SINGLE SOURCE OF TRUTH**
*Last Updated: 2026-02-10*
*Latest Update: Fixed crawler port (8022), newsreader registration (8009), workflow orchestrator (8023)*

This document serves as the absolute reference for port allocations within the JustNews ecosystem. All service configurations, container definitions, and environment variables must adhere to this registry to prevent collision and ensure service discovery.

## 1. Core Services & Agents (8000 - 8023)

| Port | Service Identifier | Configuration Key | Description |
| :--- | :--- | :--- | :--- |
| **8000** | `mcp-bus` | `MCP_BUS_PORT` | **MCP Bus Service**. Central message broker and discovery. Routes all inter-agent calls. |
| **8001** | `chief-editor` | `CHIEF_EDITOR_AGENT_PORT` | **Chief Editor**. Orchestrates the editorial workflow. |
| **8002** | `scout` | `SCOUT_AGENT_PORT` | (DEPRECATED) Scout Agent. Legacy discovery service - DO NOT USE. |
| **8003** | `fact-checker` | `FACT_CHECKER_AGENT_PORT` | **Fact Checker**. Verifies claims against knowledge base. |
| **8004** | `analyst` | `ANALYST_AGENT_PORT` | **Analyst Agent**. Deep dive content analysis. |
| **8005** | `synthesizer` | `SYNTHESIZER_AGENT_PORT` | **Synthesizer**. Content generation and drafting. |
| **8006** | `critic` | `CRITIC_AGENT_PORT` | **Critic Agent**. Quality assurance and review. |
| **8007** | `memory` | `MEMORY_AGENT_PORT` | **Memory Service**. Long-term context and recall. Ingests analyzed articles. |
| **8008** | `reasoning` | `REASONING_AGENT_PORT` | **Reasoning Agent**. Complex query processing. |
| **8009** | `newsreader` | `NEWSREADER_PORT` | **Newsreader**. Content ingestion and parsing from URLs. |
| **8010** | `vllm-service` | `VLLM_SERVICE_PORT` | **VLLM / Qwen 2.5** API. *Note: Dev container uses 8001 for vLLM; production uses 8010.* |
| **8012** | `analytics` | `ANALYTICS_AGENT_PORT` | **Analytics Agent**. Performance tracking and metrics. |
| **8013** | `dashboard` | `DASHBOARD_PORT` | **Main Dashboard**. User interface for operations. |
| **8014** | `gpu-orchestrator`| `GPU_ORCHESTRATOR_PORT` | **GPU Orchestrator**. Resource allocation and inference management. |
| **8016** | `crawler-control` | `CRAWLER_CONTROL_AGENT_PORT`| **Crawler Control**. Orchestration of crawl jobs. Web UI for monitoring. |
| **8020** | `archive` | `ARCHIVE_AGENT_PORT` | **Archive Service**. Historical record storage and retrieval. |
| **8022** | `crawler` | `CRAWLER_AGENT_PORT` | **Crawler Agent**. Web scraping and article extraction engine. |
| **8023** | `workflow-orchestrator` | `WORKFLOW_ORCHESTRATOR_PORT` | **Workflow Orchestrator**. Job scheduling, pipeline management, and policy enforcement. Routes synthesis and publishing. |
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
