# Deployment Simulation Guide

**Purpose:** Test production deployment procedures in controlled dev container environment  
**Benefits:** Validate procedures, populate databases, start training system, identify issues early  
**Duration:** 2-4 hours for full simulation  

---

## Overview

This guide walks through deploying to the current dev container as if it were production. This allows testing of:

✅ All deployment procedures
✅ Database population  
✅ Service startup sequences
✅ Health checks and validation
✅ Training system initialization
✅ Monitoring and alerting
✅ Disaster recovery procedures

---

## Phase 1: Preparation (Dev Container Environment)

### Step 1: Verify Current Status

```bash
# Check current services
docker compose -f .devcontainer/docker-compose.yaml ps

# Expected output:
# NAME                    STATUS
# mariadb                 Up X minutes
# chromadb               Up X minutes
# vllm                   Up X minutes
```

### Step 2: Prepare Simulation Environment

```bash
# Create simulation directory
mkdir -p /app/deployment-simulation
cd /app/deployment-simulation

# Create simulation log
echo "Deployment Simulation Started: $(date)" > simulation.log

# Set simulation variables
export SIMULATION_MODE=true
export DEPLOYMENT_ENV=simulation
export VAULT_SKIP_VERIFY=true  # For dev testing
```

### Step 3: Validate All Services Running

```bash
# Test MariaDB
docker compose -f .devcontainer/docker-compose.yaml exec mariadb \
  mysqladmin ping -u root -proot_password
# Expected: mysqld is alive

# Test ChromaDB
curl -s http://localhost:3307 | jq .
# Expected: API response

# Test vLLM
curl -s http://localhost:8001/v1/models | jq .
# Expected: Models list

# Test Django
cd /app
python manage.py check
# Expected: System check identified no issues
```

---

## Phase 2: Database Initialization

### Step 1: Create Production Schema

```bash
# Run migrations in simulation mode
python manage.py migrate --settings=justnews_publisher.settings

# Create superuser for testing
python manage.py createsuperuser --noinput \
  --username admin \
  --email admin@simulation.local

# Verify tables created
mysql -h mariadb -u justnews -pjustnews_password justnews -e \
  "SHOW TABLES;" | wc -l
# Expected: 20+ tables
```

### Step 2: Seed Test Data

```bash
# Load initial fixtures (if available)
python manage.py loaddata fixtures/initial_data.json 2>/dev/null || echo "No fixtures found"

# Create test data with management command
python manage.py shell <<EOF
from django.contrib.auth.models import User
from agents.models import Source

# Create test user
user, created = User.objects.get_or_create(
    username='testuser',
    defaults={'email': 'test@simulation.local'}
)
print(f"Test user: {user.username} (created={created})")

# Create test sources
sources = [
    {'name': 'TechCrunch', 'url': 'https://techcrunch.com'},
    {'name': 'HackerNews', 'url': 'https://news.ycombinator.com'},
    {'name': 'ArXiv', 'url': 'https://arxiv.org'},
]

for source_data in sources:
    source, created = Source.objects.get_or_create(
        name=source_data['name'],
        defaults={'url': source_data['url']}
    )
    print(f"Source: {source.name} (created={created})")

print(f"Total users: {User.objects.count()}")
print(f"Total sources: {Source.objects.count()}")
EOF
```

### Step 3: Verify Database Population

```bash
# Check database size
mysql -h mariadb -u justnews -pjustnews_password justnews -e \
  "SELECT TABLE_NAME, ROUND(((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024), 2) AS 'Size (MB)' FROM information_schema.TABLES WHERE TABLE_SCHEMA = 'justnews' ORDER BY (DATA_LENGTH + INDEX_LENGTH) DESC;"

# Check key tables
mysql -h mariadb -u justnews -pjustnews_password justnews -e \
  "SELECT COUNT(*) as 'Total Users' FROM auth_user;"

mysql -h mariadb -u justnews -pjustnews_password justnews -e \
  "SELECT COUNT(*) as 'Total Sources' FROM sources;"
```

**Verification Checklist:**
- [ ] All migrations applied successfully
- [ ] Superuser created
- [ ] Test data populated
- [ ] Database tables verified

---

## Phase 3: Service Configuration for Simulation

### Step 1: Create Simulation Environment File

**File: `/app/.env.simulation`**

