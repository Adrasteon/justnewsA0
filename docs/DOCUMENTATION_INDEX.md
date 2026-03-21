--- title: JustNews Documentation Index description: Complete guide to all JustNews documentation ---

# JustNews Documentation Index

This is a comprehensive index of all JustNews documentation, organized by topic and audience.

## 🚀 For New Operators (Start Here!)

- [Roo Gemma 3 Indexing Quickstart](../ROO_GEMMA3_INDEXING_QUICKSTART.md) — Fast path for Roo + LM Studio + Qdrant in dev-container

**Essential Reading** (in order):

1. [Setup Guide](./operations/SETUP_GUIDE.md) — Complete installation from scratch

- Python 3.12 and Miniconda setup

- Conda environment creation

- Global environment configuration

- Vault OSS installation and initialization

- MariaDB database setup

- ChromaDB vector database setup

- Verification and testing

- Systemd integration

1. [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) — Understanding and managing configuration

- Global.env file structure

- Secrets management integration

- Environment variable reference

- Troubleshooting common config issues

1. [Vault Administration](./operations/VAULT_SETUP.md) — Managing secrets securely

- Vault architecture and design

- AppRole authentication setup

- Secret creation and rotation

- Emergency procedures

- Integration with systemd services

1. [Troubleshooting](./operations/TROUBLESHOOTING.md) — When things go wrong

- Service health checks

- Common issues and fixes

- Emergency recovery procedures

- Performance monitoring

1. [Monitoring Infrastructure](./operations/MONITORING_INFRASTRUCTURE.md) — Setting up Prometheus and Grafana

- Pre-configured dashboards and configuration

- Integration with service monitoring

- Dashboard usage guide

1. **[Monitoring Quick Deploy](./operations/MONITORING_QUICK_DEPLOY.md)** — **⭐ Start here for quick deployment**

- One-command deployment script

- Full automation of installation and setup

- Step-by-step guide for deployment

- Troubleshooting tips

## 📋 For Operations / System Administrators

**Core Documentation**:

- [Setup Guide](./operations/SETUP_GUIDE.md) — End-to-end installation

- [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) — Config management

- [Living Stories Architecture](./LIVING_STORIES_ARCHITECTURE.md) — Canonical story model, meaningful-change gating, and lifecycle

- [Living Story Runbook](./operations/LIVING_STORY_RUNBOOK.md) — Day-2 operations, validation, thresholds, and troubleshooting

- [Investor One-Pager: Multi-Source Integrity Refactor (2026-02-22)](./operations/INVESTOR_ONE_PAGER_MULTI_SOURCE_REFACTOR_2026-02-22.md) — Strategic rationale, KPI framework, and phased delivery

- [Investor Technical Appendix: Multi-Source Integrity Refactor (2026-02-22)](./operations/INVESTOR_TECH_APPENDIX_MULTI_SOURCE_REFACTOR_2026-02-22.md) — Technical rollout details, telemetry, and controls

- [Multi-Source Refactor Project Plan (2026-02-22)](./operations/MULTI_SOURCE_REFACTOR_PROJECT_PLAN_2026-02-22.md) — Execution plan, milestones, RACI, and go/no-go gates

- [Multi-Source Refactor Action Checklist (2026-02-22)](./operations/MULTI_SOURCE_REFACTOR_ACTION_CHECKLIST_2026-02-22.md) — Implementation checklist, validation steps, and evidence tracking

- [Multi-Source Refactor M2 Sign-Off Evidence Index (2026-02-22)](./operations/MULTI_SOURCE_REFACTOR_M2_SIGNOFF_EVIDENCE_INDEX_2026-02-22.md) — Canonical artifact index for M2 gate sign-off (QA/Ops/Product)

- [Multi-Source Refactor M2 Sign-Off Summary (Draft, 2026-02-22)](./operations/MULTI_SOURCE_REFACTOR_M2_SIGNOFF_SUMMARY_2026-02-22_DRAFT.md) — Draft decision memo with consolidated evidence and pending approver fields

