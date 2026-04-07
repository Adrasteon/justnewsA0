# JustNews Service Lifecycle Wrappers (Docker-Canonical)

This document describes the canonical wrapper scripts:

- `./start_all_services.sh` → `bash scripts/ops/docker_compose.sh up`
- `./stop_all_services.sh` → `bash scripts/ops/docker_compose.sh down`

These wrappers are intentionally minimal and Docker-first.

## Usage

Start stack:

```bash
./start_all_services.sh
```

Stop stack:

```bash
./stop_all_services.sh
```

## Passing Docker Compose arguments

Both wrappers pass extra arguments through to the Docker compose wrapper.

Examples:

```bash
# Show service status
bash scripts/ops/docker_compose.sh status

# Tail logs
bash scripts/ops/docker_compose.sh logs

# Start specific services only
./start_all_services.sh mariadb redis

# Stop and remove volumes if required
./stop_all_services.sh -v
```

## Compose file selection

Default compose file:

- `infrastructure/docker/docker-compose.canonical.yml`

Override compose file for a command:

```bash
JUSTNEWS_COMPOSE_FILE=/path/to/compose.yml ./start_all_services.sh
```

## Preflight and validation

Recommended checks before startup:

```bash
make docker-preflight
make docker-migration-check
```

## Notes

- Active wrappers are strictly Docker-canonical and do not include legacy fallback toggles.
- Use Docker canonical commands for normal operations.
