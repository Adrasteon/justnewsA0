# JustNews Operations Guide

## Quick Links

**🔴 Live Server Go-Live (SEO/Crawler Priority):**

- [Live SEO Launch Checklist](./LIVE_SEO_LAUNCH_CHECKLIST.md) — Required actions before and during production launch to maximize crawl frequency and ranking readiness

**📈 Investor Proposal (Multi-Source Refactor):**

- [Investor One-Pager: Multi-Source Integrity Refactor (2026-02-22)](./INVESTOR_ONE_PAGER_MULTI_SOURCE_REFACTOR_2026-02-22.md)

- [Investor Technical Appendix: Multi-Source Integrity Refactor (2026-02-22)](./INVESTOR_TECH_APPENDIX_MULTI_SOURCE_REFACTOR_2026-02-22.md)

- [Multi-Source Refactor Project Plan (2026-02-22)](./MULTI_SOURCE_REFACTOR_PROJECT_PLAN_2026-02-22.md)

- [Multi-Source Refactor Action Checklist (2026-02-22)](./MULTI_SOURCE_REFACTOR_ACTION_CHECKLIST_2026-02-22.md)

- [Multi-Source Refactor Metrics Note (2026-02-22)](./MULTI_SOURCE_REFACTOR_METRICS_NOTE_2026-02-22.md)

- [Multi-Source Refactor Metrics Snapshot (Local, 2026-02-22)](./MULTI_SOURCE_REFACTOR_METRICS_SNAPSHOT_2026-02-22_LOCAL.md)

- [Multi-Source Refactor Observability Dashboard (Grafana JSON)](../grafana/multi-source-refactor-observability-dashboard.json)

- `monitoring/alerts/multi_source_refactor_alerts.yml` — Alert rules for verified-share degradation and promotion-failure spikes

- [Multi-Source Refactor Runtime Tuning Runbook (2026-02-22)](./MULTI_SOURCE_REFACTOR_RUNTIME_TUNING_RUNBOOK_2026-02-22.md)

- [Autonomic Dynamic Orchestrator Implementation Plan (2026-03-18)](./AUTONOMIC_DYNAMIC_ORCHESTRATOR_IMPLEMENTATION_PLAN_2026-03-18.md)

- [Two-Lane Traceability Implementation Plan (2026-03-20)](./TWO_LANE_TRACEABILITY_IMPLEMENTATION_PLAN_2026-03-20.md) — File-by-file implementation backlog for BBC-seed Lane 1, DDG expansion, structured attribution, and hybrid balance enforcement

- [Hybrid Whitelist + Discovery Implementation Tickets (2026-03-21)](./HYBRID_WHITELIST_DISCOVERY_IMPLEMENTATION_TICKETS_2026-03-21.md) — Implementation-ready epics and tickets for controlled global discovery with anti-flood guardrails and constrained self-learning

- [Hybrid Whitelist + Discovery Execution Checklist (2026-03-21)](./HYBRID_WHITELIST_DISCOVERY_EXECUTION_CHECKLIST_2026-03-21.md) — Phase gates, stop conditions, rollback checks, and sign-off tracking template

- [Crawl Ingestion Triage Decisions (2026-03-21)](./CRAWL_INGESTION_TRIAGE_DECISIONS_2026-03-21.md) — Prompt experiment findings, decisions, and the implemented deterministic+AI triage approach

- [Crawl Ingestion Triage System Guide (2026-03-21)](./CRAWL_INGESTION_TRIAGE_SYSTEM_GUIDE_2026-03-21.md) — Full technical and operational reference for triage functionality, runtime controls, metadata contract, user interaction, and troubleshooting

- [Multi-Source Refactor Lane 2 Crawl Fallback Runbook (2026-03-17)](./MULTI_SOURCE_REFACTOR_LANE2_FALLBACK_RUNBOOK_2026-03-17.md)

- [Multi-Source Refactor M2 Sign-Off Evidence Index (2026-02-22)](./MULTI_SOURCE_REFACTOR_M2_SIGNOFF_EVIDENCE_INDEX_2026-02-22.md)

- [Multi-Source Refactor M2 Sign-Off Summary (Draft, 2026-02-22)](./MULTI_SOURCE_REFACTOR_M2_SIGNOFF_SUMMARY_2026-02-22_DRAFT.md)

