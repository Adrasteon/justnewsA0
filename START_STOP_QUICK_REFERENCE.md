# JustNews Service Startup/Shutdown - Quick Reference

Canonical lifecycle wrappers:
- `./start_all_services.sh` → Docker compose up
- `./stop_all_services.sh` → Docker compose down

## TL;DR

```bash
# Start canonical stack
./start_all_services.sh

# Stop canonical stack
./stop_all_services.sh

# Check status
bash scripts/ops/docker_compose.sh status

# Follow logs
bash scripts/ops/docker_compose.sh logs
```

## Canonical commands

```bash
make docker-preflight
make docker-migration-check
make deploy-docker
make deploy-docker-status
make deploy-docker-logs
make deploy-docker-stop
```

## Compose override

```bash
JUSTNEWS_COMPOSE_FILE=/path/to/compose.yml ./start_all_services.sh
```

## Important

Legacy wrapper toggle behavior has been removed from active wrapper scripts.
Use Docker canonical commands and compose wrapper pathways for lifecycle operations.
