# Production Readiness Guide

**Date**: February 8, 2026  
**Version**: 1.0  
**Audience**: DevOps, Infrastructure Engineers, Security Team

---

## 📋 Overview

This guide walks through the complete production readiness process for the JustNews infrastructure. It covers deployment validation, secrets management, security hardening, and production configuration generation.

---

## ✅ Pre-Production Checklist

### Phase 1: Development Environment Validation ✅

**Status**: COMPLETE
- ✅ Dev container builds cleanly
- ✅ All services reach healthy state
- ✅ Integration tests passing (5/5)
- ✅ Performance baselines captured
- ✅ Operational procedures documented

### Phase 2: Staging Environment (This Phase)

**Must complete before production**:
- [ ] Deploy to staging environment
- [ ] Run full integration test suite
- [ ] Verify all operational procedures work
- [ ] Load test with realistic data (1000+ articles)
- [ ] Monitor for 24+ hours for stability
- [ ] Verify backup/restore procedures
- [ ] Validate monitoring & alerting
- [ ] Security scan completed

---

## 🏗️ Deployment Architecture

### Supported Deployment Targets

| Target | Status | Best For | Timeline |
|--------|--------|----------|----------|
| **Docker Compose** (dev) | ✅ Working | Local development | < 5 min |
| **Systemd** (primary) | ⏳ This Phase | Production servers | 10–30 min |
| **Kubernetes** (future) | 📋 Planned | Cloud scale | Phase 5+ |

### Systemd Deployment (Primary Target)

Per `infrastructure/README.md`, Systemd is the primary production deployment target.

**Key advantages**:
- Native Linux process management
- Automatic restart on failure
- Resource limiting (memory, CPU)
- Integrated logging (journalctl)
- No container overhead
- Simple monitoring (systemctl status)

**Prerequisites**:
- Linux host with Python 3.10+
- Systemd available (all modern Linux distributions)
- MariaDB service available (separate server or container)
- GPU drivers (for vLLM)
- 30GB free disk space (model + logs + data)
- Network access to HuggingFace (for model download)

---

## 🔐 Secrets Management

### Current State (Dev)

❌ **Not suitable for production**:
```bash
# Current (plaintext in file)
export MARIADB_PASSWORD=dev_password
export HF_TOKEN=dev_token
```

**Risk**: 
- Credentials in git history
- Exposed if env file leaked
- No rotation capability
- No audit trail

### Target State (Production)

✅ **Vault Integration** (secure):
- Centralized secrets management
- Dynamic secret generation
- Audit trail for all access
- Automatic rotation support
- Encryption at rest & in transit

**Implementation**:
1. Install Vault (standalone or HA)
2. Configure authentication (AppRole, JWT, etc.)
3. Implement `scripts/fetch_secrets_to_env.sh`
4. Set up automatic rotation (optional but recommended)

**See**: [VAULT_SETUP.md](./docs/operations/VAULT_SETUP.md) for detailed setup

---

## 🔍 Security Hardening

### 1. File Permissions

**All secrets must be 600 (read-only by owner)**:

```bash
# Wrong (readable by others):
-rw-r--r-- 1 root root  /app/global.env    ✗ 644
-rw-r--r-- 1 root root  /app/.env.prod     ✗ 644

# Correct (only owner can read):
-rw------- 1 root root  /app/global.env    ✓ 600
-rw------- 1 root root  /app/.env.prod     ✓ 600

# Fix:
chmod 600 /app/global.env
chmod 600 /app/.env.prod
```

**Service account** (systemd):
```bash
# Create dedicated service account
useradd -r -s /bin/false justnews-app
# All application files owned by this user
chown -R justnews-app:justnews-app /app
chmod 750 /app  # User can read/exec, group/others cannot
```

### 2. Network Isolation

**MariaDB** (database):
```yaml
# ✗ Wrong: Exposed to networks
ports:
  - "3306:3306"  # Anyone on network can connect

# ✓ Correct: Only app container accesses
# No port mapping, Docker internal network only
docker network: internal
```

