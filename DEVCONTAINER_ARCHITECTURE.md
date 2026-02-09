# DevContainer Architecture Diagram

```
┌───────────────────────────────────────────────────────────────────────────┐
│                    VS CODE REMOTE DEVCONTAINER                           │
│                      (Running on Docker Engine)                           │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ APP CONTAINER (JustNews Development)                           │   │
│  │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │   │
│  │                                                               │   │
│  │ Base Image: nvidia/cuda:12.4.1-devel-ubuntu22.04             │   │
│  │ Python: 3.12                                                 │   │
│  │ CUDA: 12.4.1                                                 │   │
│  │                                                               │   │
│  │ ┌────────────────────────────────────────────────────────┐  │   │
│  │ │ Entrypoint: /usr/local/bin/entrypoint.sh              │  │   │
│  │ │   └─ Activates /deps/.venv virtualenv                 │  │   │
│  │ └────────────────────────────────────────────────────────┘  │   │
│  │                                                               │   │
│  │ ┌────────────────────────────────────────────────────────┐  │   │
│  │ │ Post-Create Command: create_deps_venv.sh              │  │   │
│  │ │   1. Create virtualenv at /deps/.venv                 │  │   │
│  │ │   2. Install 100+ packages from requirements-*.txt     │  │   │
│  │ │   3. Chain to post-create.sh initialization:          │  │   │
│  │ │      ├─ Load global.env configuration                 │  │   │
│  │ │      ├─ Wait for MariaDB (60s timeout)                │  │   │
│  │ │      ├─ Run Django migrations (--fake-initial)         │  │   │
│  │ │      ├─ Verify ChromaDB connectivity                  │  │   │
│  │ │      ├─ Verify vLLM connectivity                      │  │   │
│  │ │      └─ Collect static files                          │  │   │
│  │ └────────────────────────────────────────────────────────┘  │   │
│  │                                                               │   │
│  │ Volumes Mounted:                                             │   │
│  │ • /app → host code (bind mount, cached)                    │   │
│  │ • /deps → dependency venv (named volume)                  │   │
│  │ • /data → persistent data (named volume)                  │   │
│  │                                                               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Port Forwarding (from Host)                                │  │
│  │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │  │
│  │                                                             │  │
│  │ 3306 (Host) ──bind──> 3306 (MariaDB service)              │  │
│  │ 3307 (Host) ──bind──> 8000 (ChromaDB service)             │  │
│  │ 8001 (Host) ──bind──> 8000 (vLLM service)                 │  │
│  │ 8100 (Host) ──bind──> 8100 (Django Publisher)             │  │
│  │                                                             │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└───────────────────────────────────────────────────────────────────────────┘
                            ↓ depends_on
                    (Docker Compose)
        ┌───────────────────┬──────────────────┬──────────────────┐
        │                   │                  │                  │
        ▼                   ▼                  ▼                  ▼
    ┌────────────┐   ┌────────────┐   ┌─────────────┐   ┌────────────┐
    │  MariaDB   │   │  ChromaDB  │   │   vLLM      │   │ (Optional) │
    │  Database  │   │   Vector   │   │ Inference   │   │ Services   │
    │            │   │   Store    │   │             │   │            │
    ├────────────┤   ├────────────┤   ├─────────────┤   ├────────────┤
    │ Port: 3306 │   │ Port: 3307 │   │ Port: 8001  │   │Port: Varies│
    │            │   │            │   │             │   │            │
    │ Image:     │   │ Image:     │   │ Image:      │   │Image:      │
    │ mariadb    │   │ chromadb   │   │ vllm/       │   │ redis,     │
    │ :latest    │   │ :0.4.18    │   │ vllm-openai │   │prometheus, │
    │            │   │            │   │ :latest     │   │ grafana... │
    │ Persistent │   │ Ephemeral  │   │ ~14GB Model │   │            │
    │ (mariadb   │   │ by default │   │ Cache       │   │Not in      │
    │ _data vol) │   │            │   │ (host fs)   │   │docker-     │
    │            │   │ Stable API │   │ 5-10 min    │   │compose     │
    │ MariaDB    │   │ (v0.4.18)  │   │ 1st startup │   │            │
    │ init time: │   │ Startup:   │   │ 30-60s      │   │(Optional:  │
    │ 15-30sec   │   │ 2-5sec     │   │ 2nd+        │   │add to      │
    │            │   │            │   │             │   │compose if  │
    │ Connection │   │ HTTP API:  │   │ HTTP API:   │   │testing     │
    │ check:     │   │ /api/v1/   │   │ /v1/models, │   │full stack) │
    │ Python     │   │ heartbeat  │   │ /v1/        │   │            │
    │ socket     │   │            │   │ completions │   │            │
    │            │   │ Health:    │   │             │   │            │
    │ Status:    │   │ OK         │   │ Health:     │   │Status:     │
    │ ✅ Working│   │ Status: ✅ │   │ OK          │   │Not Set Up  │
    │            │   │ Working    │   │ Status: ✅  │   │            │
    │            │   │            │   │ Working (but│   │            │
    │            │   │            │   │ slow 1st    │   │            │
    │            │   │            │   │ start)      │   │            │
    └────────────┘   └────────────┘   └─────────────┘   └────────────┘
        ↑                   ↑                  ↑
        │                   │                  │
        └───────────────────┴──────────────────┘
                     │
            Connected Inside Container
            (via docker-compose network)
                     │
         ┌───────────┴───────────┐
         │                       │
    MariaDB:3306           ChromaDB:3307
    (internal)             (internal)
    vLLM:8001
    (internal)
```

