# Service Startup & Troubleshooting Guide

**For Dev Container Developers**

This guide helps diagnose and resolve common service startup issues in the JustNews dev container.

---

## Quick Health Check

Run this from inside the dev container to verify all services:

```bash
#!/usr/bin/env bash
# Quick status check (run from /app)

echo "=== Service Health Check ==="
echo ""

# MariaDB
python3 << 'EOF'
import socket
try:
    sock = socket.create_connection(("mariadb", 3306), timeout=2)
    sock.close()
    print("✓ MariaDB: Accessible (port 3306)")
except:
    print("✗ MariaDB: Not accessible")
EOF

# ChromaDB
python3 << 'EOF'
import socket
try:
    sock = socket.create_connection(("chromadb", 3307), timeout=2)
    sock.close()
    print("✓ ChromaDB: Port open (port 3307, internal)")
except:
    print("✗ ChromaDB: Port not open")
EOF

# vLLM
python3 << 'EOF'
import socket
try:
    sock = socket.create_connection(("vllm", 8001), timeout=2)
    sock.close()
    print("✓ vLLM: Port open (port 8001, internal)")
except:
    print("✗ vLLM: Port not open")
EOF

echo ""
echo "=== Service Status from Host ==="
echo "Run from host terminal: docker-compose ps"
```

---

## Service Details

### MariaDB (Database)

**Port**: `3306` (internal)  
**Connection String**: `mariadb:3306`  
**Default Credentials**: 
- User: `justnews`
- Password: `dev_justnews_password` (from `global.env`)
- Database: `justnews`

**Startup Behavior**:
- Initializes on first start: ~15-30 seconds
- Creates database schema if not present
- Persists to `mariadb_data` Docker volume

**Troubleshooting**:

**Issue**: "Connection refused" multiple times, then succeeds
- **Solution**: Normal. MariaDB takes 20-30 seconds on first startup. post-create.sh waits up to 60 seconds.

**Issue**: "Table already exists" during migration
- **Solution**: Expected if database schema already existed. That's why `--fake-initial` flag is used in migrations.

**Issue**: Persistent connection failures after 60 seconds
- **Recovery**:
  ```bash
  # From host:
  docker-compose restart mariadb
  docker-compose logs mariadb -n 50
  
  # Check volume exists:
  docker volume ls | grep mariadb_data
  ```

**Healthy Indicators**:
- ✅ `docker-compose ps` shows `healthy` or `up`
- ✅ Python socket connection succeeds
- ✅ Django can import settings: `python manage.py shell` without errors

---

### ChromaDB (Vector Database)

**Port**: `3307` (external, maps to internal 8000)  
**Connection String**: `chromadb:3307` (from dev container)  
**Health Endpoint**: `http://chromadb:3307/api/v1/heartbeat`  
**Version**: `0.4.18` (pinned for API stability)

**Startup Behavior**:
- Lightweight (~2-5 seconds on startup)
- In-memory by default (`IS_PERSISTENT=FALSE` in docker-compose)
- No initial data to load

**Troubleshooting**:

**Issue**: HTTP 404 on `/api/version` or `/api/v1/heartbeat`
- **Cause**: Container running `latest` image (has breaking API changes)
- **Solution**: 
  ```bash
  # Verify in docker-compose.yaml:
  grep "chromadb/chroma:" .devcontainer/docker-compose.yaml
  # Should show: chromadb/chroma:0.4.18
  
  # If running latest, restart with corrected image:
  docker-compose down chromadb
  docker-compose up -d chromadb
  ```

**Issue**: Port 3307 refuses connections
- **Cause**: Container not running or crashed during startup
- **Recovery**:
  ```bash
  docker-compose logs chromadb -n 100
  docker-compose restart chromadb
  sleep 3
  curl -f http://chromadb:3307/api/v1/heartbeat
  ```

**Issue**: Embeddings not persisting between restarts
- **Expected**: `IS_PERSISTENT=FALSE` means data is ephemeral
- **Workaround**: Update docker-compose if persistence needed for your task:
  ```yaml
  chromadb:
    environment:
      - IS_PERSISTENT=TRUE
    volumes:
      - chromadb_data:/data
  ```