**ChromaDB** (vector database):
```yaml
# ✓ Correct: Only app container accesses
# No port mapping to host
ports:
  - "3307:8000"  # Only Docker Compose exposes (for dev)
# Production: Remove port mapping entirely
```

**vLLM** (LLM server):
```yaml
# ✓ Correct: Only app container accesses
ports:
  - "8001:8000"  # Only Docker Compose exposes (for dev)
# Production: Remove port mapping entirely
```

**Firewall rules** (Linux host):
```bash
# Only allow SSH
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp  # SSH only
ufw allow out to 0.0.0.0/0 port 443 tcp  # HTTPS for HuggingFace
ufw enable

# Verify
ufw status
# Should show: SSH allowed, all else denied
```

### 3. API Authentication

**Current state (dev)**: No authentication

**Production requirements**:
- API key validation on all endpoints
- Rate limiting (100 req/min per key)
- JWT tokens with expiration (24 hours)
- Request signing (HMAC-SHA256)

**Implementation checklist**:
- [ ] Add authentication middleware to app
- [ ] Generate API keys for clients
- [ ] Implement rate limiting
- [ ] Setup JWT token validation
- [ ] Document authentication in API docs

**See**: `config/schemas/__init__.py` for examples

### 4. TLS/HTTPS

**For production app server**:
```bash
# Generate self-signed certificate (short-term)
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365

# Or use Let's Encrypt (recommended)
certbot certonly --standalone -d your-domain.com

# Configure in app (Django/FastAPI)
# See infrastructure/README.md for framework-specific setup
```

**Certificate storage**:
```bash
# Store in /etc/justnews/ with restricted permissions
sudo mkdir -p /etc/justnews/tls
sudo cp cert.pem /etc/justnews/tls/
sudo cp key.pem /etc/justnews/tls/
sudo chmod 600 /etc/justnews/tls/key.pem
sudo chmod 644 /etc/justnews/tls/cert.pem
```

### 5. Logging & Audit Trail

**Application logs** (must be secure):
```bash
# Log file locations
/var/log/justnews/app.log       # Application logs
/var/log/justnews/access.log    # HTTP access logs
/var/log/justnews/error.log     # Errors only

# Permissions
sudo chown -R root:root /var/log/justnews
sudo chmod 750 /var/log/justnews
sudo chmod 640 /var/log/justnews/*.log
```

**Security audit log** (separate from app logs):
```bash
# Log all sensitive operations
- User login/logout
- API key usage
- Permission changes
- Configuration updates
- Backup operations
- Incident responses

# Store in audit log
/var/log/justnews/audit.log
```

**Log rotation**:
```bash
# Setup logrotate to prevent disk fill
/etc/logrotate.d/justnews

/var/log/justnews/*.log {
    daily
    rotate 30
    compress
    delaycompress
    copytruncate
    notifempty
    create 640 justnews-app justnews-app
}

# Verify
logrotate -d /etc/logrotate.d/justnews
```

---

## 🚀 Systemd Deployment

### Step 1: Prepare Host System

```bash
# 1. Update system packages
sudo apt update && sudo apt upgrade -y

# 2. Install dependencies
sudo apt install -y python3.10 python3-pip curl build-essential

# 3. Install NVIDIA GPU drivers (if GPU present)
ubuntu-drivers autoinstall
# Verify: nvidia-smi

# 4. Create application directory
sudo mkdir -p /opt/justnews
sudo chown -R root:root /opt/justnews
chmod 755 /opt/justnews

# 5. Clone application code
cd /opt/justnews
git clone https://github.com/your-org/justnews.git .
# OR untar release package
tar xzf justnews-release.tar.gz -C /opt/justnews

# 6. Verify code
ls -la /opt/justnews/infrastructure/scripts/
ls -la /opt/justnews/requirements*.txt
```

### Step 2: Create Systemd Service Files

