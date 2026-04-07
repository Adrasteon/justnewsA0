---
title: Docker Canonical Commands
description: One-page operator command reference for Docker-first JustNews runtime
---

# Docker Canonical Commands

## Core lifecycle

- Preflight: `make docker-preflight`
- Compliance report: `make docker-migration-check`
- Start stack: `make deploy-docker`
- Stop stack: `make deploy-docker-stop`
- Status: `make deploy-docker-status`
- Logs: `make deploy-docker-logs`

## Wrapper equivalents

- `bash scripts/ops/docker_compose.sh up`
- `bash scripts/ops/docker_compose.sh down`
- `bash scripts/ops/docker_compose.sh status`
- `bash scripts/ops/docker_compose.sh logs`

## Compose file selection

Default:
- `infrastructure/docker/docker-compose.canonical.yml`

Override:
- `JUSTNEWS_COMPOSE_FILE=/path/to/compose.yml bash scripts/ops/docker_compose.sh up`

## Canonical lifecycle wrappers

- `./start_all_services.sh` -> Docker up
- `./stop_all_services.sh` -> Docker down

Wrappers are intentionally minimal and always Docker-canonical.

## Quick incident flow

1. `make deploy-docker-status`
2. `make deploy-docker-logs`
3. `make docker-migration-check`
4. restart if needed:
   - `make deploy-docker-stop`
   - `make deploy-docker`