---

## Initialization Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. VS CODE → Open Remote in Container (devcontainer.json)          │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. Docker Compose Up                                                │
│    - Start mariadb (15-30 sec init)                                 │
│    - Start chromadb (2-5 sec init)                                  │
│    - Start vllm (2-5 min on first run for model download)           │
│    - Start app container (depends_on: vllm)                         │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. App Container Command: sleep infinity                            │
│    + Entrypoint: /usr/local/bin/entrypoint.sh                       │
│      └─ Activates /deps/.venv virtualenv                            │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. postCreateCommand: /usr/local/bin/create_deps_venv.sh            │
│    ┌─────────────────────────────────────────────────────────────┐  │
│    │ Step 1: Create virtualenv                                   │  │
│    │   mkdir -p /deps                                            │  │
│    │   uv venv /deps/.venv  (or python3 -m venv fallback)        │  │
│    │ Status: ✓ Takes ~10-30 seconds                              │  │
│    └─────────────────────────────────────────────────────────────┘  │
│    ┌─────────────────────────────────────────────────────────────┐  │
│    │ Step 2: Install dependencies                                │  │
│    │   uv pip install -r requirements-bootstrap.txt              │  │
│    │   [100+ packages: fastapi, django, torch, pandas, etc.]    │  │
│    │ Status: ✓ Takes ~1-2 minutes                                │  │
│    └─────────────────────────────────────────────────────────────┘  │
│    ┌─────────────────────────────────────────────────────────────┐  │
│    │ Step 3: Fix CRLF line endings                               │  │
│    │   sed -i 's/\r$//' /app/global.env                          │  │
│    │ Status: ✓ Takes <1 second                                   │  │
│    └─────────────────────────────────────────────────────────────┘  │
│    ┌─────────────────────────────────────────────────────────────┐  │
│    │ Step 4: Chain to post-create.sh                             │  │
│    │   /usr/local/bin/post-create.sh                             │  │
│    └─────────────────────────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. Post-Create Initialization Script                                │
│    ┌─────────────────────────────────────────────────────────────┐  │
│    │ Step 1: Load Configuration                                  │  │
│    │   source /app/global.env                                    │  │
│    │ Status: ✓ Takes <1 second                                   │  │
│    └─────────────────────────────────────────────────────────────┘  │
│    ┌─────────────────────────────────────────────────────────────┐  │
│    │ Step 2: Wait for MariaDB Readiness 🟡 BLOCKING              │  │
│    │   Loop: Python socket connection attempt to mariadb:3306    │  │
│    │   Timeout: 60 seconds (max 60 retries with 1s backoff)      │  │
│    │ Status: ✓ Takes 1-30 seconds (depending on init speed)      │  │
│    │ Issue: If MariaDB doesn't start, blocks initialization      │  │
│    └─────────────────────────────────────────────────────────────┘  │
│    ┌─────────────────────────────────────────────────────────────┐  │
│    │ Step 3: Run Django Migrations 🟡 BLOCKING                   │  │
│    │   python manage.py migrate --fake-initial --noinput        │  │
│    │ Status: ✓ Takes 10-20 seconds                               │  │
│    │ Issue: If database unreachable, fails                       │  │
│    └─────────────────────────────────────────────────────────────┘  │
│    ┌─────────────────────────────────────────────────────────────┐  │
│    │ Step 4: Verify Service Connectivity (Non-blocking)          │  │
│    │   - ChromaDB socket check (port 3307)                       │  │
│    │   - vLLM socket check (port 8001)                           │  │
│    │ Status: ⚠️ Warnings only (services may still be loading)    │  │
│    │ Issue: vLLM model download takes 5-10 minutes (first time)  │  │
│    └─────────────────────────────────────────────────────────────┘  │
│    ┌─────────────────────────────────────────────────────────────┐  │
│    │ Step 5: Collect Static Files 🟡 BLOCKING                    │  │
│    │   python manage.py collectstatic --noinput                 │  │
│    │ Status: ✓ Takes 5-10 seconds                                │  │
│    │ Issue: If Django settings not loaded, fails                 │  │
│    └─────────────────────────────────────────────────────────────┘  │
│    ┌─────────────────────────────────────────────────────────────┐  │
│    │ Step 6: Display Status Summary                              │  │
│    │   [✓ SUCCESS] Dev Container Initialization Complete!        │  │
│    │   (or [⚠ WARNING] with count of failures)                   │  │
│    │ Status: ✓ Takes <1 second                                   │  │
│    └─────────────────────────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 6. User Gets Shell Prompt                                           │
│    Total Time: ~2-3 minutes (on system with GPU + good network)     │
│                                                                     │
│    Services Status:                                                 │
│    ✓ MariaDB: Ready (can execute queries immediately)              │
│    ✓ Django: Ready (migrations applied, static files collected)    │
│    ✓ ChromaDB: Ready (HTTP API operational)                        │
│    ⚠️ vLLM: May still be loading model (ongoing async)             │
│                                                                     │
│    Next Steps Available:                                            │
│    - Run Python in REPL: python                                     │
│    - Execute Django shell: python manage.py shell                  │
│    - Test database: curl http://localhost:3306 ...                 │
│    - Test vLLM: curl http://vllm:8001/v1/models                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Port Mapping Reference