**Main app service** (`/etc/systemd/system/justnews-app.service`):

```ini
[Unit]
Description=JustNews Web Application
After=mariadb.service network-online.target
Wants=network-online.target

[Service]
Type=simple
User=justnews-app
Group=justnews-app
WorkingDirectory=/opt/justnews

# Environment
EnvironmentFile=/etc/justnews/.env.prod
Environment="DJANGO_SETTINGS_MODULE=justnews_publisher.settings"
Environment="PYTHONUNBUFFERED=1"

# Startup
ExecStart=/opt/justnews/venv/bin/python manage.py runserver 0.0.0.0:8000

# Resource limits
MemoryMax=2G
MemoryHigh=1.8G
CPUQuota=200%  # 2 CPU cores
TasksMax=512

# Restart policy
Restart=on-failure
RestartSec=10
StartLimitBurst=5
StartLimitIntervalSec=300

# Logging
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**vLLM service** (`/etc/systemd/system/justnews-vllm.service`):

```ini
[Unit]
Description=JustNews vLLM Model Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=justnews-app
Group=justnews-app
WorkingDirectory=/opt/justnews

# Environment
EnvironmentFile=/etc/justnews/.env.prod
Environment="PYTHONUNBUFFERED=1"

# GPU assignment
ExecStart=/opt/justnews/venv/bin/python -m vllm.entrypoints.openai.api_server \\
  --model Qwen/Qwen2.5-14B-Instruct-AWQ \\
  --tensor-parallel-size 1 \\
  --gpu-memory-utilization 0.9 \\
  --port 8001

# Resource limits (GPU + memory)
MemoryMax=30G
MemoryHigh=25G
CPUQuota=400%  # 4 CPU cores for inference
TasksMax=512

# Restart policy
Restart=on-failure
RestartSec=30
StartLimitBurst=3
StartLimitIntervalSec=300

# Logging
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**ChromaDB service** (`/etc/systemd/system/justnews-chromadb.service`):

```ini
[Unit]
Description=JustNews ChromaDB Vector Database
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=justnews-app
Group=justnews-app
WorkingDirectory=/opt/justnews

# Environment
EnvironmentFile=/etc/justnews/.env.prod
Environment="PYTHONUNBUFFERED=1"

# Startup
ExecStart=/opt/justnews/venv/bin/chroma run --host 0.0.0.0 --port 8002

# Resource limits
MemoryMax=6G
MemoryHigh=5G
CPUQuota=200%
TasksMax=256

# Restart policy
Restart=on-failure
RestartSec=10
StartLimitBurst=5
StartLimitIntervalSec=300

# Logging
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Step 3: Start Services

```bash
# 1. Reload systemd daemon
sudo systemctl daemon-reload

# 2. Start services (in order)
sudo systemctl start mariadb        # Assumes mariadb already setup
sleep 10
sudo systemctl start justnews-chromadb
sleep 5
sudo systemctl start justnews-vllm  # Takes 2-5 min for model load
sleep 120
sudo systemctl start justnews-app

# 3. Enable auto-start
sudo systemctl enable justnews-app
sudo systemctl enable justnews-chromadb
sudo systemctl enable justnews-vllm

# 4. Verify status
sudo systemctl status justnews-app
sudo systemctl status justnews-chromadb
sudo systemctl status justnews-vllm
```

### Step 4: Verify Deployment

```bash
# Check service status
systemctl status justnews-app          # Should be "active (running)"
systemctl status justnews-vllm         # Should be "active (running)"
systemctl status justnews-chromadb     # Should be "active (running)"

# Check logs
sudo journalctl -u justnews-app -f     # Follow app logs
sudo journalctl -u justnews-vllm -f    # Follow vllm logs
sudo journalctl -u justnews-chromadb -f  # Follow chromadb logs

# Check listening ports
sudo netstat -tlnp | grep 8000
sudo netstat -tlnp | grep 8001
sudo netstat -tlnp | grep 8002

