# Root Legacy Script Redirect Index

This index maps retired root-level helper scripts to their canonical Docker-first replacements.

Purpose
- Preserve operator continuity after root-level script cleanup.
- Provide a single source of truth for replacement commands.
- Prevent drift back to legacy orchestration paths.

Canonical policy
- Runtime orchestration is Docker-first.
- Use scripts/ops/docker_compose.sh (directly or via approved wrappers).
- Do not reintroduce root-level service orchestration scripts.

## Redirect map

### Service lifecycle
- `./start_all_services.sh` -> `bash scripts/ops/docker_compose.sh up`
- `./stop_all_services.sh` -> `bash scripts/ops/docker_compose.sh down`
- `make deploy-development` -> `make deploy-docker`
- `make deploy-staging` -> `make deploy-docker`
- `make deploy-production` -> `make deploy-docker`

### Status and logs
- Legacy ad-hoc status checks -> `bash scripts/ops/docker_compose.sh status`
- Legacy ad-hoc tail commands -> `bash scripts/ops/docker_compose.sh logs`

## Operator quick commands
- Start: `make deploy-docker`
- Stop: `make deploy-docker-stop`
- Status: `make deploy-docker-status`
- Logs: `make deploy-docker-logs`
- Migration/compliance check: `make docker-migration-check`

## Notes
- This file is referenced by docs/DOCUMENTATION_INDEX.md and should remain stable.
- If workflows change, update this file and the operations docs in the same change.
