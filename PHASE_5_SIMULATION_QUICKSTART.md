# Phase 5: Deployment Simulation - Quick Start Guide

## TL;DR - Get Running in 5 Minutes

```bash
# 1. Make sure you're in the app directory
cd /app

# 2. Run the automated simulation (default settings)
bash run_deployment_simulation.sh

# That's it! The script will:
# ✓ Verify all services (MariaDB, ChromaDB, vLLM)
# ✓ Run migrations
# ✓ Populate test data
# ✓ Start the application
# ✓ Run integration tests
# ✓ Display results
```

---

## What Was Created

### 1. **DEPLOYMENT_SIMULATION_GUIDE.md** (16KB)
Complete step-by-step guide covering 9 phases:
- Database initialization & seeding
- Service configuration
- Application deployment
- Training system initialization
- Integration testing
- Monitoring & metrics
- Disaster recovery testing
- Cleanup & documentation

**Use this when:** You want detailed procedures for each step

---

### 2. **populate_database.py** (15KB, executable)
Automated Python script to seed test data:
- Creates users (default: 5)
- Creates news sources (default: 10)
- Generates documents (default: 50)
- Creates embeddings (default: 100)
- Initializes training jobs (default: 3)

**Usage:**
```bash
# Default (5 users, 10 sources, 50 docs, 100 embeddings, 3 jobs)
python populate_database.py

# Custom with verbose output
python populate_database.py --users 10 --sources 20 --documents 100 --verbose

# Full mode (maximum data)
python populate_database.py --full --verbose
```

**Use this when:** You need to quickly populate the database with test data

---

### 3. **run_deployment_simulation.sh** (9KB, executable)  
Bash orchestration script that automates everything:

**Usage:**
```bash
# Standard mode (recommended first run)
bash run_deployment_simulation.sh

# Quick mode (fast testing with reduced data)
bash run_deployment_simulation.sh --quick

# Full mode (comprehensive testing with max data)
bash run_deployment_simulation.sh --full

# Skip integration tests
bash run_deployment_simulation.sh --skip-tests

# Verbose output
bash run_deployment_simulation.sh --verbose

# Get help
bash run_deployment_simulation.sh --help
```

**What it does:**
1. ✓ Verifies Docker services (MariaDB, ChromaDB, vLLM)
2. ✓ Runs database migrations
3. ✓ Populates test data using populate_database.py
4. ✓ Starts Django development server
5. ✓ Verifies application health
6. ✓ Runs integration tests (optional)
7. ✓ Generates summary report

**Output Files:**
- `deployment-simulation/simulation_*.log` - Full simulation log
- `deployment-simulation/app.log` - Application output

**Use this when:** You want automated end-to-end testing

---

## Common Workflows

### Workflow 1: Quick Test (5 min)
Perfect for rapid iteration:
```bash
bash run_deployment_simulation.sh --quick
```
Creates small dataset, tests all services, skips heavy testing.

### Workflow 2: Full Validation (30 min)
Complete testing before production consideration:
```bash
bash run_deployment_simulation.sh --full
```
Large dataset, all integration tests, comprehensive validation.

### Workflow 3: Data Population Only (2 min)
Just populate the database:
```bash
python populate_database.py --users 20 --documents 200 --verbose
```

### Workflow 4: Manual Testing (15 min)
Run steps individually for detailed inspection:

```bash
# Step 1: Start services (if not running)
docker-compose -f .devcontainer/docker-compose.yaml up -d

# Step 2: Run migrations
python manage.py migrate

# Step 3: Populate data with options
python populate_database.py --users 5 --sources 10 --documents 50 --verbose

# Step 4: Start app
python manage.py runserver 0.0.0.0:8000

# Step 5: In another terminal - run tests
pytest tests/integration/ -v

# Step 6: Verify
curl -s http://localhost:8000/health | jq .
```

---

## Verification Checklist

After running simulation, verify:

```bash
# Check database connection
mysql -h mariadb -u justnews -pjustnews_password justnews -e "SELECT COUNT(*) as 'Total Tables' FROM information_schema.TABLES WHERE TABLE_SCHEMA='justnews';"

# Check documents ingested
mysql -h mariadb -u justnews -pjustnews_password justnews -e "SELECT COUNT(*) as 'Total Documents' FROM documents;"

# Check embeddings created
mysql -h mariadb -u justnews -pjustnews_password justnews -e "SELECT COUNT(*) as 'Total Embeddings' FROM embeddings;"

# Check application health
curl -s http://localhost:8000/health | jq .

# Check ChromaDB connection
curl -s http://localhost:3307 | jq .

# Check vLLM models
curl -s http://localhost:8001/v1/models | jq .

# Monitor system resources
nvidia-smi  # GPU usage
free -h     # Memory usage
df -h       # Disk usage
top -b -n1  # Top processes
```

---

## Troubleshooting