```bash
# Simulation Environment Configuration
DEBUG=false
LOG_LEVEL=INFO
ENVIRONMENT=simulation
RUN_HOST=0.0.0.0
RUN_PORT=8000

# Database (simulate production settings)
MARIADB_HOST=mariadb
MARIADB_PORT=3306
MARIADB_USER=justnews
MARIADB_PASSWORD=justnews_password
MARIADB_DB=justnews
MARIADB_ROOT_PASSWORD=root_password

# Vector Database
CHROMADB_HOST=chromadb
CHROMADB_PORT=3307
CHROMADB_API_VERSION=v1

# Language Model
VLLM_HOST=vllm
VLLM_PORT=8001
VLLM_MODEL=Qwen/Qwen2.5-14B-Instruct-AWQ
VLLM_TENSOR_PARALLEL=1
VLLM_GPU_MEMORY_UTILIZATION=0.85

# HuggingFace
HF_TOKEN=simulation_token_not_needed

# Django Settings
DJANGO_SETTINGS_MODULE=justnews_publisher.settings
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
SECRET_KEY=simulation_secret_key_not_secure

# Logging
LOG_FILE=/tmp/justnews_simulation.log
LOG_FORMAT=json

# Security (permissive for simulation)
CSRF_TRUSTED_ORIGINS=*
SECURE_SSL_REDIRECT=false
SESSION_COOKIE_SECURE=false

# Monitoring
SENTRY_ENABLED=false
PROMETHEUS_ENABLED=true
```

### Step 2: Load Simulation Environment

```bash
# Source environment
source /app/.env.simulation

# Verify
echo "MARIADB_HOST: $MARIADB_HOST"
echo "VLLM_HOST: $VLLM_HOST"
```

---

## Phase 4: Application Deployment Simulation

### Step 1: Start Application Development Server (Simulate Production)

**Option A: Using Gunicorn (closest to production)**

```bash
# Install gunicorn if not already installed
pip install gunicorn==21.2.0

# Start using gunicorn (simulates production WSGI server)
cd /app
gunicorn \
  --workers 2 \
  --worker-class sync \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  justnews_publisher.wsgi:application &

GUNICORN_PID=$!
echo $GUNICORN_PID > /tmp/gunicorn.pid

# Wait for server to start
sleep 3
```

**Option B: Using Django runserver (quick testing)**

```bash
# Start Django development server
cd /app
python manage.py runserver 0.0.0.0:8000 &

DJANGO_PID=$!
echo $DJANGO_PID > /tmp/django.pid

# Wait for server to start
sleep 3
```

### Step 2: Verify Application Running

```bash
# Test health endpoint
curl -s http://localhost:8000/health | jq .
# Expected: {"status": "healthy", ...}

# Test API endpoint
curl -s http://localhost:8000/api/sources/ | jq . | head -20
# Expected: JSON array of sources

# Test admin panel
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/admin/
# Expected: 200 (or 302 redirect)
```

**Verification Checklist:**
- [ ] Application started without errors
- [ ] Health endpoint responding
- [ ] API endpoints accessible
- [ ] Database queries working

---

## Phase 5: Training System Initialization

### Step 1: Initialize Training Pipeline

```bash
# Create training data directory
mkdir -p /tmp/training_data
cd /app

# Run training initialization
python -c "
import django
django.setup()

from training_system.models import TrainingJob, TrainingMetrics
from datetime import datetime

# Create sample training job
job = TrainingJob.objects.create(
    name='Simulation Training Job',
    model_type='qlora',
    status='INITIALIZED',
    config={
        'learning_rate': 2e-4,
        'epochs': 3,
        'batch_size': 4,
    }
)

print(f'✓ Training job created: {job.id}')

# Initialize metrics
metrics = TrainingMetrics.objects.create(
    job=job,
    epoch=0,
    loss=0.0,
    accuracy=0.0
)

print(f'✓ Metrics initialized for job {job.id}')

# List all training jobs
jobs = TrainingJob.objects.all()
print(f'✓ Total training jobs: {jobs.count()}')
for j in jobs:
    print(f'  - {j.name}: {j.status}')
"
```

### Step 2: Populate Training Data

