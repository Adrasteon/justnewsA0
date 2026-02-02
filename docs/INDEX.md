---
title: "JustNews Documentation Index"
description: "Master navigation and comprehensive documentation index for JustNews V4.0"
tags: ["documentation", "index", "navigation", "getting-started"]
status: "current"
version: "2.0"
last_updated: "2026-02-02"
audience: ["everyone"]
---

# JustNews Documentation Index

**Master Navigation Point** | **Last Updated**: February 2, 2026

This is your authoritative guide to all JustNews documentation. Choose your role below to get started.

---

## 🚀 **Quick Start by Role**

### 👤 For New Operators (Start Here!)

Getting JustNews running on a new machine? **Start in order:**

1. **[Setup Guide](./operations/SETUP_GUIDE.md)** - Complete installation from scratch
   - Python 3.12 & Miniconda setup
   - Conda environment creation (phased environments)
   - Global environment configuration
   - Vault secrets management setup
   - MariaDB database initialization
   - ChromaDB vector store setup
   - Systemd integration & startup

2. **[Startup Analysis & Architecture](./operations/startup-analysis.md)** - Understanding the canonical startup system
   - 5-phase startup sequence
   - Database migration enforcement
   - vLLM GPU readiness verification
   - Integration smoke tests

3. **[Operator Quick Start](./operations/operator-quick-start.md)** - Day-to-day operations
   - Common scenarios with commands
   - Health check procedures
   - Performance expectations
   - Troubleshooting guide

4. **[Environment Configuration](./operations/ENVIRONMENT_CONFIG.md)** - Managing config & secrets
   - Global.env structure
   - Vault integration
   - Environment variables reference
   - Secrets management

5. **[Troubleshooting Guide](./operations/TROUBLESHOOTING.md)** - When things go wrong
   - Service health diagnostics
   - Common issues & fixes
   - Emergency recovery
   - Log analysis

---

### 🔧 For System Administrators/DevOps

**Infrastructure & Operations:**
- [Setup Guide](./operations/SETUP_GUIDE.md) - Complete installation procedures
- [Vault Setup & Administration](./operations/VAULT_SETUP.md) - Secrets infrastructure
- [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) - Config management
- [Systemd Operations](./infrastructure/systemd/README.md) - Service management
- [Troubleshooting Guide](./operations/TROUBLESHOOTING.md) - Diagnostics

**Monitoring & Observability:**
- [Monitoring Infrastructure](./operations/MONITORING_INFRASTRUCTURE.md) - Prometheus/Grafana deployment
- [GPU Monitoring Guide](./operations/gpu-monitoring.md) - GPU resource monitoring
- [Systemd Health Monitoring](./operations/systemd-monitoring.md) - Service health checks
- [Hardware Safety & Constraints](./operations/hardware_safety.md) - Power limits, memory

**Database Management:**
- [MariaDB Integration Guide](./infrastructure/systemd/mariadb_integration.md) - Database setup & connectivity
- [Database Documentation](../database/README.md) - Schema reference
- [Database ORM Guide](../database/core/) - Connection pooling & ORM patterns

---

### 👨‍💻 For Developers

