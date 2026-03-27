# JustNews Deployment System - Unified Infrastructure as Code

Docker-first deployment framework for the JustNews distributed system. systemd remains available as an optional
host-wrapper/legacy compatibility path during transition.

## Overview

The deployment system provides a unified approach to deploying JustNews across different environments and platforms. It
supports:

- **Docker Compose**: Canonical app runtime and service lifecycle

- **systemd**: Optional host-level wrapper and legacy compatibility path

- **Infrastructure as Code**: Declarative configuration management

- **Multi-environment**: Development, staging, production profiles

---

## Recent updates (what changed)

We recently added several operational improvements to make local and production deployments safer and easier to manage:

- **MCP Bus health & metrics**: the MCP Bus `/health`endpoint now performs best-effort per-agent probes and returns
  structured`agent_details` plus overall status, allowing precise monitoring and alerting.

- **Prometheus & Grafana**: new Prometheus alert rules for MCP Bus overall and per-agent degraded/unreachable conditions
  (`monitoring/alerts/mcp_bus_alerts.yml`) and Grafana panels (Overall health stat, Degraded Count, Agent Status table)
  have been added and provisioned in the system overview dashboard.

- **Alertmanager support**: an example Alertmanager configuration and templates were added
  (`monitoring/alertmanager/alertmanager.example.yml`,`monitoring/alertmanager/mcp_bus_templates.tmpl`), together with
  an idempotent systemd unit installer script`scripts/install_alertmanager_unit.sh`and Makefile helpers (`make
  alertmanager-install`,`make alertmanager-install-unit`,`make alertmanager-test`).

- **Startup integration**: optional opt-in behaviour (`AUTO_INSTALL_ALERTMANAGER`) lets the`mcp_bus`startup sequence run
  the idempotent Alertmanager installer to provision and enable the host-level unit. This is disabled by default for
  multi-host safety; set`AUTO_INSTALL_ALERTMANAGER=1`in`/etc/justnews/global.env` only on controlled admin hosts.

- **Model & orchestrator readiness**: Mistral‑7B is the new default vLLM model, with ModelSpec & GPU orchestrator
  integration, conservative defaults, and monitoring for OOM/restarts. See
  `docs/operations/VLLM_MISTRAL_7B_SETUP.md`and`docs/operations/ModelSpec.md` for details.

---

## Architecture

```text
infrastructure/
├── systemd/                  # Systemd orchestration (production & dev)
│   ├── services/             # Native service definitions
│   ├── units/                # Unit files for all agents and services
│   ├── monitoring/           # Prometheus/Grafana configs
│   └── canonical_system_startup.sh # Entry point for system startup
├── scripts/                  # Global infrastructure validation
├── config/                   # Configuration templates and environments
└── helm/                     # Kubernetes charts (deprecated/archive)
```

## Quick Start

### 1. Choose Deployment Target

This workspace now treats **Docker Compose** as the canonical app orchestrator.
systemd remains supported as an optional host-level/legacy compatibility layer.

### 2. Configure Environment

Copy and customize the global environment file:

```bash
sudo cp infrastructure/systemd/examples/justnews.env.example /etc/justnews/global.env
sudo nano /etc/justnews/global.env
```

Ensure essential variables are set:
- `MARIADB_HOST`
- `CHROMA_HOST`
- `CANONICAL_ENV` (e.g., `justnews-py312`)

### 3. Deploy

Use Docker-first deployment targets:

```bash
make deploy-docker
```

Or direct compose wrapper:

```bash
bash scripts/ops/docker_compose.sh up
```

Optional legacy/systemd path remains available during transition for hosts that still rely on systemd wrappers.

## - MCP_BUS_HOST, MCP_BUS_PORT

## - LOG_LEVEL, MONITORING_ENABLED

```

### 3. Deploy Services

```bash

## Deploy all services

./scripts/deploy.sh --target $DEPLOY_TARGET --env $DEPLOY_ENV

## Deploy specific service

./scripts/deploy.sh --target $DEPLOY_TARGET --env $DEPLOY_ENV --service mcp-bus

## Check deployment status

./scripts/health-check.sh

## Rollback if needed

./scripts/rollback.sh --target $DEPLOY_TARGET