**Healthy Indicators**:
- ✅ Health check passes: `curl -f http://chromadb:3307/api/v1/heartbeat`
- ✅ Container shows "healthy" in docker-compose ps
- ✅ Can create collections and add embeddings via Python API

---

### vLLM (LLM Inference Server)

**Port**: `8001` (external, maps to internal 8000)  
**Connection String**: `vllm:8001` (from dev container)  
**Health Endpoints**:
- `/v1/models` — List loaded models
- `/v1/completions` — Test inference (POST)

**Model**: `Qwen/Qwen2.5-14B-Instruct-AWQ` (AWQ/Int4 quantized, ~14GB)

**Startup Behavior**:
- **First start**: 2-5 minutes (downloads model from HuggingFace)
- **Subsequent starts**: 30-60 seconds (loads from cache)
- **GPU Required**: Yes, uses all available CUDA devices
- **Model Cache**: `~/.cache/huggingface/` (mounted from host)

**Troubleshooting**:

**Issue**: "Connection refused" immediately, then port is open but `/v1/models` returns 404
- **Cause**: vLLM is starting (common during first-run model download)
- **Solution**: Wait 2-5 minutes for model to load
- **Check progress**:
  ```bash
  docker-compose logs vllm -f --tail 50
  # Look for: "Loaded model" or "Listening on" messages
  ```

**Issue**: vLLM container exits/crashes
- **Likely causes**:
  1. GPU out of memory (24GB RTX 3090 should be enough for Qwen 2.5 14B)
  2. Model download failed (network issue)
  3. CUDA not available in container
- **Recovery**:
  ```bash
  docker-compose logs vllm -n 100
  # Check for: CUDA errors, OOM, download failures
  
  # Restart with verbose logging:
  docker-compose restart vllm
  sleep 5
  docker-compose logs vllm -f
  ```

**Issue**: Model download stuck or timing out
- **Cause**: Large model (~14GB) over slow network
- **Solution**:
  1. Check HuggingFace availability: `curl -I https://huggingface.co`
  2. Verify `HF_TOKEN` is set if using gated models
     ```bash
     echo $HF_TOKEN
     ```
  3. Pre-download model on host:
     ```bash
     # On your host machine with better network:
     huggingface-cli download Qwen/Qwen2.5-14B-Instruct-AWQ
     ```

**Issue**: Inference very slow or non-responsive
- **Cause**: GPU memory pressure, model thrashing
- **Check**:
  ```bash
  # From host, check GPU usage:
  nvidia-smi -l 1  # Updates every 1 second
  # Should show stable allocated memory
  ```

**Healthy Indicators**:
- ✅ `docker-compose ps` shows `up`, not exited
- ✅ Container logs show "Loaded model" messages
- ✅ `/v1/models` endpoint returns model list
- ✅ `nvidia-smi` shows GPU memory allocated
- ✅ Test inference succeeds:
  ```bash
  curl -X POST http://vllm:8001/v1/completions \
    -H "Content-Type: application/json" \
    -d '{
      "model": "Qwen/Qwen2.5-14B-Instruct-AWQ",
      "prompt": "Hello, how are you?",
      "max_tokens": 10
    }' | python -m json.tool | head -20
  ```

---

## Full Service Diagnostic

Run this script to capture detailed status (Python):

