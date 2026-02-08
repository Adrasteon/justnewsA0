## Dev setup — reproducible environment for live-run testing

This file outlines the minimal reproducible steps required to run a local dev stack for the JustNews live-run testing
flow. Use this on a development machine with Docker and the recommended conda environment.

### Quick Setup (Dev Container Recommended)

**For the fastest, most reliable setup, use VS Code's Dev Container feature:**

1. Open the project in VS Code
2. Install the "Dev Containers" extension
3. Press `F1` and select "Dev Containers: Reopen in Container"
4. Wait for initialization (auto-runs Python venv setup + Django migrations)
5. See [.devcontainer/README.md](.devcontainer/README.md) for details

The dev container **automatically:**
- Creates virtual environment using UV package manager  
- Installs all dependencies from `requirements-bootstrap.txt`
- Waits for MariaDB to be ready
- Runs Django migrations (with `--fake-initial` for existing schemas)
- Verifies service connectivity
- Collects static files

**Success indicator**: `[✓ SUCCESS] Dev Container Initialization Complete!`

### Manual Setup (Local Development)

#### Prerequisites

- Docker / docker-compose or equivalent
- git
- conda or mamba (recommended: Python 3.12 environment)
- UV package manager (optional but recommended): `pip install uv`

#### Create the Python environment

**Option 1: Using UV (Recommended)**

```bash
# Install UV if not already installed
pip install uv

# Create venv with UV and install dependencies
uv venv /path/to/venv
source /path/to/venv/bin/activate
uv pip install -r requirements-bootstrap.txt

# Install playwright browsers (if needed)
playwright install
```

**Option 2: Using Conda/Mamba**

```bash
# Create or update the conda env from repository environment.yml
mamba env create -f environment.yml -n ${CANONICAL_ENV:-justnews-py312} \
  || mamba env update -f environment.yml -n ${CANONICAL_ENV:-justnews-py312}

mamba activate ${CANONICAL_ENV:-justnews-py312}

# Install playwright browsers
playwright install
```

**Note:** The deprecated `requirements.txt` should not be used; use `requirements-bootstrap.txt` or `environment.yml` instead.

Build local MariaDB image (used for tests / local dev)

```bash
docker build -f scripts/dev/db-mariadb/Dockerfile -t justnews-mariadb:latest scripts/dev

```

Start a minimal local stack (db + redis) for smoke/e2e tests

```bash
docker-compose -f scripts/dev/docker-compose.e2e.yml up -d db redis

```bash

Verify local services

```bash

## DB check (mysql client may be required)

mysql -h 127.0.0.1 -P 13306 -u justnews -ptest -e "SELECT 1;"

## Redis check

redis-cli -h 127.0.0.1 -p 16379 PING

## Chroma can be started separately if needed using the official image

docker run --rm -p 8000:8000 chromadb/chroma:0.4.18

```

Running tests — smoke/unit

```bash

## Run a focused smoke test suite (fast)

pytest tests/smoke -q

## Run full test matrix (longer)

pytest -q

```

### Verify Environment Setup

Before running the full system, verify all dependencies are properly installed and services are accessible:

```bash

# Verify key packages
python -c "import fastapi, django, torch, pandas; print('✓ All core packages imported')"

# Test database connectivity
source global.env
python manage.py dbshell

# Check Django migrations  
python manage.py showmigrations --list

```

### Post-Create Initialization (Dev Container Only)

When using the dev container, the `postCreateCommand` automatically runs:

1. **Dependency Installation**: Creates `/deps/.venv` with UV
2. **Environment Loading**: Loads configuration from `global.env`
3. **Service Wait**: Waits up to 60 seconds for MariaDB readiness
4. **Django Setup**: Runs migrations with `--fake-initial`
5. **Static Files**: Collects Django static files

Check initialization status:

```bash
tail -50 /tmp/setup_complete_v*.log
```

If issues occur, initialization details are logged to `/tmp/migrate.log` (for Django) and `/tmp/setup_complete*.log` (for overall setup).

### Troubleshooting Environment Issues

If you run into environment issues the first place to check is `environment.yml` and the local compose file
`scripts/dev/docker-compose.e2e.yml`.