### Issue: "Cannot connect to MariaDB"
```bash
# Check if container is running
docker-compose -f .devcontainer/docker-compose.yaml ps mariadb

# If not running, start services
docker-compose -f .devcontainer/docker-compose.yaml up -d

# Test connection directly
docker-compose -f .devcontainer/docker-compose.yaml exec mariadb mysqladmin ping -u root -proot_password
```

### Issue: "Port 8000 already in use"
```bash
# Find process using port 8000
lsof -i :8000

# Kill process
kill -9 <PID>

# Or use different port
python manage.py runserver 0.0.0.0:8001
```

### Issue: "Application startup timeout"
```bash
# Check Django logs
tail -f deployment-simulation/app.log

# Try running migrations again
python manage.py migrate --noinput

# Run basic Django check
python manage.py check
```

### Issue: "Out of memory during training"
```bash
# Check current memory usage
free -h

# Reduce test data
bash run_deployment_simulation.sh --quick

# Or manually create smaller dataset
python populate_database.py --documents 10 --embeddings 20
```

### Issue: "GPU memory full"
```bash
# Check vLLM status
curl -s http://localhost:8001/v1/models | jq .

# Check GPU memory
nvidia-smi

# Restart vLLM if stuck
docker-compose -f .devcontainer/docker-compose.yaml restart vllm

# Wait for reload
sleep 10
curl -s http://localhost:8001/v1/models | jq .
```

---

## Performance Baselines

After simulation, you'll have:

| Metric | Expected Range |
|--------|-----------------|
| App startup time | 5-10 seconds |
| First API response | <100ms |
| Database query | <10ms |
| Embedding generation | 100-500ms per document |
| Training epoch | 1-5 minutes |
| GPU memory usage | 18-22GB |
| CPU usage | 20-40% |

---

## Next Steps After Simulation

1. **Review Results:**
   ```bash
   cat deployment-simulation/simulation_*.log
   ```

2. **Check Dashboard:**
   Open browser: http://localhost:8000

3. **Inspect Data:**
   ```bash
   mysql -h mariadb -u justnews -pjustnews_password justnews -e "SELECT * FROM documents LIMIT 5;"
   ```

4. **Run Custom Tests:**
   ```bash
   pytest tests/ -v -k "test_name"
   ```

5. **Stop Simulation:**
   ```bash
   # Get app PID from log
   ps aux | grep runserver
   
   # Kill process
   kill <PID>
   
   # Optionally stop Docker services
   docker-compose -f .devcontainer/docker-compose.yaml stop
   ```

---

## Architecture During Simulation

```
┌─────────────────────────────────────────────────────────────┐
│                    DEV CONTAINER                             │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   MariaDB    │  │  ChromaDB    │  │    vLLM      │       │
│  │   (3306)     │  │   (3307)     │  │   (8001)     │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│         ▲                  ▲                  ▲               │
│         └──────────────────┼──────────────────┘               │
│                            │                                  │
│  ┌──────────────────────────────────────────────────┐        │
│  │          Django Application (8000)                │        │
│  │  ┌────────────────────────────────────────────┐  │        │
│  │  │  Training System Integration               │  │        │
│  │  │  • Model Loading                           │  │        │
│  │  │  • Inference Pipeline                      │  │        │
│  │  │  • Data Processing                         │  │        │
│  │  └────────────────────────────────────────────┘  │        │
│  └──────────────────────────────────────────────────┘        │
│                                                               │
└─────────────────────────────────────────────────────────────┘

Data Flow:
  1. populate_database.py → MariaDB
  2. Training data → ChromaDB (embeddings)
  3. vLLM inference → Model outputs
  4. Django endpoints ← Results
```

---

## File Structure

```
/app/
├── DEPLOYMENT_SIMULATION_GUIDE.md     (9-phase detailed guide)
├── populate_database.py                (auto-populate script)
├── run_deployment_simulation.sh        (orchestration script)
└── deployment-simulation/              (auto-created during run)
    ├── simulation_*.log               (run logs)
    ├── app.log                        (app output)
    └── service_pids.txt               (process IDs)
```

---

## Key Differences: Simulation vs Production

| Aspect | Simulation | Production |
|--------|-----------|-----------|
| Location | Dev container | Remote server |
| Services | Docker Compose | Systemd |
| Secrets | Environment variables | HashiCorp Vault |
| Monitoring | Optional | Required |
| Security | Relaxed | Hardened |
| Backups | Manual | Automated |
| Scaling | Single process | Multiple workers |
| Load balancing | Direct access | Required |

---

## Questions?

Refer to the detailed guides:
- **Full procedures:** See `DEPLOYMENT_SIMULATION_GUIDE.md`
- **Production deployment:** See `docs/operations/DEPLOYMENT_PLAYBOOK.md`
- **Troubleshooting:** See `docs/operations/VAULT_TROUBLESHOOTING.md`
- **Security:** See `docs/security/SECURITY_AUDIT.md`

---

**Status:** ✅ Phase 5 Simulation Framework Ready  
**Last Updated:** $(date)  
**Total Documentation:** 9,600+ lines (Phases 1-5)  
**Git Commits:** 37+  
**Ready for:** Local testing, database population, training system validation

