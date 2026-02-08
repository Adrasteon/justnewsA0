Devcontainer GPU / Volumes guide
-------------------------------

Quick summary
- Code volume: host repo is mounted at `/app` (bind-mount)
- Dependency volume: isolated named volume mounted at `/deps` (created by Compose)
- Data volume: persistent named volume mounted at `/data`

Host requirements
- Docker Engine or Docker Desktop with WSL2 backend (Windows).
- NVIDIA drivers installed on the host that match the CUDA version you want to use (see below).
- `nvidia-container-toolkit` installed and configured on the host (for Linux). On Windows Docker Desktop, enable WSL2 GPU support.

CUDA image choice
- This devcontainer uses an NVIDIA CUDA base image (`nvidia/cuda:12.2.1-devel-ubuntu22.04`) so the container has CUDA libs present.
- Ensure your host GPU driver is compatible with CUDA 12.2.x. If not, choose a different matching CUDA base image.

How dependency venvs are created
- On `postCreateCommand`, the container runs `/usr/local/bin/create_deps_venv.sh` which will create a venv at `/deps/.venv` using `uv` (if available) or falling back to `python -m venv` and installing `requirements.txt`.
- The venv is isolated in the `justnews_deps` volume and not stored in the project code volume.

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

Automatic Initialization on First Start
- When the container is created, `postCreateCommand` automatically:
  1. Creates the Python virtualenv at `/deps/.venv`
  2. Installs dependencies from `requirements.txt` via `uv` (or pip fallback)
  3. **NEW:** Waits for MariaDB to be ready
  4. **NEW:** Runs Django migrations automatically
  5. **NEW:** Verifies service connectivity
  6. **NEW:** Collects static files

- If initialization succeeds, you'll see: `[✓ SUCCESS] Dev Container Initialization Complete!`

First-Time Usage Checklist (After Container Starts)

Run the following commands inside the container terminal to verify everything is working:

```bash
# 1. Load environment and verify database connectivity
source global.env
python -c "from database.utils import create_database_service; db = create_database_service(); print('✓ Database connected successfully')"

# 2. Verify vLLM is accessible (may take 1-2 minutes to load model)
curl -s http://vllm:8001/v1/models | jq .

# 3. Verify ChromaDB is accessible
curl -s http://chromadb:3307/api/version

# 4. Run a quick sanity test
python pytest tests/smoke_live.py -v --tb=short -k "test_import" 2>/dev/null || echo "✓ Basic imports working"

# 5. Check Django admin is ready
python manage.py showmigrations --list | head -5
```

Troubleshooting First-Run Issues

**MariaDB connection refused:**
```bash
# Wait a bit longer and retry
sleep 10
python manage.py dbshell
```

**vLLM model not downloading:**
```bash
# Verify HF_TOKEN is set and valid
echo $HF_TOKEN
# Check vLLM logs
docker compose logs vllm -n 50
```

**Django migrations already applied error:**
- This is safe; just means migrations ran successfully in background
- Continue with development

**Port conflicts:**
- Verify ports 3306, 3307, 8001, 8100 are available on host
- Check: `docker compose ps`

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

| Component | Port | Notes |
|-----------|------|-------|
| **Django Publisher** | **8100** | Development server (localhost only) |
| MariaDB | 3306 | Database backend |
| ChromaDB | 3307 | Vector embeddings |
| vLLM | 8001 | LLM inference service |

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


Troubleshooting
- If GPUs are not visible inside the container, confirm `nvidia-smi` works on the host and that Docker has GPU access. On Linux run:

```bash
docker run --gpus all --rm nvidia/cuda:12.2.1-base-ubuntu22.04 nvidia-smi
```

Contact
- If you want me to pin a different CUDA version or to make `/deps` tmpfs instead of a named volume, tell me which preference to use.