- [Multi-Source Refactor Closeout Summary (2026-02-22)](./MULTI_SOURCE_REFACTOR_CLOSEOUT_SUMMARY_2026-02-22.md)

- [Multi-Source Refactor Dev/Staging Parity Runsheet (2026-02-22)](./MULTI_SOURCE_REFACTOR_DEV_STAGING_PARITY_RUNSHEET_2026-02-22.md)

- [Multi-Source Refactor Rollback Drill Artifact Template (2026-02-22)](./MULTI_SOURCE_REFACTOR_ROLLBACK_DRILL_ARTIFACT_TEMPLATE_2026-02-22.md)

- [Multi-Source Refactor Rollback Drill Artifact (Local, 2026-02-22)](./MULTI_SOURCE_REFACTOR_ROLLBACK_DRILL_ARTIFACT_2026-02-22_LOCAL.md)

- [Multi-Source Refactor Provenance Sample Evidence Template (2026-02-22)](./MULTI_SOURCE_REFACTOR_PROVENANCE_SAMPLE_EVIDENCE_TEMPLATE_2026-02-22.md)

- [Multi-Source Refactor Provenance Sample Evidence (Local, 2026-02-22)](./MULTI_SOURCE_REFACTOR_PROVENANCE_SAMPLE_EVIDENCE_2026-02-22_LOCAL.md)

- [AI Assistant Refactor Guardrails (2026-02-22)](./AI_ASSISTANT_REFACTOR_GUARDRAILS_2026-02-22.md)

- [AI Assistant Task Prompt Template (2026-02-22)](./AI_ASSISTANT_TASK_PROMPT_TEMPLATE_2026-02-22.md)

**Getting Started**:

- [Setup Guide](./SETUP_GUIDE.md) — Complete end-to-end installation (Python, Vault, MariaDB, ChromaDB, systemd)

- [Roo Code Gemma 3 + Indexing Setup Guide](./ROO_CODE_GEMMA3_INDEXING_SETUP.md) — Full dev-container configuration for LM Studio, Qdrant, and Roo workspace indexing

- [Environment Configuration](./ENVIRONMENT_CONFIG.md) — Global configuration, environment variables, secrets management

- [Troubleshooting](./TROUBLESHOOTING.md) — Diagnostics and recovery procedures

- [Living Story Runbook](./LIVING_STORY_RUNBOOK.md) — Canonical story philosophy, meaningful-change thresholds, and day-2 operations

- `scripts/ops/living_story_dashboard_report.py` — Generates JSON/Markdown operator telemetry reports for living-story decisions and latency trends

- [Fact Checker Troubleshooting](./FACT_CHECKER_TROUBLESHOOTING.md) — Devcontainer/backend routing, auth, and circuit-breaker recovery

- [MCP Bus Health & Diagnostics](./MCP_BUS_HEALTH.md) — Details on `/health`and`/ready`, testing, and developer guidance

- [Crawler Maturity Checklist](./CRAWLER_MATURITY_CHECKLIST.md) — Phased roadmap and acceptance criteria to move toward enterprise-grade crawling

- [Crawler Ingest Resiliency Runbook](./CRAWLER_INGEST_RESILIENCY.md) — Disk-backed deferred ingest spool, replay behavior, and outage recovery

- [Monitoring Scripts Reference](./MONITORING_SCRIPTS_REFERENCE.md) — Script-level monitoring checks, technical signals, and recommended run sequence

- [Autonomic Dynamic Orchestrator Implementation Plan (2026-03-18)](./AUTONOMIC_DYNAMIC_ORCHESTRATOR_IMPLEMENTATION_PLAN_2026-03-18.md) — Concrete backlog and canary rollout defaults for real-time dynamic orchestration

- [Two-Lane Traceability Implementation Plan (2026-03-20)](./TWO_LANE_TRACEABILITY_IMPLEMENTATION_PLAN_2026-03-20.md) — Planned rollout for BBC-seed comparative retrieval, attributed speech traceability, and hybrid balance governance