# Test connectivity
curl http://localhost:8000/health      # App health
curl http://localhost:8001/v1/models   # vLLM models
curl http://localhost:8002/api/v1/heartbeat  # ChromaDB health
```

---

## 📝 Environment Configuration

### Configuration Hierarchy

```
1. System defaults (code)
                ↓
2. .env.default (public, git-tracked)
                ↓
3. .env.<environment> (prod, staging, dev - git-ignored)
                ↓
4. /etc/justnews/.env.prod (systemd runtime, secure)
                ↓
5. Vault secrets (production only, highest priority)
```

### Environment Files

**Development** (`.env.dev`):
```bash
DEBUG=true
LOG_LEVEL=DEBUG
MARIADB_HOST=mariadb
MARIADB_PORT=3306
MARIADB_DB=justnews_dev
CHROMADB_HOST=chromadb
CHROMADB_PORT=3307
VLLM_HOST=vllm
VLLM_PORT=8001
HF_TOKEN=your-dev-token
```

**Staging** (`.env.staging`):
```bash
DEBUG=false
LOG_LEVEL=INFO
MARIADB_HOST=staging-db.internal
MARIADB_PORT=3306
MARIADB_DB=justnews_staging
CHROMADB_HOST=staging-chromadb.internal
CHROMADB_PORT=8000
VLLM_HOST=staging-vllm.internal
VLLM_PORT=8000
HF_TOKEN=vault:staging-hf-token
```

**Production** (`.env.prod` - in `/etc/justnews/`):
```bash
DEBUG=false
LOG_LEVEL=WARN
MARIADB_HOST=prod-db.internal
MARIADB_PORT=3306
MARIADB_DB=justnews_prod
CHROMADB_HOST=prod-chromadb.internal
CHROMADB_PORT=8000
VLLM_HOST=prod-vllm.internal
VLLM_PORT=8000
HF_TOKEN=vault:prod-hf-token
VAULT_ADDR=https://vault.company.com
VAULT_TOKEN=s.xxxxxxxxxxxxx
TLS_CERT=/etc/justnews/tls/cert.pem
TLS_KEY=/etc/justnews/tls/key.pem
```

### Generate Production Config

```bash
# From project root
python infrastructure/scripts/generate-config.py \
  --deploy-env production \
  --deploy-target systemd \
  --output /tmp/config_prod.env

# Review before deploying
cat /tmp/config_prod.env