```bash

## Service Architecture

### Core Services

| Service | Type | Ports | Description | |---------|------|-------|-------------| | **mcp-bus** | FastAPI | 8000 |
Central communication hub | | **scout** | FastAPI + GPU | 8004 | Content discovery and analysis | | **analyst** |
FastAPI + GPU | 8004 | Sentiment and bias analysis | | **synthesizer** | FastAPI + GPU | 8005 | Content synthesis and
clustering | | **fact-checker** | FastAPI + GPU | 8003 | Evidence-based verification | | **memory** | FastAPI | 8007 |
Vector storage and retrieval | | **chief-editor** | FastAPI | 8001 | Workflow orchestration | | **reasoning** | FastAPI
| 8008 | Symbolic logic processing | | **newsreader** | FastAPI + GPU | 8009 | OCR and visual analysis | | **critic** |
FastAPI | 8006 | Quality assessment | | **dashboard** | FastAPI | 8013 | Web monitoring interface | | **analytics** |
FastAPI | 8011 | Advanced analytics engine | | **archive** | FastAPI | 8012 | Document storage and retrieval | |
**balancer** | FastAPI | 8010 | Load balancing and routing |  # DEPRECATED - functionality moved to
critic/analytics/gpu_orchestrator

### Infrastructure Services

| Service | Type | Ports | Description | |---------|------|-------|-------------| | **mariadb** | Database | 3306 |
Primary relational data storage | | **chromadb** | Vector DB | 3307 | Vector embeddings and semantic search | |
**redis** | Cache | 6379 | Session and cache storage | | **grafana** | Monitoring | 3000 | Dashboard and visualization |
| **prometheus** | Monitoring | 9090 | Metrics collection | | **nginx** | Reverse Proxy | 80/443 | Load balancing and
SSL |

## Deployment Targets

### Systemd (Production)

```bash

## Install systemd units