- [Hybrid Whitelist + Discovery Implementation Tickets (2026-03-21)](./HYBRID_WHITELIST_DISCOVERY_IMPLEMENTATION_TICKETS_2026-03-21.md) — Delivery backlog for lifecycle states, discovery sandboxing, score-based promotion, and learning-loop guardrails

- [Hybrid Whitelist + Discovery Execution Checklist (2026-03-21)](./HYBRID_WHITELIST_DISCOVERY_EXECUTION_CHECKLIST_2026-03-21.md) — Operator checklist for rollout readiness, canary gates, and emergency rollback

- [Lane 2 Crawl Fallback Runbook](./MULTI_SOURCE_REFACTOR_LANE2_FALLBACK_RUNBOOK_2026-03-17.md) — Enables secondary-lane crawl attempt when primary lane yields zero new ingest

- [Dev Data Reset (Preserve Sources)](../../scripts/maintenance/reset_dev_data_preserve_sources.py) — Clears crawl/article/embedding/synthesis runtime data and always resets `sources.last_crawl_at` to `NULL` while preserving `sources` rows

**Infrastructure**:

- [Vault Setup & Administration](./VAULT_SETUP.md) — Secrets management, AppRole, key rotation

- [Systemd Operations](../infrastructure/systemd/README.md) — Service management and deployment

## Deployment Procedures

This guide covers production deployment, scaling, and operational procedures for JustNews.

## Stage B Validation Workflow

- Follow the playbook in `docs/operations/stage_b_validation.md` when preparing Stage B rollout work.

- Instantiate ops tickets with the checklist from `docs/operations/stage_b_ticket_template.md`.

- Attach artifacts to the running ticket and log summaries in `docs/operations/stage_b_validation_evidence_log.md`.

- Use `bash scripts/ops/apply_stage_b_migration.sh`to run migration 003 and optionally append a timestamped entry to the
  evidence log; the script drops raw output in`logs/operations/migrations/` for archival.

## Environment Overview

### Development Environment

- **Purpose**: Feature development and testing

- **Components**: systemd with hot reload support via development scripts

- **Persistence**: Local volumes and SQLite

- **Monitoring**: Basic logging and health checks

### Staging Environment

- **Purpose**: Integration testing and validation

- **Components**: systemd services with multiple instances or dedicated staging host

- **Persistence**: MariaDB with test data

- **Monitoring**: Prometheus/Grafana dashboards

### Production Environment

- **Purpose**: Live system serving real traffic

- **Components**: systemd-managed services with cluster-level HA managed outside this repo

- **Persistence**: MariaDB cluster with backups

- **Monitoring**: Full observability stack

## Prerequisites

### System Requirements

```bash

## Minimum hardware requirements

- CPU: 8 cores

- RAM: 32GB

- GPU: NVIDIA RTX 3090 or equivalent (24GB VRAM)

- Storage: 500GB SSD

- Network: 1Gbps connection

## Software requirements

- NVIDIA GPU Operator (if using GPU features)

- MariaDB 10.11+

- ChromaDB 0.4.18+

- Redis 7+

- systemd (required for production runs)

## NOTE: Kubernetes and Docker are deprecated and archived; see `infrastructure/archives/` for historical artifacts.

```yaml

### Network Configuration

```yaml

## Required ports (internal)

8000: MCP Bus
8001-8008: Agent services
8013: Dashboard
8014: Public API
8020: GraphQL API
8021: Archive API

## External access

80/443: Web interface and APIs

```

#### GPU / bitsandbytes (important ops note)

- The repository currently ships a pre-built bitsandbytes wheel targeting CUDA 12.2 (it contains
  libbitsandbytes_cuda122.so). Until the host drivers, CUDA runtime and the canonical environment are upgraded to a
  newer, compatible CUDA ABI, you must pin the runtime so the correct native library is selected.

- Operational requirement: set BNB_CUDA_VERSION=122 in your service environment (for example `/etc/justnews/*.env` or
  systemd unit Environment entries) to force loading the in-repo CUDA‑12.2 bitsandbytes library. If this is not set,
  bitsandbytes may attempt to load a native library matching the running CUDA runtime and fail if a matching binary is
  not available.

- Artifacts & guidance: see the prebuilt wheel and notes under
  `.build/bitsandbytes/dist/`and`docs/bitsandbytes_cuda122_wheel.md`. When you upgrade the system/CUDA/PyTorch stacks,
  either rebuild a matching wheel or install a bitsandbytes package built for the new CUDA target.