# Deploy to production host
scp /tmp/config_prod.env prod-server:/tmp/
ssh prod-server "sudo mv /tmp/config_prod.env /etc/justnews/.env.prod && sudo chmod 600 /etc/justnews/.env.prod"
```

---

## ✅ Production Readiness Checklist

### Pre-Deployment (Before Day 1)

- [ ] **Infrastructure Ready**
  - [ ] Production server provisioned (30GB disk, 8GB CPU RAM, GPU if needed)
  - [ ] MariaDB server running (separate from app)
  - [ ] Network configured (app → db internal, SSH only inbound)
  - [ ] GPU drivers installed (if applicable)
  - [ ] Python 3.10+ installed

- [ ] **Secrets Configured**
  - [ ] Vault installed and running
  - [ ] All secrets migrated from plaintext to Vault
  - [ ] API keys generated for all integrations
  - [ ] HF_TOKEN configured with production account
  - [ ] Database credentials set to production values

- [ ] **Security Hardened**
  - [ ] TLS certificates generated/obtained
  - [ ] Firewall configured (SSH only + outbound HTTPS)
  - [ ] File permissions set correctly (600 for secrets, 640 for logs)
  - [ ] Service account created (`justnews-app`)
  - [ ] SELinux policies configured (if applicable)
  - [ ] Security scan completed (no critical vulnerabilities)

- [ ] **Monitoring Setup**
  - [ ] Prometheus scraping configured
  - [ ] Alerting thresholds in place
  - [ ] Log aggregation setup (ELK, Splunk, etc.)
  - [ ] Slack/PagerDuty integration configured
  - [ ] Backup procedures tested
  - [ ] Disaster recovery plan validated

- [ ] **Documentation Complete**
  - [ ] Runbooks written for common operations
  - [ ] Incident response procedures documented
  - [ ] Escalation contacts listed
  - [ ] Access requests documented
  - [ ] Architecture diagrams created

### Post-Deployment (Day 1+)

- [ ] **Services Healthcheck**
  - [ ] `systemctl status justnews-app` shows active
  - [ ] `systemctl status justnews-vllm` shows active
  - [ ] `systemctl status justnews-chromadb` shows active
  - [ ] All health endpoints return 200 OK
  - [ ] GPU memory stable (21–22GB for vLLM)
  - [ ] Database connections < 30

- [ ] **Data Validation**
  - [ ] Database migrations complete
  - [ ] Initial data loaded (if needed)
  - [ ] Collections initialized in ChromaDB
  - [ ] vLLM model fully loaded and responding

- [ ] **Operational Readiness**
  - [ ] Logs flowing to aggregation system
  - [ ] Alerts firing and routing correctly
  - [ ] Backups running on schedule
  - [ ] Monitoring dashboard populated
  - [ ] On-call rotation activated

- [ ] **Performance Baseline**
  - [ ] Capture baseline performance metrics
  - [ ] Compare against dev/staging
  - [ ] Document any deviations
  - [ ] Alert thresholds adjusted if needed

### Weeks 1-2 (Stabilization Period)

- [ ] **Monitor for Issues**
  - [ ] No unexpected restarts
  - [ ] Memory usage stable (no leaks)
  - [ ] Response times consistent
  - [ ] Error rates < 0.1%

- [ ] **Optimize if Needed**
  - [ ] Adjust resource limits based on actual usage
  - [ ] Tune database connection pooling
  - [ ] Fine-tune alert thresholds
  - [ ] Update runbooks based on learnings

- [ ] **User Validation**
  - [ ] Functionality verified by QA team
  - [ ] Performance acceptable to users
  - [ ] No data quality issues
  - [ ] Feedback incorporated

---

## 🆘 Rollback Plan

**If critical issue within 24 hours of deployment**:

```bash
# 1. Stop all services
sudo systemctl stop justnews-app justnews-vllm justnews-chromadb

# 2. Restore from backup
sudo systemctl start mariadb
# Restore database from backup (see docs/operations/BACKUP.md)

# 3. Revert code (if needed)
cd /opt/justnews
git checkout production-backup-commit-hash
# OR restore from release package

# 4. Restart services
sudo systemctl start justnews-chromadb
sleep 5
sudo systemctl start justnews-vllm
sleep 120
sudo systemctl start justnews-app

# 5. Validate
curl http://localhost:8000/health
sudo systemctl status justnews-app
```

**Rollback decision criteria**:
- ✗ Any service unable to start
- ✗ Error rate > 5%
- ✗ Response time > 10s (p99)
- ✗ Data corruption detected
- ✗ Security vulnerability discovered

---

## 📚 Related Documentation

- [Vault Setup](./docs/operations/VAULT_SETUP.md)
- [Service Operations](./docs/operations/SERVICE_OPERATIONS.md)
- [Monitoring Setup](./docs/operations/MONITORING.md)
- [Infrastructure Details](./infrastructure/README.md)
- [Deployment Scripts](./infrastructure/scripts/)

---

## 🚀 Next Steps

1. **Prepare staging environment** - Deploy to staging first (recommended)
2. **Run integration tests** - `python tests/integration/test_devcontainer.py`
3. **Load test** - Run with 1000+ articles for 24+ hours
4. **Security scan** - Run vulnerability scanner on final image
5. **Get signoff** - QA, Security, and Ops team approval
6. **Deploy to production** - Follow steps in this guide
7. **Monitor closely** - First week is critical

---

**Production Readiness Status**: This guide is your roadmap. Follow steps sequentially before going live.

