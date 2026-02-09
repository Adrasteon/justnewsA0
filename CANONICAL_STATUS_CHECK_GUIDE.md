# JustNews Canonical System Status Check

## Overview

**Purpose:** Rapid "light touch" verification that all JustNews system components are operational.

**Scope:** NOT a replacement for comprehensive testing—designed for quick diagnostics during development and deployment.

**Runtime:** ~30-60 seconds (depending on service startup state)

**Usage:**
```bash
python canonical_status_check.py        # Run normally
python canonical_status_check.py -v     # Verbose output
```

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| **0** | 🟢 GO | All systems operational, proceed with work |
| **0** | 🟡 GO (with warnings) | Systems operational, some minor issues noted |
| **2** | 🟠 DEGRADED | Some critical components offline, limited functionality |
| **1** | 🔴 NO-GO | Critical failures, system not operational |

## What Gets Checked

### 📦 Infrastructure (2 checks)
- ✓ All Docker containers running (mariadb, chromadb, vllm, app)
- ✓ Network ports accessible (3306, 3307, 8000)

### 🔌 Service Health (3 checks)
- ✓ MariaDB connectivity and auth
- ✓ ChromaDB HTTP API heartbeat
- ✓ vLLM API responding

### 📊 Database Schema (2 checks)
- ✓ All required pipeline tables exist
- ✓ Django migrations applied

### 🧠 Vector Database (1 check)
- ✓ ChromaDB collections accessible (may be empty on fresh build)

### 🤖 ML Model (1 check)
- ✓ vLLM model loaded (warns if still initializing)

### 🔑 Environment (2 checks)
- ✓ Required environment variables set
- ✓ Python dependencies installed

**Total: 11 checks**

## Output Example

```
============================================================
JustNews Canonical System Status Check
============================================================

📦 INFRASTRUCTURE CHECKS
------------------------------------------------------------
  ✓ Docker Containers
  ✓ Port MariaDB (3306) [0.1s]
  ✓ Port ChromaDB (3307) [0.1s]
  ✓ Port vLLM (8000) [0.2s]

🔌 SERVICE HEALTH CHECKS
------------------------------------------------------------
  ✓ MariaDB Connection [0.3s]
  ✓ ChromaDB API [0.1s]
  ✓ vLLM API [1.2s]

📊 DATABASE SCHEMA CHECKS
------------------------------------------------------------
  ✓ Database Tables (14 found)
  ✓ Database Migrations (24)

🧠 VECTOR DATABASE CHECKS
------------------------------------------------------------
  ✓ ChromaDB Collections (0) (expected for fresh build)

🤖 ML MODEL CHECKS
------------------------------------------------------------
  ✓ vLLM Model (Qwen2.5-14B-Instruct-AWQ)

🔑 ENVIRONMENT CHECKS
------------------------------------------------------------
  ✓ Environment Variables
  ✓ Python Dependencies

============================================================
SUMMARY
============================================================

Checks completed: 11
  ✓ OK:       11
  ⚠ Warnings: 0
  ✗ Failures: 0

System Status: 🟢 GO
```

## Common Scenarios

### ✓ Fresh Build (All Green)
```
System Status: 🟢 GO
```
Everything initialized, ready for development/deployment.

### ⚠ Fresh Build with Warnings
```
System Status: 🟡 GO (with warnings)

Warnings (may be expected):
  • ChromaDB Collections (0): No collections (expected for fresh build)
  • vLLM Model: Model still loading...
```
This is **expected**. Collections will be created during crawling. Model loading is normal for large models (Qwen2.5-14B).

### 🟠 Degraded Service
```
System Status: 🟠 DEGRADED

Failed checks (needs attention):
  • Docker Containers: Missing: vllm
  • vLLM API: Connection refused
```
A service is down but system partially functional. Check logs:
```bash
docker logs vllm
docker restart vllm
```

### 🔴 Critical Failure
```
System Status: 🔴 NO-GO

Failed checks (needs attention):
  • MariaDB Connection: Connection refused
  • Docker Containers: Missing: mariadb, chromadb
```
Infrastructure down. Rebuild containers:
```bash
docker-compose restart mariadb chromadb
# or full rebuild
docker-compose down && docker-compose up -d
```

## Integration Points

### In CI/CD Pipeline
```yaml
- name: System Status Check
  run: |
    python canonical_status_check.py
  continue-on-error: false  # Fail build if status is NO-GO
```