- [Multi-Source Refactor Closeout Summary (2026-02-22)](./operations/MULTI_SOURCE_REFACTOR_CLOSEOUT_SUMMARY_2026-02-22.md) — Current-purpose closure record with delivered scope and follow-up items

- [Multi-Source Refactor Dev/Staging Parity Runsheet (2026-02-22)](./operations/MULTI_SOURCE_REFACTOR_DEV_STAGING_PARITY_RUNSHEET_2026-02-22.md) — Operator execution checklist to capture remaining dev/staging parity artifacts

- [Multi-Source Refactor Metrics Snapshot (Local, 2026-02-22)](./operations/MULTI_SOURCE_REFACTOR_METRICS_SNAPSHOT_2026-02-22_LOCAL.md) — Seeded `/metrics` evidence confirming required lane observability series

- [Multi-Source Refactor Observability Dashboard (Grafana JSON)](./grafana/multi-source-refactor-observability-dashboard.json) — Panel definitions for verified share, lane totals, promotion failures, and conversions

- [Multi-Source Refactor Alert Rules](../monitoring/alerts/multi_source_refactor_alerts.yml) — Alert IDs for verified-share degradation and promotion-failure spikes

- [Multi-Source Refactor Rollback Drill Artifact Template (2026-02-22)](./operations/MULTI_SOURCE_REFACTOR_ROLLBACK_DRILL_ARTIFACT_TEMPLATE_2026-02-22.md) — Standardized capture format for apply/rollback payloads, latency, and reversion proof

- [Multi-Source Refactor Rollback Drill Artifact (Local, 2026-02-22)](./operations/MULTI_SOURCE_REFACTOR_ROLLBACK_DRILL_ARTIFACT_2026-02-22_LOCAL.md) — Seeded rollback evidence from local control-plane harness run

- [Multi-Source Refactor Provenance Sample Evidence Template (2026-02-22)](./operations/MULTI_SOURCE_REFACTOR_PROVENANCE_SAMPLE_EVIDENCE_TEMPLATE_2026-02-22.md) — Standardized sample-record checklist for provenance field completeness

- [Multi-Source Refactor Provenance Sample Evidence (Local, 2026-02-22)](./operations/MULTI_SOURCE_REFACTOR_PROVENANCE_SAMPLE_EVIDENCE_2026-02-22_LOCAL.md) — Seeded provenance-field completeness evidence from local harness sample set

- [AI Assistant Refactor Guardrails (2026-02-22)](./operations/AI_ASSISTANT_REFACTOR_GUARDRAILS_2026-02-22.md) — AI implementation constraints, safety rules, and acceptance gates

- [AI Assistant Task Prompt Template (2026-02-22)](./operations/AI_ASSISTANT_TASK_PROMPT_TEMPLATE_2026-02-22.md) — Standardized prompt scaffold to enforce guardrails on each AI task

- [Vault Setup & Administration](./operations/VAULT_SETUP.md) — Secrets management

- [Troubleshooting](./operations/TROUBLESHOOTING.md) — Diagnostics and recovery

- [Monitoring Infrastructure](./operations/MONITORING_INFRASTRUCTURE.md) — Prometheus/Grafana deployment

- [Monitoring Scripts Reference](./operations/MONITORING_SCRIPTS_REFERENCE.md) — Script-by-script operational guide for workflow, crawl, DB, embedding, and clustering diagnostics

- [Autonomic Dynamic Orchestrator Implementation Plan (2026-03-18)](./operations/AUTONOMIC_DYNAMIC_ORCHESTRATOR_IMPLEMENTATION_PLAN_2026-03-18.md) — File-level implementation backlog and canary defaults for real-time dynamic control

