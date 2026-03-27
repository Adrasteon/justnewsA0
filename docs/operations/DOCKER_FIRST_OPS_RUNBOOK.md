---
title: Docker-First Operations Runbook
description: Operational runbook for Docker canonical runtime with optional systemd host wrappers
---

# Docker-First Operations Runbook

## Canonical lifecycle commands

Use Make targets:

- Start: `make deploy-docker`
- Stop: `make deploy-docker-stop`
- Status: `make deploy-docker-status`
- Logs: `make deploy-docker-logs`

Or direct wrapper:

- `bash scripts/ops/docker_compose.sh up`
- `bash scripts/ops/docker_compose.sh down`
- `bash scripts/ops/docker_compose.sh status`
- `bash scripts/ops/docker_compose.sh logs`

## Compose file selection

Default compose file:
- `infrastructure/docker/docker-compose.canonical.yml`

Override with env:
- `JUSTNEWS_COMPOSE_FILE=/path/to/compose.yml bash scripts/ops/docker_compose.sh up`

## Systemd role during transition

- systemd app-orchestration scripts are legacy compatibility paths.
- systemd may still be used for host-level wrappers only (optional), such as:
  - auto-starting Docker Compose at boot,
  - host monitoring/alerting units.
- Example host wrapper unit:
  - `infrastructure/systemd/units/justnews-docker-compose.service.example`

## Incident response quick checklist

1. `make deploy-docker-status`
2. `make deploy-docker-logs`
3. `make docker-migration-check`
4. verify database/vector/cache container health
5. restart stack if needed:
   - `make deploy-docker-stop`
   - `make deploy-docker`

## Rollback

If Docker path fails during transition:
- revert to previous known-good compose file or image tags,
- use legacy systemd app path only as temporary fallback,
- capture failure logs and update compose health/dependency configuration.