### In Deployment Scripts
```bash
#!/bin/bash
python canonical_status_check.py
if [ $? -ne 0 ]; then
    echo "System not ready for deployment!"
    exit 1
fi
echo "Proceeding with deployment..."
```

### In Development
```bash
# Quick health check before running tests
python canonical_status_check.py && pytest tests/
```

### In Monitoring
```bash
# Run every 60 seconds, alert on failures
while true; do
    python canonical_status_check.py > /tmp/status.txt 2>&1
    if [ $? -ne 0 ]; then
        # Alert/notify
        mail -s "JustNews Status Check Failed" ops@company.com < /tmp/status.txt
    fi
    sleep 60
done
```

## Customization

### Environment Variables

The script uses standard environment variables from your `.env` or `global.env`:

```bash
# Database
MARIADB_HOST=mariadb              # Default: "mariadb"
MARIADB_PORT=3306                 # Default: 3306
MARIADB_USER=justnews             # Default: "justnews"
MARIADB_PASSWORD=***              # Default: "dev_justnews_password"
MARIADB_DB=justnews               # Default: "justnews"

# Vector Database
CHROMADB_HOST=chromadb            # Default: "chromadb"
CHROMADB_PORT=3307                # Default: 3307

# ML Model
VLLM_HOST=vllm                     # Default: "vllm"
VLLM_PORT=8000                     # Default: 8000

# App
APP_HOST=localhost                 # Default: "localhost"
APP_PORT=8000                      # Default: 8000
```

Override by setting environment variables:
```bash
CHROMADB_PORT=8001 python canonical_status_check.py
```

### Adding Custom Checks

Edit `canonical_status_check.py` and add a method to the `CanonicalStatusChecker` class:

```python
def check_custom_service(self) -> None:
    """Check custom service."""
    try:
        # Your check logic here
        result = do_something()
        
        if result:
            self.record_result("Custom Service", Status.OK)
        else:
            self.record_result("Custom Service", Status.FAIL, "Custom reason")
    except Exception as e:
        self.record_result("Custom Service", Status.FAIL, str(e)[:40])
```

Then call it from `run_all_checks()`:
```python
print("🔧 CUSTOM CHECKS")
print("-" * 60)
self.check_custom_service()
print()
```

## Troubleshooting

### Script Hangs
The script has 5-10 second timeouts on all network operations. If it hangs:
```bash
# Kill and check with verbose output
timeout 30 python canonical_status_check.py -v

# Or check specific service (ChromaDB v2 API)
curl -v http://chromadb:8000/api/v2/heartbeat
```

### "Connection refused" on Docker services
Services are running but not ready. This is normal during startup:
```bash
# Wait for service to be ready
docker-compose logs -f mariadb
# Once ready, re-run:
python canonical_status_check.py
```

### Python import errors
Required packages not installed:
```bash
pip install pymysql chromadb requests
```

### Missing environment variables
The script has reasonable defaults but will warn if key vars are missing:
```bash
# Source your environment
source global.env
python canonical_status_check.py
```

## Performance Considerations

- **Fast:** Container checks, port checks, API health (< 1 sec each)
- **Slower:** Database queries, vLLM initialization (1-5 sec each)
- **Total typical time:** 30-45 seconds

To speed up (skip heavy checks):
```python
# Edit canonical_status_check.py, comment out in run_all_checks():
# self.check_database_tables()        # Skip if you know schema is good
# self.check_vllm_model()             # Skip if model still loading
```

## Related Commands

```bash
# View full logs for failed service
docker logs <service_name>

# Restart a service
docker restart <service_name>

# Full system restart
docker-compose down && docker-compose up -d

# Check detailed health
docker ps --format "table {{.Names}}\t{{.Status}}"

# View resource usage
docker stats
```

## Files

- **Script:** [canonical_status_check.py](canonical_status_check.py)
- **Documentation:** [CANONICAL_STATUS_CHECK_GUIDE.md](CANONICAL_STATUS_CHECK_GUIDE.md) (this file)
- **Related:** [DEVCONTAINER_QUICK_REFERENCE.md](DEVCONTAINER_QUICK_REFERENCE.md)

## Future Enhancements

Potential additions (not currently implemented):
- [ ] Database backup verification
- [ ] ChromaDB collection consistency check
- [ ] Application endpoint health checks
- [ ] Resource usage warnings (disk, memory, CPU)
- [ ] Log error rate analysis
- [ ] Persistent status history tracking