sudo cp systemd/services/*.service /etc/systemd/system/
sudo systemctl daemon-reload

## Start all services

sudo systemctl enable --now justnews-*

## View status

sudo systemctl status justnews-mcp-bus

## View logs for a specific service

sudo journalctl -u justnews-mcp-bus -f

```

### Systemd (Legacy)

```bash

## Install services

sudo cp systemd/services/*.service /etc/systemd/system/
sudo systemctl daemon-reload

## Start all services

sudo systemctl start justnews-*

## Check status

sudo systemctl status justnews-mcp-bus

```bash

## Configuration Management

### Environment Variables

```bash

## Database Configuration

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=justnews
MYSQL_USER=justnews
MYSQL_PASSWORD=secure_password

## Vector Database Configuration

CHROMA_HOST=localhost
CHROMA_PORT=3307

## Redis Configuration

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=secure_password

## GPU Configuration

GPU_ORCHESTRATOR_HOST=localhost
GPU_ORCHESTRATOR_PORT=8014
CUDA_VISIBLE_DEVICES=0,1,2,3

## MCP Bus Configuration

MCP_BUS_HOST=localhost
MCP_BUS_PORT=8000

## Monitoring Configuration

GRAFANA_ADMIN_PASSWORD=admin_password
PROMETHEUS_RETENTION_TIME=30d

## Logging Configuration

LOG_LEVEL=INFO
LOG_FORMAT=json

```

## Secrets Management

```bash

## Systemd-based secrets: Use environment files (deploy/refactor/config/environments/<env>.env)

## and restrict permissions to the config files for security (600). Use Vault or another secret manager for production secrets.

chmod 600 deploy/refactor/config/environments/production.env

```bash

### Configuration Examples

#### Systemd Configuration

```bash

## Example: edit environment file and add database configuration (deploy/refactor/config/environments/production.env)

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=justnews
MYSQL_USER=justnews
MYSQL_PASSWORD=secure_password

CHROMA_HOST=localhost
CHROMA_PORT=3307

```

## Service Dependencies

```

mcp-bus (8000) ←─┐
                   ├── scout (8004)
                   ├── analyst (8004)
mariadb (3306) ←──┼── synthesizer (8005)
chromadb (3307) ←─┼── fact-checker (8003)
redis (6379) ←────┼── memory (8007)
                   ├── chief-editor (8001)
                   ├── reasoning (8008)
                   ├── newsreader (8009)
                   └── critic (8006)

dashboard (8013) ←─┼── analytics (8011)
                   ├── archive (8012)
                   └── balancer (8010)

grafana (3000) ←── prometheus (9090)
nginx (80/443) ←───┼── all FastAPI services

```

## Health Checks and Monitoring

### Service Health Checks

```bash

## Check all services

./scripts/health-check.sh

## Check specific service

curl <http://localhost:8000/health>
curl <http://localhost:8004/health>

## Health checks (systemd)

sudo systemctl status justnews-mcp-bus
sudo systemctl status justnews-scout
sudo journalctl -u justnews-mcp-bus -f

```bash

### Monitoring Integration

This repository now includes a richer monitoring and alerting setup for operational readiness and rapid incident triage.

- **Prometheus**: configured via `infrastructure/systemd/monitoring/prometheus.yml`. Alert rules for MCP Bus are
  in`monitoring/alerts/mcp_bus_alerts.yml` (MCPBusOverallDegraded, MCPBusAgentUnreachable, MCPBusAgentDegraded).

- **Grafana**: dashboards are provisioned under `infrastructure/systemd/monitoring/grafana/provisioning`. The System
  Overview dashboard includes new panels for MCP Bus overall health, degraded agent counts and a per-agent status table
  (see`monitoring/dashboards/generated/system_overview_dashboard.json`).

- **Alertmanager**: example config & templates are provided at
  `monitoring/alertmanager/alertmanager.example.yml`and`monitoring/alertmanager/mcp_bus_templates.tmpl`.

- Idempotent installer script: `scripts/install_alertmanager_unit.sh`(backs up existing units
  to`/var/backups/justnews/alertmanager/` and replaces them safely).

- Makefile helpers: `make alertmanager-install`,`make alertmanager-install-unit`,`make alertmanager-enable`,`make
  alertmanager-test`.

- **MCP Bus health**: the MCP Bus `/health`endpoint now performs per-agent probes and emits metrics that drive alerts
  and Grafana rendering. See`docs/operations/MCP_BUS_HEALTH.md` for details and testing guidance.

Quick commands:

```bash

## Access Grafana

open <http://localhost:3000>

## Access Prometheus

open <http://localhost:9090>

## View service metrics

curl <http://localhost:8000/metrics>

## Install Alertmanager (apt or release fallback) and copy example configs

make alertmanager-install

## Install the example systemd unit for Alertmanager (idempotent)

make alertmanager-install-unit

## Enable and start Alertmanager (or boot via full startup sequence)

make alertmanager-enable

## Send a test alert to validate routing & templates

make alertmanager-test

```

Operational notes:

- We intentionally default `AUTO_INSTALL_ALERTMANAGER=0`in`/etc/justnews/global.env`; enable it only on controlled admin
  hosts if you want the MCP Bus startup to ensure Alertmanager systemd unit is installed/started automatically.

- For triage guidance and runbooks, see
  `docs/operations/MCP_BUS_ALERTS_RUNBOOK.md`and`docs/operations/MCP_BUS_HEALTH.md`.

## Scaling and Performance

### Horizontal Scaling

```bash

## systemd Horizontal Scaling

Use templated systemd units or multiple service instances for horizontal scaling.

```bash

sudo systemctl enable --now justnews-scout@2.service

```bash

## Docker Compose scaling

## systemd scaling: create additional unit instances or scale by starting multiple unit instances

for i in 1 2 3 4 5; do sudo systemctl enable --now justnews-scout@${i}; done

```

### Resource Management

```yaml

## Resource configuration

apiVersion: apps/v1
kind: Deployment
metadata:
  name: analyst
spec:
  template:
    spec:
      containers:

      - name: analyst
        resources:
          limits:
            nvidia.com/gpu: 1
            memory: 8Gi
            cpu: 2000m
          requests:
            memory: 4Gi
            cpu: 1000m

```bash

### GPU Management

```bash

## GPU resource allocation

export CUDA_VISIBLE_DEVICES=0,1,2,3
export GPU_MEMORY_FRACTION=0.8

## GPU scheduling

spec:
  template:
    spec:
      containers:

      - resources:
          limits:
            nvidia.com/gpu: 2

```

## Backup and Recovery

### Database Backup

```bash

## MariaDB backup

mysqldump -h localhost -u justnews -p justnews > backup_$(date +%Y%m%d_%H%M%S).sql

## ChromaDB backup (copy data directory)

cp -r /chroma/chroma /backup/chroma_$(date +%Y%m%d_%H%M%S)

## Redis backup

redis-cli save

```bash

### Deployment Rollback

```bash

## Rollback systemd deployment

## Revert binaries or unit files and run

sudo systemctl restart justnews-scout || true

## Rollback Docker Compose

## Docker Compose is now canonical for app runtime. Use `infrastructure/docker/docker-compose.canonical.yml` via `scripts/ops/docker_compose.sh`.

```

## Troubleshooting

### Common Issues

1. **Service Startup Failures**

```bash
   # Check logs
sudo journalctl -u justnews-mcp-bus -f

   # Check dependencies
./scripts/health-check.sh ```

1. **Database Connection Issues**

```bash
# Test MariaDB connection
mysql -h localhost -u justnews -p justnews -e "SELECT 1;"

# Test ChromaDB connection (prefer /api/v2/auth/identity; fall back to /api/v1/health or /)
curl <http://localhost:8000/api/v2/auth/identity>

# Check service status
sudo systemctl status mariadb sudo systemctl status justnews-mariadb sudo systemctl status justnews-chromadb
```

1. **GPU Resource Conflicts**

```bash
# Check GPU usage
nvidia-smi

# Check GPU orchestrator
curl <http://localhost:8014/health>
```

1. **Network Connectivity**

```bash
# Test service communication
curl <http://localhost:8000/agents> curl <http://localhost:8000/health>
```

### Debug Commands

```bash

## Full system status

./scripts/deploy.sh --status

## Service dependency check

./scripts/health-check.sh --dependencies

## Resource utilization

top -b -n 1 | head -n 20
docker stats

```bash

## Security Considerations

- **Network Security**: Service mesh with mTLS encryption

- **Secret Management**: Systemd environment files, local vault, or external secret manager. Restrict environment files
  and use a secrets manager in production.

- **Access Control**: RBAC for Kubernetes and service-level auth

- **Image Security**: Container scanning and signed images

- **Compliance**: GDPR, SOC2 compliance configurations

## Performance Benchmarks

- **Startup Time**: <30 seconds for full system

- **Service Discovery**: <1 second for agent registration

- **Horizontal Scaling**: <60 seconds for pod scaling

- **Failover**: <10 seconds for service recovery

- **GPU Allocation**: <5 seconds for GPU resource assignment

## Migration Guide

### From Systemd to Kubernetes (DEPRECATED)

1. **Backup current configuration**

```
bash ./scripts/backup-config.sh
```

1. **Generate Kubernetes manifests (DEPRECATED)**

```bash
# This step is historical; use the systemd service templates instead.
# ./scripts/generate-k8s.sh

```

1. **Deploy to Kubernetes**

```
bash kubectl apply -k kubernetes/
```

1. **Verify migration**

```
bash ./scripts/health-check.sh --target kubernetes
```

1. **Remove systemd services**

```
bash sudo systemctl stop justnews-* sudo systemctl disable justnews-*
```

### From Docker Compose to Kubernetes

1. **Export current state**

```
bash docker-compose config > current-config.yml
```

1. **Generate Kubernetes manifests**

```bash
# Docker/Kubernetes conversion tools were used historically; these are deprecated. Use systemd unit templates instead.

```

1. **Apply Kubernetes manifests**

```
bash kubectl apply -f .
```

1. **Update ingress and services**

```
bash kubectl apply -f kubernetes/ingress.yml
```

## Contributing

1. **Add new services**: Update templates and manifests

1. **Modify configurations**: Use environment-specific overlays

1. **Test deployments**: Validate across all target platforms

1. **Update documentation**: Keep deployment guides current

## Support

For deployment issues:

1. Check service logs and health endpoints

1. Verify configuration and environment variables

1. Test network connectivity between services

1. Review resource allocation and scaling settings

1. Check platform-specific documentation (Docker, Kubernetes, systemd)
