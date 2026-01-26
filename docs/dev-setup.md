## Dev setup — reproducible environment for live-run testing

This file outlines the minimal reproducible steps required to run a local dev stack for the JustNews live-run testing
flow. Use this on a development machine with Docker and the recommended conda environment.

Prerequisites

- Docker / docker-compose or equivalent

- git

- conda or mamba (recommended: Python 3.12 environment)

Create the Python environment

```bash

# create or update the conda env from repository environment.yml

conda env create -f environment.yml -n ${CANONICAL_ENV:-justnews-py312} || conda env update -f environment.yml -n ${CANONICAL_ENV:-justnews-py312}
conda activate ${CANONICAL_ENV:-justnews-py312}

# Install playwright browsers
playwright install

## install dev extras if required

pip install -r requirements.txt || true

```bash

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

If you run into environment issues the first place to check is `environment.yml` and the local compose file
`scripts/dev/docker-compose.e2e.yml`.
