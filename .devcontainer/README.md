Devcontainer GPU / Volumes guide
-------------------------------

---

## 🔴 CRITICAL: Data Preservation on Rebuild (v2.0 - IDEMPOTENT)

**YOUR WORKFLOW DATA IS NOW PRESERVED WHEN YOU REBUILD!**

### ✅ What Changed:
- **Before**: All data deleted on rebuild ❌
- **Now**: Data volumes preserved automatically ✅

### 📌 When You Rebuild:
```bash
# Normal rebuild (PRESERVES data)
VSCode: Cmd/Ctrl + Shift + P → "Remote-Containers: Rebuild and Reopen"
# All articles, embeddings, analysis kept!

# Force clean rebuild (if needed)
bash .devcontainer/scripts/pre-build-cleanup.sh --force-clean
# Then rebuild normally
```

### 🛡️ What's Preserved:
- ✅ All articles ingested with crawlers
- ✅ All embeddings in ChromaDB
- ✅ All entity extraction analysis
- ✅ All sentiment/bias analyses
- ✅ Living stories and updates
- ✅ Task metadata and status
- ✅ Vector database collections

### 📖 Full Details:
See: [`DEVCONTAINER_IDEMPOTENCE_GUARANTEE.md`](../DEVCONTAINER_IDEMPOTENCE_GUARANTEE.md)

---

Quick summary
- Code volume: host repo is mounted at `/app` (bind-mount)
- Dependency volume: isolated named volume mounted at `/deps` (created by Compose)
- Data volume: persistent named volume mounted at `/data`
- **Database volumes**: Preserved across rebuilds (mariadb_data, chromadb_data)

Host requirements
- Docker Engine or Docker Desktop with WSL2 backend (Windows).
- NVIDIA drivers installed on the host that match the CUDA version you want to use (see below).
- `nvidia-container-toolkit` installed and configured on the host (for Linux). On Windows Docker Desktop, enable WSL2 GPU support.

CUDA image choice
- This devcontainer uses an NVIDIA CUDA base image (`nvidia/cuda:12.2.1-devel-ubuntu22.04`) so the container has CUDA libs present.
- Ensure your host GPU driver is compatible with CUDA 12.2.x. If not, choose a different matching CUDA base image.

How dependency venvs are created
- On `postCreateCommand`, the container runs `/usr/local/bin/create_deps_venv.sh` which will create a venv at `/deps/.venv` using **UV package manager** (`uv venv` + `uv pip install`).
- Dependencies are installed from `requirements-bootstrap.txt` (a curated, production-ready requirements file derived from `environment.yml`).
- If UV is not available, the script falls back to `python3 -m venv` + pip installation.
- The venv is isolated in the `justnews_deps` volume and not stored in the project code volume.
- **Note:** `requirements.txt` is deprecated and contains mostly historical comments; use `requirements-bootstrap.txt` or `environment.yml` instead.

GPU Support (Default)
- GPU is **enabled by default** in this devcontainer configuration.
- All services (app, chromadb, vllm) have GPU access via `gpus: all` in docker-compose.yaml.
- The system uses NVIDIA CUDA 12.2.1 for accelerated inference and processing.
- Verify GPU access with: `nvidia-smi` inside the container

Opt out to CPU-only mode (if needed)
- To force CPU-only behavior inside the devcontainer or when running scripts locally:

```bash
export DEV_CPU_ONLY=1
```

Or set `FORCE_CPU=1`. Use CPU-only mode **only for testing/debugging** on systems without GPU support, as performance will be significantly degraded.

Rebuild / open devcontainer
- In VS Code: Command Palette → Remote-Containers: Rebuild and Reopen in Container.
- You may need to install NVIDIA/WSL GPU support on Windows before GPU access is available.
- **Note**: Your workflow data will be preserved! See "Data Preservation" section above.