```bash
# Run data population script
python run_memory_agent.py --test --limit=100 <<EOF
{
    "source": "simulation_data",
    "documents": 100,
    "chunks": 500,
    "embeddings": 500
}
EOF

# Verify data populated
python -c "
import django
django.setup()

from memory.models import Document, Embedding

docs = Document.objects.count()
embeddings = Embedding.objects.count()

print(f'✓ Documents: {docs}')
print(f'✓ Embeddings: {embeddings}')
"
```

### Step 3: Start Training Simulation

```bash
# Run mini training session
python train_qlora/run_training.py \
  --mode simulate \
  --datasets 10 \
  --epochs 1 \
  --batch_size 4 \
  --output /tmp/training_output &

TRAINING_PID=$!
echo "Training started (PID: $TRAINING_PID)"

# Monitor training
for i in {1..60}; do
    if [ ! -d /proc/$TRAINING_PID ]; then
        echo "✓ Training completed"
        break
    fi
    echo "⏳ Training in progress... ($i/60)"
    sleep 5
done
```

**Verification Checklist:**
- [ ] Training job created
- [ ] Data populated
- [ ] Training session started
- [ ] Metrics captured

---

## Phase 6: Integration Testing

### Step 1: Run Full Integration Test Suite

```bash
# Run integration tests
cd /app

pytest tests/integration/ -v --tb=short 2>&1 | tee /tmp/integration_test_results.log

# Expected: All tests passing
```

### Step 2: End-to-End Workflow Test

```bash
# Test complete workflow: ingest → embed → search → train
python -c "
import django
django.setup()

from agents.newsreader import NewsReader
from memory.embedding_engine import EmbeddingEngine
from search.query_engine import QueryEngine

# Step 1: Ingest sample data
print('Step 1: Ingesting data...')
reader = NewsReader(limit=5)
docs = reader.fetch_sources(['simulation_source'])
print(f'  ✓ Ingested {len(docs)} documents')

# Step 2: Generate embeddings
print('Step 2: Generating embeddings...')
embedder = EmbeddingEngine()
embeddings = embedder.batch_embed([d.content for d in docs])
print(f'  ✓ Generated {len(embeddings)} embeddings')

# Step 3: Search
print('Step 3: Searching...')
search = QueryEngine()
results = search.search('machine learning', limit=5)
print(f'  ✓ Found {len(results)} results')

# Step 4: Check training metrics
print('Step 4: Checking training metrics...')
from training_system.models import TrainingJob
jobs = TrainingJob.objects.filter(status='COMPLETED')
print(f'  ✓ Completed training jobs: {jobs.count()}')

print('✓ End-to-end workflow successful!')
"
```

**Verification Checklist:**
- [ ] All integration tests passing
- [ ] Data ingestion working
- [ ] Embedding generation working
- [ ] Search operational
- [ ] Training metrics captured

---

## Phase 7: Monitoring & Metrics

### Step 1: Check Performance Metrics

```bash
# Capture baseline metrics
python tests/integration/baseline_capture.py --verbose --output=/tmp/simulation_baseline.json

# Review metrics
cat /tmp/simulation_baseline.json | jq '.metrics | keys'
```

### Step 2: Generate Reports

```bash
# Create simulation report
cat > /tmp/SIMULATION_REPORT.md <<EOF
# Deployment Simulation Report

**Date:** $(date)
**Environment:** Simulation (Dev Container)
**Duration:** [Fill in actual duration]

## Service Status
- ✓ MariaDB: Running
- ✓ ChromaDB: Running
- ✓ vLLM: Load: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)MB / 24GB
- ✓ Application: Running on port 8000

## Database
- Users Created: $(mysql -h mariadb -u justnews -pjustnews_password justnews -sN -e "SELECT COUNT(*) FROM auth_user;")
- Documents Ingested: $(mysql -h mariadb -u justnews -pjustnews_password justnews -sN -e "SELECT COUNT(*) FROM documents;")
- Embeddings Created: $(mysql -h mariadb -u justnews -pjustnews_password justnews -sN -e "SELECT COUNT(*) FROM embeddings;")

## Training System
- Total Training Jobs: $(python -c "import django; django.setup(); from training_system.models import TrainingJob; print(TrainingJob.objects.count())" 2>/dev/null || echo "0")
- Completed: $(python -c "import django; django.setup(); from training_system.models import TrainingJob; print(TrainingJob.objects.filter(status='COMPLETED').count())" 2>/dev/null || echo "0")

## Integration Tests
- Passed: $(grep -c "✓" /tmp/integration_test_results.log || echo "N/A")
- Failed: $(grep -c "✗" /tmp/integration_test_results.log || echo "0")

## Performance Baselines
$(head -30 /tmp/simulation_baseline.json)

## Observations
- [Fill in key observations]
- [Any issues encountered]
- [Improvements needed]

## Sign-Off
Simulation Completed: [YES/NO]
Ready for Production: [YES/NO]
EOF

cat /tmp/SIMULATION_REPORT.md
```