```python
#!/usr/bin/env python3
import socket
import json
import urllib.request
import sys

def check_service(host, port, service_name, http_endpoint=None):
    """Check service availability and optionally test HTTP"""
    result = {"service": service_name, "port": port, "status": "unknown"}
    
    # Socket connectivity
    try:
        sock = socket.create_connection((host, port), timeout=2)
        sock.close()
        result["socket"] = "connected"
    except Exception as e:
        result["socket"] = f"failed: {e}"
        return result
    
    # HTTP health check if provided
    if http_endpoint:
        try:
            url = f"http://{host}:{port}{http_endpoint}"
            response = urllib.request.urlopen(url, timeout=3)
            result["http"] = f"{response.status} OK"
        except Exception as e:
            result["http"] = f"failed: {e}"
    
    return result

print("=== JustNews Service Diagnostic ===\n")

services = [
    ("mariadb", 3306, "MariaDB", None),
    ("chromadb", 3307, "ChromaDB", "/api/v1/heartbeat"),
    ("vllm", 8001, "vLLM", "/v1/models"),
]

results = []
for host, port, name, endpoint in services:
    result = check_service(host, port, name, endpoint)
    results.append(result)
    status = "✓" if "connected" in result.get("socket", "") else "✗"
    http_status = result.get("http", "—")
    print(f"{status} {name:15} port:{port:5} socket:{result.get('socket'):15} http:{http_status}")

print("\n=== Docker Compose Status ===")
print("From host, run: docker-compose ps")
print("Expected: app, mariadb, chromadb, vllm all 'Up'")

sys.exit(0 if all("connected" in r.get("socket", "") for r in results) else 1)
```

Save as `.devcontainer/diagnostic.py` and run:
```bash
python .devcontainer/diagnostic.py
```

---

## Common Error Messages & Solutions

### "Connection refused"
- **Check**: Service is running (`docker-compose ps`)
- **Fix**: Wait for full startup (especially vLLM on first run)
- **Fallback**: `docker-compose restart <service>`

### "No such host"
- **Check**: Container names in docker-compose.yaml
- **Fix**: Ensure service names match in connection strings

### "Operation timed out"
- **Check**: Host/port is accessible from container
- **Fix**: Force restart service, check Docker networking

### "Table already exists" (during migrate)
- **Expected**: Normal if schema pre-existed
- **Already handled**: Migrations use `--fake-initial`

### "OOM killed" (vLLM)
- **Cause**: Model doesn't fit in GPU memory
- **Solution**: Use smaller model or larger GPU

---

## Service Dependency Order

**Start sequence** (automatic in docker-compose):
1. `mariadb` (database must be ready first)
2. `chromadb` (lightweight, can start independently)
3. `vllm` (depends on HuggingFace connectivity, not other services)
4. `app` (dev container, depends_on vllm in compose)

**Post-startup checks** (in `/usr/local/bin/post-create.sh`):
1. Wait for MariaDB accessible (60 second timeout)
2. Run Django migrations
3. Health check ChromaDB and vLLM (warnings if not ready, doesn't block)

---

## Reference: Environment Variables

From `global.env`:
```bash
MARIADB_HOST=mariadb
MARIADB_PORT=3306
MARIADB_USER=justnews
MARIADB_PASSWORD=dev_justnews_password
MARIADB_DB=justnews

CHROMADB_HOST=chromadb
CHROMADB_PORT=3307

VLLM_HOST=vllm
VLLM_PORT=8001

HF_TOKEN=<your-huggingface-token>
```

---

## Quick Reference Commands

```bash
# Status
docker-compose ps -a
docker-compose ps mariadb

# Logs
docker-compose logs mariadb -n 50
docker-compose logs chromadb -f
docker-compose logs vllm --tail 100

# Restart specific service
docker-compose restart mariadb
docker-compose restart chromadb
docker-compose restart vllm

# Clean up everything (DESTRUCTIVE)
docker-compose down
docker volume rm mariadb_data chromadb_data
docker-compose up -d

# Rebuild container images
docker-compose build

# Shell into service
docker-compose exec mariadb bash
docker-compose exec vllm bash
```

---

## When to Contact Support

Escalate if:
- Services won't start after 5 restart attempts
- GPU is not detected despite `nvidia-smi` working on host
- Model downloads consistently fail (network verified as working)
- Persistent data corruption (table structure errors)
- Performance degradation on previously working system

Provide:
- Full `docker-compose logs -f` output (minimum 100 lines)
- `nvidia-smi` output from host
- Host OS and Docker version: `docker -v && docker stats --no-stream`
- Dev container initialization log: contents of `/tmp/setup_complete_v*.log`