Automatic Initialization on First Start
- When the container is created, `postCreateCommand` automatically runs two scripts:

  **1. `/usr/local/bin/create_deps_venv.sh`** — Dependency Installation
  - Creates Python virtualenv at `/deps/.venv` using UV
  - Installs 100+ packages from `requirements-bootstrap.txt`
  - Includes: FastAPI, Django, PyTorch, Transformers, Pandas, SQLAlchemy, etc.

  
  **2. `/usr/local/bin/post-create.sh`** — Post-Create Initialization
  - Loads environment from `global.env` (with proper line endings)
  - Waits up to 60 seconds for MariaDB to be ready (using Python socket checks)
  - Runs Django migrations with `--fake-initial` flag (handles pre-existing schema)
  - Verifies ChromaDB and vLLM connectivity (with INFO level warnings if still loading)
  - Collects Django static files

- **Success Indicator:** If initialization completes, you'll see:
  ```
  [✓ SUCCESS] Dev Container Initialization Complete!
  ✓ Static files collected
  ```
- **Warning Level:** If MariaDB/services aren't ready during init, you'll see warnings (they may still be loading).
- **Troubleshooting:** Check `/tmp/setup_complete_v*.log` for detailed initialization output.

First-Time Usage Checklist (After Container Starts)

Run the following commands inside the container terminal to verify everything is working:

```bash
# 0. Activate the virtual environment
source /deps/.venv/bin/activate

# 1. Verify environment configuration is loaded
source global.env
echo "✓ MARIADB_HOST=$MARIADB_HOST, MARIADB_DB=$MARIADB_DB"

# 2. Verify all key dependencies
python -c "import fastapi, django, torch, pandas; print('✓ All core packages imported')"

# 3. Check database connectivity
/deps/.venv/bin/python -c "
import os
os.environ.update({'MARIADB_HOST': 'mariadb', 'MARIADB_DB': 'justnews', 'MARIADB_USER': 'justnews', 'MARIADB_PASSWORD': 'dev_justnews_password'})
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'justnews_publisher.settings')
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute('SELECT 1')
print('✓ Database connected successfully')
"

# 4. Verify vLLM is accessible (may take 1-2 minutes to load model)
curl -s http://vllm:8001/v1/models | python -m json.tool | head -10 && echo "✓ vLLM accessible"

# 5. Verify ChromaDB is accessible (pinned to v0.4.18 for stability)
curl -s http://chromadb:3307/api/v1/heartbeat && echo "✓ ChromaDB accessible"

# 6. Check Django migrations
/deps/.venv/bin/python manage.py showmigrations --list 2>/dev/null | head -10 && echo "✓ Django migrations available"
```

Troubleshooting First-Run Issues

**MariaDB connection refused even after 60 seconds:**
```bash
# MariaDB container may still be initializing
sleep 20
source global.env
/deps/.venv/bin/python manage.py dbshell
```

**Django migration errors ("Table already exists"):**
- This is expected if database schema already exists
- The init script uses `--fake-initial` to handle this gracefully
- If migrations fail, check: `/tmp/migrate.log`
- Manual recovery: `/deps/.venv/bin/python manage.py migrate --run-syncdb`

**Module not found (e.g., "No module named 'justnews_publisher'"):**
- Ensure `/app` is in PYTHONPATH
- Activate venv: `source /deps/.venv/bin/activate`
- Check: `python -c "import sys; print(sys.path)"`

**vLLM model not downloading:**
```bash
# Verify HF_TOKEN is set and valid
echo $HF_TOKEN
# Check vLLM logs (model may take 1-2 min to load)
docker compose logs vllm -n 100
```

**ChromaDB not responding:**
- ChromaDB is pinned to **v0.4.18** for API stability
- Verify health endpoint: `curl -s http://chromadb:3307/api/v1/heartbeat`
- Check logs: `docker compose logs chromadb -n 100`
- If you see 404 errors, the container may be running `latest` image with breaking API changes
- Update docker-compose.yaml to use image: `chromadb/chroma:0.4.18`

**Line ending issues (CRLF vs LF):**
- The init script now handles this automatically
- If you edit `global.env` on Windows, it may introduce CRLF line endings
- Fix: `sed -i 's/\r$//' /app/global.env`

