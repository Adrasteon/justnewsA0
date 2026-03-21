# JustNews Script Ecosystem

This directory contains the organized script ecosystem for JustNews operations, maintenance, and development.

## Directory Structure

```text
scripts/
├── admin/           # Administrative scripts (secrets, user management)
├── deploy/          # Deployment and infrastructure setup scripts
├── dev/             # Development environment and tooling scripts
├── maintenance/     # System maintenance and monitoring scripts
├── ops/             # Operational scripts (service management, model handling)
├── perf/            # Performance testing and telemetry
├── archive/         # Archived legacy scripts (for reference only)
└── common/          # Shared utilities and frameworks
```

## Categories

### admin/

Scripts for administrative tasks and system configuration.

- `manage_secrets.py` - Manage application secrets and credentials

### deploy/

Scripts for deployment, database setup, and infrastructure provisioning.

- `setup_mariadb.sh` - MariaDB installation and configuration

- `init_database.py` - Database schema initialization and user setup

### dev/

Scripts for development environment setup and tooling.

- `setup_dev_environment.sh` - Development environment configuration

### maintenance/

Scripts for system maintenance, monitoring, and health checks.

- `validate_versions.py` - Version validation and compliance checking

### ops/

Scripts for operational tasks and service management.

- `start_services_daemon.sh` - Start all JustNews services

- `stop_services.sh` - Stop all JustNews services

- `download_agent_models.py` - Download and setup AI models

### common/

Shared utilities and frameworks used by all scripts.

- `script_framework.py` - Common script framework with logging, error handling, and configuration

## Usage

All scripts follow consistent patterns:

### Python Scripts

```bash
## Basic usage
python scripts/ops/download_agent_models.py

## With options
python scripts/ops/download_agent_models.py --verbose --log-level DEBUG

## Dry run mode (where supported)
python scripts/deploy/init_database.py --dry-run
```

### Shell Scripts

```bash
## Basic usage
./scripts/dev/setup_dev_environment.sh

## With options (varies by script)
./scripts/ops/start_services_daemon.sh --help

## Roo Code workspace indexing helper (Qdrant)

```bash
## Start and health-check Roo indexing backend
bash scripts/roo_qdrant.sh start

## Show backend status
bash scripts/roo_qdrant.sh status

## Stop backend
bash scripts/roo_qdrant.sh stop
```

## Roo Code indexing preflight verifier

```bash
## Validate LM Studio models + embeddings and Qdrant health from dev-container
bash scripts/verify_roo_index_setup.sh

## Override URLs or model IDs if needed
LM_BASE_URL=http://host.docker.internal:1234/v1 \
QDRANT_URL=http://host.docker.internal:6333 \
CHAT_MODEL_ID=google/gemma-3-12b \
EMBED_MODEL_ID=text-embedding-nomic-embed-text-v1.5 \
bash scripts/verify_roo_index_setup.sh
```

## Common Options

All Python scripts support these standard options:

- `--log-level {DEBUG,INFO,WARNING,ERROR}` - Set logging verbosity

- `--log-file FILE` - Log to file in addition to console

- `--dry-run` - Show what would be done without making changes

- `--verbose/-v` - Enable verbose output

- `--quiet/-q` - Suppress non-error output

## Environment Variables

Scripts use these common environment variables:

- `MYSQL_HOST`,`MYSQL_DATABASE`,`MYSQL_USER`,`MYSQL_PASSWORD` - MariaDB configuration

- `CHROMA_HOST`,`CHROMA_PORT` - ChromaDB configuration

- `MODEL_STORE_ROOT` - Model storage directory

- `BASE_MODEL_DIR` - Agent model cache directory

- `CONDA_DEFAULT_ENV` - Conda environment name

## Error Handling

All scripts include comprehensive error handling:

- Standardized logging with timestamps and levels

- Graceful failure with informative error messages

- Environment validation before execution

- Keyboard interrupt handling (Ctrl+C)

## Development Guidelines

When adding new scripts:

1. **Categorize properly** - Place scripts in the appropriate category directory

1. **Use the framework** - Python scripts should use `ScriptFramework`from`common/script_framework.py`

1. **Document thoroughly** - Include docstrings and usage examples

1. **Handle errors** - Implement proper error handling and logging

1. **Test scripts** - Add automated tests for critical functionality

1. **Follow conventions** - Use consistent naming and option patterns

## Migration Notes

This organized structure replaces the previous flat `scripts/` directory. Legacy scripts have been:

- **Moved**: Essential scripts moved to appropriate categories

- **Archived**: Obsolete/experimental scripts moved to `archive/`

- **Removed**: Duplicate or undocumented scripts removed entirely

For legacy script references, check the `archive/` directory or git history.