- [Two-Lane Traceability Implementation Plan (2026-03-20)](./operations/TWO_LANE_TRACEABILITY_IMPLEMENTATION_PLAN_2026-03-20.md) — File-level backlog for BBC-seed Lane 1, DDG comparative retrieval, structured attribution, and balance governance

- [Hybrid Whitelist + Discovery Implementation Tickets (2026-03-21)](./operations/HYBRID_WHITELIST_DISCOVERY_IMPLEMENTATION_TICKETS_2026-03-21.md) — Implementation-ready epics and ticket-level acceptance criteria for global discovery with strict guardrails

- [Hybrid Whitelist + Discovery Execution Checklist (2026-03-21)](./operations/HYBRID_WHITELIST_DISCOVERY_EXECUTION_CHECKLIST_2026-03-21.md) — Phase-gated rollout checklist with stop conditions and rollback controls

- [Crawl Ingestion Triage Decisions (2026-03-21)](./operations/CRAWL_INGESTION_TRIAGE_DECISIONS_2026-03-21.md) — Summary of prompt experiment evidence, architectural decisions, and implemented deterministic+AI triage path

- [Crawl Ingestion Triage System Guide (2026-03-21)](./operations/CRAWL_INGESTION_TRIAGE_SYSTEM_GUIDE_2026-03-21.md) — Complete guide to triage architecture, decision flow, operator controls, metadata, and failure handling

- [Crawler Ingest Resiliency Runbook](./operations/CRAWLER_INGEST_RESILIENCY.md) — Disk-backed deferred ingest spool, replay tuning, and outage recovery

**Deployment & Infrastructure**:

- [Systemd Operations](./infrastructure/systemd/README.md) — Service management

- [Operations Guide](./operations/README.md) — General operational procedures

- [Live SEO Launch Checklist](./operations/LIVE_SEO_LAUNCH_CHECKLIST.md) — Required pre-launch and post-launch SEO/crawler actions for the public website

**Monitoring & Maintenance**:

- [GPU Monitoring](./operations/gpu-monitoring.md) — GPU resource monitoring

- [Systemd Monitoring](./operations/systemd-monitoring.md) — Service health monitoring

- [Hardware Safety & Constraints](./operations/hardware_safety.md) — Power limits and memory constraints

- [Monitoring Infrastructure](./operations/MONITORING_INFRASTRUCTURE.md) — Prometheus and Grafana setup

- [Monitoring Scripts Reference](./operations/MONITORING_SCRIPTS_REFERENCE.md) — Detailed usage and technical signals for monitoring/status scripts

- [Autonomic Dynamic Orchestrator Implementation Plan (2026-03-18)](./operations/AUTONOMIC_DYNAMIC_ORCHESTRATOR_IMPLEMENTATION_PLAN_2026-03-18.md) — Execution roadmap for autonomous real-time orchestration

- [Dashboard Quick Reference](./operations/dashboard-quick-reference.md) — Analytics dashboard

**Database Management**:

- [Database Documentation](../database/README.md) — MariaDB schema and migrations

- [Database ORM Guide](../database/core/) — ORM and connection pooling

## 👨‍💻 For Developers

**Setup for Development**:

1. Read [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) to understand the environment