**Port conflicts:**
- Verify ports 3306, 3307, 8001, 8100 are available on host
- Check: `docker compose ps`
- Kill conflicting processes or adjust port mappings in `docker-compose.yaml`

---

## Django Publisher Website (Development)

The JustNews Publisher creates and maintains the public-facing news website. You can run it locally during development.

### Quick Start: Run the Publisher

From inside the container terminal, run:

```bash
run-publisher.sh
```

Or manually:

```bash
python manage.py runserver 0.0.0.0:8100
```

**Access the website:**
- Home page: http://localhost:8100/
- Article archive: http://localhost:8100/archive/
- By category: http://localhost:8100/world/ (or uk, tech, business, etc.)
- Admin panel: http://localhost:8100/admin/
- Article submission API: http://localhost:8100/api/publish/ (POST)

### Port Information

| Component | Port | Status | Notes |
|-----------|------|--------|-------|
| **Django Publisher** | **8100** | ✓ Development | Development server (localhost only) |
| MariaDB | 3306 | ✓ Production | Database backend (20+ GB support) |
| ChromaDB | 3307 | ✓ Stable | Vector embeddings (**v0.4.18**) |
| vLLM | 8001 | ✓ Production-Ready | LLM inference (Qwen 2.5 14B) |

### Database Initialization

The first-run `postCreateCommand` automatically runs Django migrations. If you need to manually initialize:

```bash
python manage.py migrate
python manage.py createsuperuser  # Create admin account
```

### Publishing Articles

The website accepts articles via REST API from the editorial harness:

```bash
curl -X POST http://localhost:8100/api/publish/ \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Breaking News",
    "slug": "breaking-news",
    "summary": "Article summary",
    "body": "Full article content",
    "author": "Editorial System",
    "score": 0.95,
    "category": "world",
    "is_featured": true
  }'
```

### Accessing Django Admin

1. Create superuser (if not already created):
   ```bash
   python manage.py createsuperuser
   ```

2. Navigate to: http://localhost:8100/admin/

3. Login with superuser credentials

4. Manage articles, publishing audit logs, and site configuration


Environment Variables & Configuration

- **global.env**: Main configuration file (loaded by post-create script)
  - Ensure Unix line endings (LF), not Windows (CRLF)
  - Contains: `MARIADB_HOST`, `MARIADB_DB`, `MARIADB_USER`, `MARIADB_PASSWORD`, etc.
  - Example: See `global.env.sample` for template

- **requirements-bootstrap.txt**: Python dependencies (primary source, derived from `environment.yml`)
  - Updated via UV during venv creation
  - Contains all production and development packages
  - Do NOT use deprecated `requirements.txt`

- **environment.yml**: Conda specification (reference; conda not used in devcontainer)
  - Defines complete Python 3.10 environment
  - Used to generate `requirements-bootstrap.txt`

Debugging & Logging

- **Setup logs**: Check `/tmp/setup_complete_v*.log` for initialization details
- **Django migrations**: Check `/tmp/migrate.log` for schema errors
- **Service logs**: Use `docker compose logs <service>` to view container output
  - Example: `docker compose logs mariadb -n 50`

GPU Support

- If GPUs are not visible inside the container, confirm `nvidia-smi` works on the host and that Docker has GPU access. On Linux run:

```bash
docker run --gpus all --rm nvidia/cuda:12.2.1-base-ubuntu22.04 nvidia-smi
```

Key Improvements (Feb 2026)

- ✓ Fixed CRLF line ending issues in global.env
- ✓ Upgraded to UV for faster, more reliable dependency installation
- ✓ Switched from deprecated `requirements.txt` to `requirements-bootstrap.txt`
- ✓ Replaced shell `nc` checks with Python socket connections (more reliable)
- ✓ Improved environment variable handling with `source` instead of grep/export
- ✓ Added `--fake-initial` migration flag for pre-existing schemas
- ✓ Extended MariaDB wait timeout to 60 seconds
- ✓ Separated dependency installation from Django initialization
- ✓ Added detailed initialization success/warning reporting