**Getting Started:**
1. Read [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) - understand the environment
2. Follow [Setup Guide Phase 1-2](./operations/SETUP_GUIDE.md#phase-1-python-312--miniconda) - local machine setup
3. Check [Development Guide](./developer/) - coding standards & testing

**Development Tasks:**
- [API Documentation](./api/) - REST API reference
- [Architecture Overview](./architecture_overview.md) - System design & patterns
- [Testing Guide](./developer/) - Running tests locally
- [Workflow Orchestrator Guide](./orchestrator/WORKFLOW_ORCHESTRATOR.md) - Agent orchestration

**Configuration & Environment:**
- [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) - All environment variables
- [Vault Setup for Developers](./operations/VAULT_SETUP.md#for-developers) - Secrets in development

---

### 🔒 For Security/Compliance Teams

**Secrets & Authentication:**
- [Vault Setup & Administration](./operations/VAULT_SETUP.md) - Complete secrets infrastructure
  - Raft storage architecture
  - AppRole authentication setup
  - Secret rotation procedures
  - Emergency access protocols
  - Security best practices

**Secrets Management:**
- [Environment Configuration - Secrets Section](./operations/ENVIRONMENT_CONFIG.md#secrets-management) - Secrets hierarchy
- [Vault Security Considerations](./operations/VAULT_SETUP.md#security-considerations) - Best practices

---

### 📊 For Data/Analytics Teams

**Database & Schema:**
- [Database Documentation](../database/README.md) - Schema overview
- [Database Models](../database/models/) - Table definitions & relationships
- [Database Migrations](../database/migrations/) - Schema version history

**Monitoring & Metrics:**
- [Dashboard Quick Reference](./operations/dashboard-quick-reference.md) - Analytics dashboards
- [Monitoring Infrastructure](./operations/MONITORING_INFRASTRUCTURE.md) - Metrics setup
- [GPU Monitoring](./operations/gpu-monitoring.md) - GPU metrics

---

## 📚 **Documentation by Category**

### Installation & Setup
| Document | Purpose | Audience |
|----------|---------|----------|
| [Setup Guide](./operations/SETUP_GUIDE.md) | Complete end-to-end installation | Operators, DevOps |
| [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) | Config files & environment variables | All users |
| [Vault Setup & Administration](./operations/VAULT_SETUP.md) | Secrets infrastructure setup | DevOps, Security |

### Configuration Management
| Document | Purpose | Audience |
|----------|---------|----------|
| [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md) | Global.env, env vars, secrets | All users |
| [Systemd Operations](./infrastructure/systemd/README.md) | Service management & systemd | DevOps, Operators |

### Operations & Troubleshooting
| Document | Purpose | Audience |
|----------|---------|----------|
| [Startup Analysis](./operations/startup-analysis.md) | 5-phase canonical startup | Operators, DevOps |
| [Operator Quick Start](./operations/operator-quick-start.md) | Day-to-day operations & health checks | Operators |
| [Troubleshooting Guide](./operations/TROUBLESHOOTING.md) | Diagnostics & problem resolution | All users |
| [Operations Guide](./operations/README.md) | General operational procedures | Operators |

### Infrastructure & Deployment
| Document | Purpose | Audience |
|----------|---------|----------|
| [Systemd Deployment Guide](./infrastructure/systemd/README.md) | Service orchestration & management | DevOps, Operators |
| [Systemd Comprehensive Guide](./infrastructure/systemd/COMPREHENSIVE_SYSTEMD_GUIDE.md) | Advanced systemd configuration | DevOps |
| [MariaDB Integration](./infrastructure/systemd/mariadb_integration.md) | Database connectivity & checks | DevOps, DBAs |

### Monitoring & Observability
| Document | Purpose | Audience |
|----------|---------|----------|
| [Monitoring Infrastructure](./operations/MONITORING_INFRASTRUCTURE.md) | Prometheus/Grafana deployment | DevOps, SREs |
| [GPU Monitoring](./operations/gpu-monitoring.md) | GPU resource tracking | DevOps, Operators |
| [Systemd Health Monitoring](./operations/systemd-monitoring.md) | Service health checks | Operators |
| [Dashboard Quick Reference](./operations/dashboard-quick-reference.md) | Analytics dashboards | Data teams, Analysts |
| [Dashboard Deprecation Fix](./operations/fix_dashboards.md) | Resolving Grafana issues | DevOps |

### Database & Schema
| Document | Purpose | Audience |
|----------|---------|----------|
| [Database README](../database/README.md) | Schema overview & architecture | Data teams, DBAs |
| [Database Models](../database/models/) | Table definitions & relationships | Developers, Data teams |
| [Database Migrations](../database/migrations/) | Schema version history | DevOps, Developers |

### Architecture & Design
| Document | Purpose | Audience |
|----------|---------|----------|
| [Architecture Overview](./architecture_overview.md) | System design & patterns | Architects, Developers |
| [Workflow Orchestrator](./orchestrator/WORKFLOW_ORCHESTRATOR.md) | Agent coordination via MCP | Developers |

### Development
| Document | Purpose | Audience |
|----------|---------|----------|
| [Developer Guide](./developer/README.md) | Coding standards & development setup | Developers |
| [API Reference](./api/README.md) | REST API documentation | Developers |
| [Contributing Guidelines](./CONTRIBUTING.md) | Pull request & contribution process | Contributors |

### Hardware & Constraints
| Document | Purpose | Audience |
|----------|---------|----------|
| [Hardware Safety & Constraints](./operations/hardware_safety.md) | Power limits, memory constraints | DevOps, Operators |
| [Model & Orchestrator Setup](./operations/ModelSpec.md) | GPU model configuration | Operators, Developers |
| [vLLM Mistral Setup](./operations/VLLM_MISTRAL_7B_SETUP.md) | vLLM with Mistral-7B | Operators |

---

## 🏗️ **Documentation Structure**

```
docs/
├── INDEX.md                          ⭐ You are here (master navigation)
├── README.md                          # Documentation overview
├── architecture_overview.md           # System design & patterns
├── CONTRIBUTING.md                    # Contribution guidelines
│
├── api/                               # REST API documentation
│   └── README.md                      # API reference entry point
│
├── developer/                         # Development guides
│   ├── README.md                      # Developer getting started
│   └── ...
│
├── operations/                        # Operational procedures
│   ├── README.md                      # Operations overview
│   ├── SETUP_GUIDE.md                 # ⭐ Installation (start here)
│   ├── ENVIRONMENT_CONFIG.md          # Config management
│   ├── VAULT_SETUP.md                 # Secrets infrastructure
│   ├── TROUBLESHOOTING.md             # Diagnostics & recovery
│   ├── operator-quick-start.md        # Day-to-day operations
│   ├── startup-analysis.md            # Canonical startup system
│   ├── MONITORING_INFRASTRUCTURE.md   # Prometheus/Grafana setup
│   ├── gpu-monitoring.md              # GPU resource monitoring
│   ├── systemd-monitoring.md          # Service health monitoring
│   ├── dashboard-quick-reference.md   # Analytics dashboards
│   ├── hardware_safety.md             # Power limits, memory constraints
│   ├── ModelSpec.md                   # GPU model configuration
│   └── VLLM_MISTRAL_7B_SETUP.md       # vLLM + Mistral-7B setup
│
├── infrastructure/                    # Infrastructure & deployment
│   └── systemd/                       # Systemd orchestration
│       ├── README.md                  # Systemd operations
│       ├── COMPREHENSIVE_SYSTEMD_GUIDE.md  # Advanced configuration
│       ├── QUICK_REFERENCE.md         # Copy-paste commands
│       └── mariadb_integration.md     # Database connectivity
│
├── orchestrator/                      # Workflow orchestration
│   └── WORKFLOW_ORCHESTRATOR.md       # Agent orchestration guide
│
└── tools/                             # Diagnostic tools
    └── DIAGNOSTIC_SCRIPTS.md          # Available diagnostic tools
```

---

## 📖 **How to Use This Index**

1. **Find Your Role** - Choose the section that matches your role (Operator, Developer, etc.)
2. **Follow the Path** - Each role has documents in recommended reading order
3. **Use Categories** - Browse by category if looking for specific topics
4. **Check Status** - Look for status badges to find current vs deprecated docs
5. **Cross-Reference** - Links between documents help navigate related topics

---

## 📋 **Documentation Status**

| Status | Meaning | Color |
|--------|---------|-------|
| ✅ Current | Active, production-ready | Green |
| ⚠️ Updated | Recently updated, review recommended | Yellow |
| ⏳ In Progress | Being developed | Blue |
| ❌ Deprecated | Superseded, moved to archive | Red |
| 🔒 Restricted | Access limited (security/compliance) | Gray |

**All documents listed above have status "✅ Current"** unless otherwise marked.

---

## 🔍 **Quick Reference by Task**

### "I'm new to JustNews"
→ [Setup Guide](./operations/SETUP_GUIDE.md)

### "I need to start/stop JustNews"
→ [Operator Quick Start](./operations/operator-quick-start.md)

### "Something broke, how do I fix it?"
→ [Troubleshooting Guide](./operations/TROUBLESHOOTING.md)

### "I need to understand configuration"
→ [Environment Configuration](./operations/ENVIRONMENT_CONFIG.md)

### "How do I manage secrets?"
→ [Vault Setup & Administration](./operations/VAULT_SETUP.md)

### "How do I monitor the system?"
→ [Monitoring Infrastructure](./operations/MONITORING_INFRASTRUCTURE.md)

### "I want to develop a feature"
→ [Developer Guide](./developer/README.md)

### "I need API documentation"
→ [API Reference](./api/README.md)

### "How do services work together?"
→ [Architecture Overview](./architecture_overview.md)

### "How do I deploy to production?"
→ [Setup Guide](./operations/SETUP_GUIDE.md) + [Systemd Deployment](./infrastructure/systemd/README.md)

---

## 📞 **Getting Help**

- **Documentation Issue?** Check [Troubleshooting Guide](./operations/TROUBLESHOOTING.md)
- **Found a Bug in Docs?** See [Contributing Guidelines](./CONTRIBUTING.md)
- **Technical Question?** Search the relevant guide above or check code comments
- **Production Emergency?** Follow [Emergency Recovery](./operations/TROUBLESHOOTING.md#emergency-recovery)

---

## 🔄 **Documentation Updates & Maintenance**

**Last Comprehensive Update**: February 2, 2026  
**Documentation Version**: 2.0 (Enterprise-Grade Standard)  
**Metadata Format**: YAML frontmatter with status, audience, and versioning

**All documentation files include**:
- Status badge (current, deprecated, in-progress)
- Target audience specification
- Last update timestamp
- Clear cross-references

---

**Start exploring:** Choose your role above and begin reading documents in the recommended order. All links are relative and work within this documentation structure.