1. Follow [Setup Guide Phase 1-2](./operations/SETUP_GUIDE.md#phase-1-python-312--miniconda) to set up your machine

1. Check out [Development Guide](./developer/) for coding standards

**Common Development Tasks**:

- [Testing Guide](./developer/) — Running tests locally

- [API Documentation](./api/) — REST API reference

- [Architecture Documentation](../docs/) — System design and patterns

**Environment & Configuration**:

- [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) — How to use environment variables

- [Global.env Reference](./operations/ENVIRONMENT_CONFIG.md#the-etcjustnewsglobalenv-file) — Configuration file
  structure

## 🔒 For Security / Compliance Teams

**Secrets & Authentication**:

- [Vault Setup & Administration](./operations/VAULT_SETUP.md) — Secrets management architecture

- Vault OSS (open-source, no cloud dependency)

- AppRole authentication

- Secret rotation procedures

- Emergency access procedures

**Security Considerations**:

- [Vault Setup - Security Section](./operations/VAULT_SETUP.md#security-considerations) — Best practices

- [Environment Configuration - Secrets](./operations/ENVIRONMENT_CONFIG.md#secrets-management) — Secrets hierarchy

## 📊 For Data / Analytics Teams

**Database Schema**:

- [Database Models](../database/models/) — Table definitions

- [Database README](../database/README.md) — Schema overview

**Analytics & Metrics**:

- [Dashboard Quick Reference](./operations/dashboard-quick-reference.md) — Analytics dashboard usage

- [Monitoring Guide](./operations/systemd-monitoring.md) — Metrics and monitoring

## 🎯 Topic-Based Index

### Installation & Setup

- [Setup Guide](./operations/SETUP_GUIDE.md) — Complete installation

- [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) — Configuration files

- [Vault Setup](./operations/VAULT_SETUP.md) — Secrets infrastructure

### Configuration Management

- [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) — Full guide

- [Global.env Reference](./operations/ENVIRONMENT_CONFIG.md#the-etcjustnewsglobalenv-file) — Configuration file

- [Environment Variables](./operations/ENVIRONMENT_CONFIG.md#common-environment-variables) — Variable reference

### Database Management

- [Database README](../database/README.md) — Overview

- [Database Models](../database/models/) — Table definitions

- [Database Migrations](../database/migrations/) — Schema versions

### Secrets & Security

- [Vault Setup & Administration](./operations/VAULT_SETUP.md) — Complete guide

- [AppRole Authentication](./operations/VAULT_SETUP.md#approle-authentication) — Service auth

- [Secret Rotation](./operations/VAULT_SETUP.md#secret-rotation) — Regular key rotation

- [Environment Secrets](./operations/ENVIRONMENT_CONFIG.md#secrets-management) — Using secrets in code

### Service Management

- [Setup Guide - Systemd Integration](./operations/SETUP_GUIDE.md#phase-7-systemd-integration-and-startup) — Service
  setup

- [Systemd Operations](./infrastructure/systemd/README.md) — Service commands

- [Systemd Monitoring](./operations/systemd-monitoring.md) — Health checks

- [Crawler Ingest Resiliency Runbook](./operations/CRAWLER_INGEST_RESILIENCY.md) — Deferred ingest spool controls and replay diagnostics

### Monitoring & Troubleshooting

- [Troubleshooting Guide](./operations/TROUBLESHOOTING.md) — Complete reference

- [Living Story Runbook](./operations/LIVING_STORY_RUNBOOK.md) — Living-story-specific diagnostics and tuning

- [GPU Monitoring](./operations/gpu-monitoring.md) — GPU resources

- [Systemd Monitoring](./operations/systemd-monitoring.md) — Service health

- [Monitoring Scripts Reference](./operations/MONITORING_SCRIPTS_REFERENCE.md) — Script catalog and operational run sequence

- [Dashboard Reference](./operations/dashboard-quick-reference.md) — Analytics

### Deployment

- [Setup Guide](./operations/SETUP_GUIDE.md) — Initial deployment

- [Systemd Operations](./infrastructure/systemd/README.md) — Service deployment

- [Operations Guide](./operations/README.md) — General procedures

## 📁 Documentation File Locations

```bash

docs/
├── api/                           # REST API reference
├── developer/                     # Developer guides
├── LIVING_STORIES_ARCHITECTURE.md # Living story architecture (current behavior)
├── LIVING_STORIES_IMPLEMENTATION_PLAN.md # Phase roadmap and status
├── operations/                    # Operational procedures
│   ├── SETUP_GUIDE.md            # ⭐ Start here: Complete installation
│   ├── ENVIRONMENT_CONFIG.md     # Configuration management
│   ├── VAULT_SETUP.md            # Secrets administration
│   ├── TROUBLESHOOTING.md        # Diagnostics & recovery
│   ├── LIVING_STORY_RUNBOOK.md   # Living story operations and tuning
│   ├── README.md                 # Operations overview
│   ├── gpu-monitoring.md         # GPU monitoring
│   ├── systemd-monitoring.md     # Service health monitoring
│   └── ...
├── user-guides/                  # End-user documentation
├── CONTRIBUTING.md               # Contribution guidelines
└── ...

database/
├── README.md                      # Database architecture
├── models/                        # Table definitions
├── migrations/                    # Schema migrations
└── core/                          # ORM and utilities

infrastructure/
├── systemd/
│   └── README.md                 # Service management
└── ...

```

## 🔍 Quick Reference by Task

### "I'm new to JustNews and need to set up a machine"

→ Read [Setup Guide](./operations/SETUP_GUIDE.md) in order (7 phases)

### "I need to understand the configuration system"

→ Read [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md)

### "How do I manage secrets?"

→ Read [Vault Setup & Administration](./operations/VAULT_SETUP.md)

### "Something broke, how do I fix it?"

→ Read [Troubleshooting](./operations/TROUBLESHOOTING.md)

### "How do I monitor system and service health?"

→ Read [Monitoring Infrastructure](./operations/MONITORING_INFRASTRUCTURE.md)

→ Use [Monitoring Scripts Reference](./operations/MONITORING_SCRIPTS_REFERENCE.md) for script-level checks and signal interpretation

### "How do I run a test locally?"

→ Activate conda environment, then see [Development Guide](./developer/)

### "How do I deploy to production?"

→ Follow [Setup Guide](./operations/SETUP_GUIDE.md), then [Systemd Operations](./infrastructure/systemd/README.md)

### "Where is the database schema?"

→ See [Database README](../database/README.md) and [Models](../database/models/)

### "How do I rotate secrets?"

→ See [Vault Setup - Secret Rotation](./operations/VAULT_SETUP.md#secret- rotation)

### "How do I monitor system health?"

→ See [Troubleshooting - Monitoring](./operations/TROUBLESHOOTING.md#monitoring- and-observability)

→ See [Monitoring Scripts Reference](./operations/MONITORING_SCRIPTS_REFERENCE.md)

### "What are all the environment variables?"

→ See [Environment Configuration - Common Variables](./operations/ENVIRONMENT_CONFIG.md#common-environment-variables)

## 📞 Getting Help

1. **Check the docs first**:

- [Troubleshooting Guide](./operations/TROUBLESHOOTING.md) — Common issues

- FAQ — Frequently asked questions

- Glossary — Key terms

1. **Review relevant documentation**:

- Installation issues → [Setup Guide](./operations/SETUP_GUIDE.md)

- Configuration issues → [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md)

- Secrets issues → [Vault Setup](./operations/VAULT_SETUP.md)

- Service issues → [Troubleshooting](./operations/TROUBLESHOOTING.md)

1. **Check logs**:

```bash
   # View service logs
sudo journalctl -u vault -u mariadb -u chromadb -f

   # Check application logs
tail -f logs/*.log ```

1. **Run diagnostics**:

```bash
# Full health check
bash scripts/run_with_env.sh python check_databases.py

# Service status
sudo systemctl status vault mariadb chromadb
```

## 📝 Documentation Standards

All documentation follows these standards:

- **YAML frontmatter**: Title, description, optional tags

- **Headers**: H1 for page title, H2+ for sections

- **Code blocks**: Language-tagged for syntax highlighting

- **Tables**: For reference material

- **Internal links**: Relative paths for repo navigation

- **External links**: Full URLs with clear context

---

**Last Updated**: December 15, 2024 **Version**: 4.0.0 **Maintainer**: JustNews Operations Team