```
┌─────────────────────────────────────────────────────────────────────┐
│ FORWARDED PORTS (accessible from host)                              │
├─────────────┬──────────────┬──────────────┬─────────────────────────┤
│ Host Port   │ → Container  │ Service      │ Purpose                 │
├─────────────┼──────────────┼──────────────┼─────────────────────────┤
│ 3306        │ → 3306       │ MariaDB      │ Database connections    │
│ 3307        │ → 8000       │ ChromaDB     │ Vector DB API           │
│ 8001        │ → 8000       │ vLLM         │ LLM inference API       │
│ 8100        │ → 8100       │ Django       │ Publisher website dev   │
└─────────────┴──────────────┴──────────────┴─────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ INTERNAL NETWORK (accessible only from within containers)           │
├─────────────┬──────────────┬──────────────┬─────────────────────────┤
│ Service     │ Container    │ Port         │ From App Container      │
├─────────────┼──────────────┼──────────────┼─────────────────────────┤
│ MariaDB     │ mariadb      │ 3306         │ mariadb:3306            │
│ ChromaDB    │ chromadb     │ 3307         │ chromadb:3307           │
│ vLLM        │ vllm         │ 8001         │ vllm:8001               │
└─────────────┴──────────────┴──────────────┴─────────────────────────┘

⚠️ NOTE: Agent services (8000-8020) are NOT in docker-compose
   They must be run manually if needed for testing
   Example: CHIEF_EDITOR_AGENT_PORT=8001 python -m agents.chief_editor.main
```

---

## Issue Location Map

```
┌─────────────────────────────────────────────────────────────────────┐
│ IDENTIFIED ISSUES & WHERE TO FIX                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ 🔴 CRITICAL: Journalist Port Conflict                              │
│   Location: agents/journalist/main.py:97                           │
│   Status: HARDCODED port=8016                                      │
│   Fix: Use environment variable → port=int(os.environ.get(...))    │
│   Impact: Journalist agent cannot start with Crawler Control       │
│                                                                     │
│ 🟡 MEDIUM: Missing Agent Port Env Vars                             │
│   Location: global.env (missing 18+ variables)                     │
│   Status: Incomplete                                               │
│   Fix: Add section with MCP_BUS_PORT, CHIEF_EDITOR_AGENT_PORT...   │
│   Impact: Cannot start agents with consistent config               │
│                                                                     │
│ 🟡 LOW: HITL Service Naming Inconsistency                          │
│   Location: agents/hitl_service/main.py:30, app.py:31             │
│   Status: Dual naming (HITL_SERVICE_PORT + HITL_PORT legacy)       │
│   Fix: Standardize on HITL_SERVICE_PORT=8019                       │
│   Impact: Configuration confusion only                             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