## Deployment Methods

### Method 1: systemd (Preferred / Production)

#### Prerequisites

```bash

## No Kubernetes required. systemd is the default orchestration for JustNews.

## Ensure systemd and MariaDB are available on the host.

```bash

#### Deploy Infrastructure

```bash

## Install MariaDB via your OS package manager or use the supplied scripts

sudo apt-get update && sudo apt-get install -y mariadb-server
sudo systemctl enable --now mariadb

## Optionally install ChromaDB following upstream packaging or binary install

```

#### Deploy JustNews

```bash

## Clone repository

git clone <repository>
cd JustNews

## Install systemd units

sudo cp infrastructure/systemd/units/*.service /etc/systemd/system/
sudo systemctl daemon-reload

## Start and enable core services (MariaDB should be configured already)

sudo systemctl enable --now justnews-mcp-bus
sudo systemctl enable --now justnews-redis

## Enable/start agent services

for service in justnews-scout justnews-analyst justnews-synthesizer; do
  sudo systemctl enable --now $service || true
done

```

#### Configuration

```bash

## Create local environment files and place them under `deploy/refactor/config/environments/`.

cp deploy/refactor/config/environments/development.env deploy/refactor/config/environments/production.env

## Edit production.env with proper MARIADB/CHROMADB/REDIS values

```

### Method 2: Docker Compose (DEPRECATED & ARCHIVED)

> ⚠️ Docker Compose has been deprecated and archived in this repository. It is not supported for active development or
deployments. Historical compose files are available under `infrastructure/archives/docker/` for reference only; prefer
systemd artifacts for local and production deployments.

#### Quick Start

```bash

## Clone repository

## Scale via systemd

## Create additional unit instances or use templated units to add replicas. See the systemd scaling section above.

cd JustNews

## Start all services (DEPRECATED)

## (DEPRECATED) docker-compose -f docker-compose.yml up -d

## Check status

## (DEPRECATED) docker-compose ps

## (DEPRECATED) docker-compose logs -f

```bash

#### Production-Ready Compose

```bash

## Use production compose file (DEPRECATED)

## (DEPRECATED) docker-compose -f docker-compose.prod.yml up -d

sudo systemctl status --type=service --state=running
sudo journalctl -u <unit-name> -f
## (DEPRECATED) docker-compose up -d --scale scout=3 --scale analyst=2

```

### Method 3: systemd (Legacy)

#### Systemd Deployment

```bash

## Install systemd services

sudo cp infrastructure/systemd/units/*.service /etc/systemd/system/
sudo systemctl daemon-reload

## Start services in order (MariaDB recommended; Postgres services are deprecated)

sudo systemctl start justnews-mcp-bus
sudo systemctl start justnews-mariadb || sudo systemctl start justnews-postgres
sudo systemctl start justnews-redis

## Start agents

for service in justnews-scout justnews-analyst justnews-synthesizer; do
  sudo systemctl start $service
done
sudo systemctl list-units > systemd_backup.txt

## Enable auto-start

sudo systemctl enable justnews-*

```bash

## Scaling Procedures

### Horizontal Scaling

#### systemd Scaling

```yaml
Use systemd templated units or clone the unit to start additional instances of an agent if you need horizontal scaling.
Example: Run multiple instances of `justnews-scout@` template (if available) or duplicate the unit with numbered instances and start them as required.

```

## Start a second instance

sudo systemctl enable --now justnews-scout@2.service

```yaml

  metrics:

  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70

```

#### Manual Scaling

```bash

## For systemd: start additional instances or use templated units to add more replicas

sudo systemctl enable --now justnews-scout@2.service

```bash

### Vertical Scaling

#### GPU Scaling (systemd)

```bash

## Check GPU utilization

nvidia-smi

## Update GPU resource allocation in the service configuration. For systemd based deployments, update the service environment or system-wide GPU limits and restart the service. See the `infrastructure/systemd/units/` templates for guidance.

```

#### Memory/CPU Scaling

```bash

## Update resource requests/limits

Edit the relevant systemd service file to adjust resources and restart the service:

```bash