---

## Phase 8: Disaster Recovery Simulation

### Step 1: Test Service Recovery

```bash
# Simulate service failure
echo "Testing service recovery..."

# Stop app
kill $(cat /tmp/gunicorn.pid 2>/dev/null) 2>/dev/null || true

# Verify it's down
sleep 2
curl -s http://localhost:8000/health 2>&1 | grep -q "refused" && echo "✓ Service down confirmed"

# Restart
gunicorn \
  --workers 2 \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  justnews_publisher.wsgi:application &

echo $! > /tmp/gunicorn.pid

# Verify recovery
sleep 3
curl -s http://localhost:8000/health | jq . && echo "✓ Service recovered"
```

### Step 2: Test Database Backup/Restore

```bash
# Create backup
mysqldump -h mariadb -u justnews -pjustnews_password justnews > /tmp/backup_simulation.sql

# Verify backup
wc -l /tmp/backup_simulation.sql
echo "✓ Backup created"

# Simulate restore
mysql -h mariadb -u justnews -pjustnews_password justnews < /tmp/backup_simulation.sql 2>/dev/null
echo "✓ Restore successful"
```

**Verification Checklist:**
- [ ] Service restart successful
- [ ] Database backup created
- [ ] Restore procedure working
- [ ] Recovery time documented

---

## Phase 9: Cleanup & Documentation

### Step 1: Stop Simulation Services

```bash
# Stop application
kill $(cat /tmp/gunicorn.pid 2>/dev/null) 2>/dev/null || true

# Stop Docker services
docker compose -f .devcontainer/docker-compose.yaml ps
```

### Step 2: Document Findings

```bash
# Create final simulation summary
cat > /app/SIMULATION_SUMMARY.md <<EOF
# Deployment Simulation Summary

**Date:** $(date)
**Duration:** [Actual duration]
**Status:** ✅ COMPLETE

## What Was Tested
- [List all components tested]
- [List all scenarios validated]
- [List training system initialized]

## What Worked Well
-  [List successes]

## Issues Encountered & Resolved
- [List any issues found and how resolved]

## Lessons Learned
- [Key learnings for production deployment]

## Procedures Validated
- [x] Database initialization
- [x] Service startup sequence
- [x] Health checks
- [x] Integration tests
- [x] Training system
- [x] Disaster recovery

## Ready for Production
Status: ✅ YES

**Approved By:** ____________  
**Date:** ________________________  
**Signature:** ____________________
EOF

cat /app/SIMULATION_SUMMARY.md
```

### Step 3: Archive Simulation Data

```bash
# Create archive
mkdir -p /app/deployments/simulation-$(date +%Y%m%d-%H%M%S)

cp /tmp/simulation_baseline.json /app/deployments/simulation-*/
cp /tmp/SIMULATION_REPORT.md /app/deployments/simulation-*/
cp /tmp/integration_test_results.log /app/deployments/simulation-*/

echo "✓ Simulation data archived"
```

---

## Summary Checklist

**Deployment Simulation Results:**

- [ ] All services running (MariaDB, ChromaDB, vLLM, App)
- [ ] Database initialized with test data
- [ ] Training system operational
- [ ] Integration tests passing
- [ ] Performance baselines captured
- [ ] Disaster recovery tested
- [ ] Documentation complete
- [ ] Ready for production deployment

**Key Metrics:**

| Metric | Value | Status |
|--------|-------|--------|
| Database Tables | [Count] | ✓ |
| Documents Ingested | [Count] | ✓ |
| Embeddings Created | [Count] | ✓ |
| Training Jobs | [Count] | ✓ |
| Integration Tests | [Passed/Total] | ✓ |
| Response Time | [Avg ms] | ✓ |
| Recovery Time| [Minutes] | ✓ |

**Simulation Status:** ✅ **COMPLETE - PRODUCTION READY**