sudo systemctl edit --full justnews-synthesizer.service sudo systemctl daemon- reload sudo systemctl restart justnews-
synthesizer

```

```

## Monitoring & Alerting

### Health Checks

- Monitoring script catalog: [MONITORING_SCRIPTS_REFERENCE.md](./MONITORING_SCRIPTS_REFERENCE.md)

#### Service Health

```bash

## Check all services

curl <http://localhost:8000/health>
curl <http://localhost:8001/health>

## ... check all agent health endpoints

## Service health (systemd)

sudo systemctl status justnews-mcp-bus
sudo systemctl status justnews-scout
sudo journalctl -u <unit-name> -f

```bash

#### Application Metrics

```bash

## Prometheus metrics

curl <http://localhost:9090/metrics>

## Custom metrics

curl <http://localhost:8000/metrics>
curl <http://localhost:8004/metrics>  # GPU metrics

```

### Alerting Configuration

#### Prometheus Alerts

```yaml
groups:

- name: justnews_alerts
  rules:

  - alert: HighCPUUsage
    expr: cpu_usage_percent > 85
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High CPU usage detected"

  - alert: GPUOutOfMemory
    expr: gpu_memory_used_percent > 95
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "GPU memory critically high"

```bash

#### Dashboard Access

```bash

## Grafana dashboard

open <http://localhost:3000>

## Application dashboard

open <http://localhost:8013>

```

## Backup & Recovery

### Database Backup

```bash

## MariaDB backup

mysqldump -h localhost -u justnews -p justnews_db > backup_$(date +%Y%m%d).sql

## ChromaDB backup (copy data directory)

cp -r /chroma/chroma /backup/chroma_$(date +%Y%m%d)

## Automated backup script

./scripts/backup_database.sh

```bash

### Configuration Backup

```bash

## Backup configs

tar -czf config_backup_$(date +%Y%m%d).tar.gz config/

## systemd units backup

sudo systemctl list-units --type=service --state=active > systemd_backup.txt

```

### Recovery Procedures

#### Database Recovery

```bash

## Stop all services

for svc in justnews-*; do sudo systemctl stop $svc || true; done

## Restore database

mysql -h localhost -u justnews -p justnews_db < backup_file.sql

## Restart services

for svc in justnews-*; do sudo systemctl start $svc || true; done

```

#### Full System Recovery

```bash

## Complete recovery script

./scripts/disaster_recovery.sh

## Verify recovery

make health-check
make test-integration

```

## Security Operations

### Access Control

```bash

## Rotate API keys

./scripts/rotate_api_keys.sh

## Update certificates

./scripts/update_certificates.sh

## Security audit

./scripts/security_audit.sh

```

### Compliance Monitoring

```bash

## GDPR compliance check

./scripts/gdpr_audit.sh

## Data retention cleanup

./scripts/data_cleanup.sh

## Audit log review

./scripts/review_audit_logs.sh

```

## Troubleshooting

### Common Issues

#### Service Startup Failures

```bash

## Check service logs

sudo journalctl -u justnews-mcp-bus -f

## Check system events

sudo journalctl -u justnews-mcp-bus --since "1 hour ago"

## Check resource constraints

sudo systemctl status <unit-name>

```bash

#### Performance Issues

```bash

## Check resource usage

top -b -n 1 | head -n 20

## Check GPU usage

nvidia-smi

## Profile application

./scripts/profile_performance.sh

```

#### Network Issues

```bash

## Check service connectivity

curl <http://localhost:8000/health>

## Network policies are not applicable to systemd-managed services

## DNS resolution

nslookup mcp-bus

```

## Maintenance Windows

### Scheduled Maintenance

```bash

## Enter maintenance mode

./scripts/maintenance_mode.sh enable

## Perform maintenance

## ... maintenance tasks ...

## Exit maintenance mode

./scripts/maintenance_mode.sh disable

```

### Rolling Updates

```bash

## Rolling updates with systemd

Update code, update the unit file or the ExecStart command, and run:

```bash

sudo systemctl daemon-reload sudo systemctl restart justnews-scout

```bash

Rollback: Revert the unit file or binaries and run `sudo systemctl restart justnews-scout`.

```

---

*Operations Guide Version: 1.0.0* *Last Updated: October 22, 2025*
