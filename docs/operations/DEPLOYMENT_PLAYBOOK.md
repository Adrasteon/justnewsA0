# Production Deployment Playbook

**Important:** This is a detailed runbook for deploying the justnews application to production. Follow each step carefully and verify before proceeding to the next.

**Estimated Duration:** 3-4 hours for complete deployment  
**Required Team:** Infrastructure Lead + Security Lead + Database Administrator  
**Rollback Available:** Yes (documented in this guide)

---

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Infrastructure Provisioning](#infrastructure-provisioning)
3. [Vault Setup](#vault-setup)
4. [Secrets Management](#secrets-management)
5. [Service Deployment](#service-deployment)
6. [Post-Deployment Validation](#post-deployment-validation)
7. [Monitoring & Alerting](#monitoring--alerting)
8. [Troubleshooting](#troubleshooting)
9. [Rollback Procedures](#rollback-procedures)

---

## Pre-Deployment Checklist

### Infrastructure Readiness

**Hardware Requirements (Minimum):**
```
✓ CPU: 4 cores (8+ recommended)
✓ RAM: 50GB (64GB+ recommended)
✓ Disk: 500GB SSD (1TB recommended)
✓ GPU: NVIDIA RTX 3090 or A100 (24GB+ VRAM)
✓ Network: 100 Mbps connectivity
```

**Verification:**
```bash
# Run on destination host
lscpu              # Verify CPU cores
free -h            # Verify memory
df -h /            # Verify disk space
nvidia-smi         # Verify GPU
speedtest          # Verify connectivity (if available)
```

**Sign-off:**
- [ ] **Infrastructure Lead:** ____________ (signature) Date: _______
- [ ] **On-Call Engineer:** ____________ (signature) Date: _______

### Security Audit Completion

**Before deploying to production, MUST complete:**

- [ ] **Run Security Audit Checklist**
  ```bash
  # Reference: docs/security/SECURITY_AUDIT.md
  # Time: 4-8 hours | Responsible: Security Lead
  # Status: _____ (PASS/FAIL)
  ```

- [ ] **All critical findings resolved**
  - [ ] No security blockers remaining
  - [ ] All permission issues fixed
  - [ ] All network policies validated

- [ ] **Security Lead Sign-Off**
  - [ ] Security Lead: ____________ (signature) Date: _______
  - [ ] Findings Document: [path to audit results]

### Team Availability

- [ ] **Infrastructure Lead Available**
  - [ ] Contact: ________________
  - [ ] Phone: ________________
  - [ ] Email: ________________

- [ ] **Security Lead Available**
  - [ ] Contact: ________________
  - [ ] Phone: ________________
  - [ ] Email: ________________

- [ ] **Database Administrator Available**
  - [ ] Contact: ________________
  - [ ] Phone: ________________
  - [ ] Email: ________________

- [ ] **On-Call Coverage Arranged**
  - [ ] 72-hour post-deployment monitoring
  - [ ] Incident escalation chain ready
  - [ ] PagerDuty configured

### Documentation Review

- [ ] [PRODUCTION_READINESS.md](docs/operations/PRODUCTION_READINESS.md) - Reviewed
- [ ] [SERVICE_OPERATIONS.md](docs/operations/SERVICE_OPERATIONS.md) - Reviewed
- [ ] [MONITORING.md](docs/operations/MONITORING.md) - Reviewed
- [ ] [SECURITY_AUDIT.md](docs/security/SECURITY_AUDIT.md) - Completed
- [ ] [VAULT_INTEGRATION_TESTING.md](docs/operations/VAULT_INTEGRATION_TESTING.md) - Reviewed

**Deployment Manager:** ____________ **Date:** _______ **Time:** _______

---

## Infrastructure Provisioning

### Step 1: Provision Production Host

**Options:**
- [ ] On-premises (physical server)
- [ ] Cloud (AWS, Azure, GCP, etc.)
- [ ] Hybrid (mix of on-prem and cloud)

**For Cloud Deployments:**

```bash
# Example: AWS EC2
aws ec2 run-instances \
  --image-id ami-0c6f5e5e1234567890 \
  --instance-type g4dn.xlarge \
  --key-name production-key \
  --security-group-ids sg-12345678 \
  --subnet-id subnet-12345678 \
  --iam-instance-profile Name=justnews-prod \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=justnews-prod},{Key=Environment,Value=production}]' \
  --user-data file://user-data.sh
```

### Step 2: OS Installation & Hardening

**Baseline Ubuntu 22.04 LTS:**

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install base packages
sudo apt install -y \
  curl wget git docker.io openssh-server openssh-client \
  build-essential python3.10 python3-pip python3-venv \
  nvidia-driver-530 nvidia-utils

# Harden SSH
sudo sed -i 's/#PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
echo "PubkeyAuthentication yes" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd

# Enable UFW firewall
sudo ufw enable
sudo ufw allow 22/tcp  # SSH
sudo ufw allow 80/tcp  # HTTP
sudo ufw allow 443/tcp # HTTPS

# Create application user
sudo useradd -m -s /usr/sbin/nologin -d /var/lib/justnews justnews-app

# Create required directories
sudo mkdir -p /etc/justnews /var/lib/justnews /var/log/justnews
sudo chown justnews-app:justnews-app /var/lib/justnews /var/log/justnews
sudo chmod 700 /etc/justnews /var/lib/justnews /var/log/justnews

# Install CUDA/GPU drivers (if GPU host)
# Follow: https://docs.nvidia.com/cuda/cuda-installation-guide-linux/
```

**Verification:**
```bash
✓ sudo -l  # Non-sudo user created
✓ ssh-keygen -t ed25519  # SSH key working
✓ nvidia-smi  # GPU detected
✓ sudo ufw status  # Firewall active
```

### Step 3: Install & Configure Container Runtime

**For Docker (if using for auxiliary services):**

```bash
# Install Docker
sudo apt install -y docker.io docker-compose

# Configure Docker
sudo usermod -aG docker justnews-app
sudo systemctl enable docker
sudo systemctl start docker

# Verify
docker ps -q
```

### Step 4: Install & Configure Systemd

**Systemd will manage services, not Docker Compose in production**

```bash
# Verify systemd
systemctl --version

# Create systemd directory (if needed)
sudo mkdir -p /etc/systemd/system

# (Systemd services will be deployed in Step 6)
```

**Verification Checklist:**
- [ ] Host provisioned with sufficient resources
- [ ] OS hardened (SSH, firewall)
- [ ] Application user created
- [ ] Directory structure ready
- [ ] GPU drivers installed (if applicable)
- [ ] Docker running (if using auxiliary containers)
- [ ] Systemd operational

**Sign-off:** Infrastructure Lead: ____________ Time: _______

---

## Vault Setup

### Step 1: Vault Server Installation & Configuration

**Prerequisites:**
- Vault server already deployed (separate infrastructure)
- Vault is unsealed and healthy
- Vault TLS configured with trusted certificate

**Verification:**
```bash
# From production host
curl -k https://vault.prod.internal:8200/v1/sys/health | jq .
# Expected: "initialized": true, "sealed": false
```

### Step 2: Create Service Account in Vault

**For AppRole Authentication (if not using Kubernetes):**

```bash
# On Vault server (requires admin access)
vault auth enable approle  # (if not already enabled)

# Create role for production app
vault write auth/approle/role/justnews-prod \
  bind_secret_ids=true \
  secret_id_ttl=0 \
  token_ttl=1h \
  token_max_ttl=24h \
  policies="prod/justnews"

# Generate credentials
vault read auth/approle/role/justnews-prod/role-id
# Save: VAULT_ROLE_ID

vault write -f auth/approle/role/justnews-prod/secret-id
# Save: VAULT_SECRET_ID (KEEP SECURE - regenerate after first use)

# Verify
vault read auth/approle/role/justnews-prod
```

**For Kubernetes Authentication (if using K8s):**

```bash
# Requires: K8s service account, RBAC setup
vault auth enable kubernetes  # (if not already enabled)

vault write auth/kubernetes/config \
  host=https://kubernetes.default.svc.cluster.local:443 \
  token_reviewer_jwt="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
  kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt

vault write auth/kubernetes/role/justnews-prod \
  bound_service_account_names=justnews \
  bound_service_account_namespaces=prod \
  policies="prod/justnews" \
  ttl=1h
```

### Step 3: Create secrets in Vault

**Create all required production secrets:**

```bash
# Database credentials
vault write secret/data/prod/mariadb \
  password="$(openssl rand -base64 32)" \
  replication_password="$(openssl rand -base64 32)" \
  root_password="$(openssl rand -base64 32)"

# Encryption keys
vault write secret/data/prod/encryption \
  key="$(openssl rand -hex 32)"

# HuggingFace token
vault write secret/data/prod/huggingface \
  token="hf_xxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Django settings
vault write secret/data/prod/django \
  secret_key="$(openssl rand -base64 64)" \
  allowed_hosts="justnews.example.com,api.justnews.example.com"

# JWT secrets
vault write secret/data/prod/jwt \
  secret="$(openssl rand -base64 64)" \
  expiry_hours=24

# Email configuration
vault write secret/data/prod/email \
  user="noreply@justnews.example.com" \
  password="smtp_password_here"

# Third-party integrations
vault write secret/data/prod/sentry \
  dsn="https://xxx@sentry.io/project"

vault write secret/data/prod/datadog \
  api_key="datadog_api_key_here" \
  app_key="datadog_app_key_here"

vault write secret/data/prod/slack \
  webhook_url="https://hooks.slack.com/..."

vault write secret/data/prod/pagerduty \
  integration_key="pagerduty_key_here"
```

### Step 4: Create Vault Policy

```bash
# Create policy for production app
vault policy write prod/justnews - <<EOF
# Allow reading production secrets
path "secret/data/prod/*" {
  capabilities = ["read", "list"]
}

# Allow reading secret metadata (for rotation checks)
path "secret/metadata/prod/*" {
  capabilities = ["read", "list"]
}

# Allow token self-renewal
path "auth/token/renew-self" {
  capabilities = ["update"]
}

# Allow token lookup
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
EOF

# Verify
vault policy read prod/justnews
```

**Verification Checklist:**
- [ ] Vault server healthy and unsealed
- [ ] Service account created (AppRole or K8s)
- [ ] All required secrets created
- [ ] Policy configured with least-privilege grants
- [ ] Credentials securely stored (not in git)

**Sign-off:** Security Lead: ____________ Time: _______

---

## Secrets Management

### Step 1: Prepare Environment Files

**On production host:**

```bash
# Create secrets directory
sudo mkdir -p /etc/justnews
sudo chown justnews-app:justnews-app /etc/justnews
sudo chmod 700 /etc/justnews

# Verify directory
ls -la /etc/justnews
```

### Step 2: Create Fetch Secrets Script

**Create `/etc/justnews/fetch_secrets_to_env.sh`:**

```bash
#!/bin/bash
# Script to fetch secrets from Vault and populate .env.prod

set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-https://vault.prod.internal:8200}"
VAULT_NAMESPACE="${VAULT_NAMESPACE:-prod}"
VAULT_AUTH_METHOD="${VAULT_AUTH_METHOD:-approle}"
ENV_FILE="/etc/justnews/.env.prod"

echo "Fetching secrets from Vault..."

# Authenticate
if [ "$VAULT_AUTH_METHOD" = "approle" ]; then
    TOKEN=$(curl -s -X POST "$VAULT_ADDR/v1/auth/approle/login" \
      -d "{\"role_id\":\"$VAULT_ROLE_ID\",\"secret_id\":\"$VAULT_SECRET_ID\"}" | \
      jq -r '.auth.client_token')
else
    TOKEN=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)
fi

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo "✗ Failed to authenticate with Vault"
    exit 1
fi

echo "✓ Authenticated with Vault"

# Fetch and generate .env.prod
cat > "$ENV_FILE" <<ENVEOF
# Production Environment Configuration
# Generated from Vault on: $(date -u +%Y-%m-%dT%H:%M:%SZ)
# DO NOT EDIT MANUALLY - regenerate using this script

DEBUG=false
LOG_LEVEL=WARNING
ENVIRONMENT=production
RUN_HOST=0.0.0.0
RUN_PORT=8000

# Database
MARIADB_HOST=mariadb.prod.internal
MARIADB_PORT=3306
MARIADB_USER=justnews_prod
MARIADB_PASSWORD=$(curl -s -H "X-Vault-Token: $TOKEN" \
  "$VAULT_ADDR/v1/secret/data/prod/mariadb" | \
  jq -r '.data.data.password')
MARIADB_DB=justnews_prod

# And so on for all other secrets...
ENVEOF

# Verify
if grep -q 'MARIADB_PASSWORD=' "$ENV_FILE"; then
    echo "✓ Environment file generated successfully"
else
    echo "✗ Failed to generate environment file"
    exit 1
fi

# Set permissions
chmod 600 "$ENV_FILE"

echo "✓ Secrets management ready"
```

### Step 3: Run Fetch Script

```bash
# Set Vault credentials
export VAULT_ROLE_ID="your_role_id_here"
export VAULT_SECRET_ID="your_secret_id_here"

# Run script
bash /etc/justnews/fetch_secrets_to_env.sh

# Verify
ls -la /etc/justnews/.env.prod
grep -c '^\[A-Z_\]*=' /etc/justnews/.env.prod  # Should show ~85 variables
```

**Verification Checklist:**
- [ ] Vault secrets directory created with 700 permissions
- [ ] Fetch script in place and executable
- [ ] Script successfully generates `.env.prod`
- [ ] All secrets interpolated (no `${VAULT_*}` remaining)
- [ ] File permissions 600 (read-only by owner)
- [ ] No plaintext passwords in scripts

**Sign-off:** Security Lead: ____________ Time: _______

---

## Service Deployment

### Step 1: Clone Application Repository

```bash
# Clone from git
cd /var/lib/justnews
sudo -u justnews-app git clone https://github.com/Adrasteon/justnewsA0 .

# Verify
ls -la /var/lib/justnews/.git
```

### Step 2: Install Python Dependencies

```bash
# Create virtual environment
cd /var/lib/justnews
sudo -u justnews-app python3.10 -m venv /var/lib/justnews/venv

# Install dependencies
sudo -u justnews-app /var/lib/justnews/venv/bin/pip install -r requirements-bootstrap.txt
```

### Step 3: Create Systemd Service Files

**`/etc/systemd/system/justnews-chromadb.service`:**

```ini
[Unit]
Description=ChromaDB Vector Database for JustNews
After=network-online.target
Wants=network-online.target
Documentation=https://docs.trychroma.com

[Service]
Type=simple
User=justnews-app
Group=justnews-app
WorkingDirectory=/var/lib/justnews
Environment="PATH=/var/lib/justnews/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
EnvironmentFile=/etc/justnews/.env.prod

ExecStart=/var/lib/justnews/venv/bin/python -m chromadb.server \
  --host 127.0.0.1 \
  --port 3307 \
  --no-auth

Restart=on-failure
RestartSec=10s
StartLimitSequence=5
StartLimitBurst=3
StartLimitIntervalSec=60s

# Security
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/chromadb

# Resource limits
MemoryLimit=6G
CPUQuota=200%
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/justnews-vllm.service`:**

```ini
[Unit]
Description=vLLM Language Model Server for JustNews
After=network-online.target chromadb.service
Wants=network-online.target
Requires=chromadb.service
Documentation=https://docs.vllm.ai

[Service]
Type=simple
User=justnews-app
Group=justnews-app
WorkingDirectory=/var/lib/justnews
Environment="PATH=/var/lib/justnews/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
Environment="CUDA_VISIBLE_DEVICES=0"
EnvironmentFile=/etc/justnews/.env.prod

ExecStart=/var/lib/justnews/venv/bin/python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-14B-Instruct-AWQ \
  --host 127.0.0.1 \
  --port 8001 \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.85 \
  --max-num-seqs 10 \
  --disable-log-requests \
  --disable-log-stats

TimeoutStartSec=300
Restart=on-failure
RestartSec=30s
StartLimitSequence=3
StartLimitBurst=2
StartLimitIntervalSec=120s

# Security
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes

# Resource limits
MemoryLimit=30G
CPUQuota=400%
LimitNOFILE=65536

# GPU access
DeviceAccess=/dev/nvidia* /dev/nvidiactl /dev/nvidia-devctl

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/justnews-app.service`:**

```ini
[Unit]
Description=JustNews Web Application
After=network-online.target chromadb.service vllm.service mariadb.service
Wants=network-online.target
Requires=chromadb.service vllm.service
Documentation=https://github.com/Adrasteon/justnewsA0

[Service]
Type=notify
User=justnews-app
Group=justnews-app
WorkingDirectory=/var/lib/justnews
Environment="PATH=/var/lib/justnews/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=/etc/justnews/.env.prod

ExecStartPre=/var/lib/justnews/venv/bin/python manage.py migrate
ExecStart=/var/lib/justnews/venv/bin/gunicorn \
  --workers 4 \
  --worker-class sync \
  --worker-tmp-dir /dev/shm \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  --log-level warning \
  --bind 0.0.0.0:8000 \
  justnews_publisher.wsgi:application

TimeoutStartSec=60
TimeoutStopSec=10
Restart=on-failure
RestartSec=10s
StartLimitSequence=5
StartLimitBurst=3
StartLimitIntervalSec=60s

# Security
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/justnews /var/log/justnews

# Resource limits
MemoryLimit=2G
CPUQuota=200%
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

### Step 4: Install Systemd Services

```bash
# Copy service files (already created above)
# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable justnews-chromadb.service
sudo systemctl enable justnews-vllm.service
sudo systemctl enable justnews-app.service

# Verify services are registered
sudo systemctl list-unit-files | grep justnews
```

### Step 5: Start Services in Order

```bash
 # Start ChromaDB first
sudo systemctl start justnews-chromadb.service

# Wait for ChromaDB to be ready
sleep 5

# Verify ChromaDB
sudo systemctl status justnews-chromadb.service

# Start vLLM
echo "Starting vLLM... (this may take 2-5 minutes for model loading)"
sudo systemctl start justnews-vllm.service

# Monitor vLLM startup
for i in {1..60}; do
    if curl -s http://localhost:8001/v1/models >/dev/null 2>&1; then
        echo "✓ vLLM ready"
        break
    fi
    echo "⏳ Waiting for vLLM... ($i/60)"
    sleep 5
done

# Start application
sudo systemctl start justnews-app.service

# Wait for app to be ready
sleep 5

# Verify all services
sudo systemctl status justnews-app.service
sudo systemctl status justnews-vllm.service
sudo systemctl status justnews-chromadb.service
```

**Verification Checklist:**
- [ ] All services started without errors
- [ ] ChromaDB responding on 3307
- [ ] vLLM responding on 8001 (model loaded)
- [ ] App responding on 8000
- [ ] All services have correct status
- [ ] No restart loops in logs

**Sign-off:** Infrastructure Lead: ____________ Time: _______

---

## Post-Deployment Validation

### Step 1: Health Check Endpoints

```bash
# ChromaDB health
curl -s http://localhost:3307 | jq .

# vLLM health
curl -s http://localhost:8001/v1/models | jq .

# App health
curl -s http://localhost:8000/health | jq .

# Expected: All return 200 with data
```

### Step 2: Smoke Tests

```bash
# Run integration tests
cd /var/lib/justnews
/var/lib/justnews/venv/bin/pytest tests/integration/test_devcontainer.py -v

# All tests should pass
```

### Step 3: Database Check

```bash
# Verify database connectivity
source /etc/justnews/.env.prod

mysql -h $MARIADB_HOST -u $MARIADB_USER -p"$MARIADB_PASSWORD" \
  -e "USE $MARIADB_DB; SELECT COUNT(*) as table_count FROM information_schema.tables;"

# Should return count without errors
```

### Step 4: Service Log Review

```bash
# Check for errors
sudo journalctl -u justnews-app.service -n 50
sudo journalctl -u justnews-vllm.service -n 50
sudo journalctl -u justnews-chromadb.service -n 50

# Look for ERROR or CRITICAL messages
```

**Verification Checklist:**
- [ ] All health endpoints returning 200
- [ ] Integration tests passing
- [ ] Database accessible and functional
- [ ] Service logs show no errors
- [ ] All services running for >2 minutes

**Sign-off:** Operations Lead: ____________ Time: _______

---

## Monitoring & Alerting

### Step 1: Configure Monitoring (Prometheus/Grafana - Optional)

```bash
# Install Prometheus (if not already installed)
sudo apt install -y prometheus grafana-server

# Create Prometheus scrape config for vLLM
cat | sudo tee -a /etc/prometheus/prometheus.yml <<EOF

  - job_name: 'vllm'
    static_configs:
      - targets: ['localhost:8001']
        
  - job_name: 'app'
    static_configs:
      - targets: ['localhost:8000']
EOF

# Restart Prometheus
sudo systemctl restart prometheus

# Verify
curl http://localhost:9090/api/v1/query?query=up
```

### Step 2: Configure Sentry (Error Tracking)

```bash
# Verify Sentry DSN in environment
grep SENTRY_DSN /etc/justnews/.env.prod

# Test error tracking (if available)
curl -X POST http://localhost:8000/test-sentry
```

### Step 3: Configure Logging

```bash
# Verify centralized logging (if configured)
tail -f /var/log/justnews/app.log

# Expected: JSON formatted logs with timestamps
```

### Step 4: Set Up Alerting

**Email alerts (basic):**

```bash
# Install postfix for email
sudo apt install -y postfix

# Configure systemd timer to monitor services
cat | sudo tee /etc/systemd/system/justnews-monitor.service <<EOF
[Unit]
Description=JustNews Service Monitor
After=justnews-app.service

[Service]
Type=simple
ExecStart=/opt/justnews/monitor.sh

Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
```

**Verification Checklist:**
- [ ] Monitoring system configured
- [ ] Metrics being collected
- [ ] Dashboards accessible
- [ ] Alerting channels active (email, Slack, PagerDuty)
- [ ] Test alert successful

**Sign-off:** Operations Lead: ____________ Time: _______

---

## Troubleshooting

### Common Issues During Deployment

**Issue: Service fails to start**
```bash
# Check logs
sudo journalctl -u justnews-app.service -n 100

# Check configuration
sudo systemctl status justnews-app.service

# Restart
sudo systemctl restart justnews-app.service
```

**Issue: vLLM model loading timeout**
```bash
# Increase timeout in service file
# TimeoutStartSec=600 (10 minutes max)

# Check GPU memory
nvidia-smi

# Monitor loading
sudo tail -f /var/log/justnews/vllm.log
```

**Issue: Database connection refused**
```bash
# Verify MariaDB host and port
echo $MARIADB_HOST $MARIADB_PORT

# Test connectivity
mysql -h $MARIADB_HOST -P $MARIADB_PORT -u $MARIADB_USER -p"$MARIADB_PASSWORD" -e "SELECT 1;"
```

For more issues, see: [SERVICE_OPERATIONS.md](docs/operations/SERVICE_OPERATIONS.md)

---

## Rollback Procedures

### Emergency Rollback (Service Down)

```bash
# Stop all services
sudo systemctl stop justnews-app.service
sudo systemctl stop justnews-vllm.service
sudo systemctl stop justnews-chromadb.service

# Restore previous version
cd /var/lib/justnews
git reset --hard HEAD~1

# Restart
sudo systemctl start justnews-chromadb.service
sleep 10
sudo systemctl start justnews-vllm.service
sleep 30
sudo systemctl start justnews-app.service

# Verify
curl http://localhost:8000/health
```

### Database Rollback

```bash
# Restore from backup (requires backup infrastructure)
# Reference: PRODUCTION_READINESS.md - Rollback section
```

### Full Rollback (If production deployment failed)

1. Stop all services: `sudo systemctl stop justnews-*.service`
2. Restore previous version from git/backup
3. Restore database from backup
4. Verify all services
5. Document rollback reason
6. Schedule post-mortem

**Rollback Approved By:** ____________ Time: _______ Reason: _____________

---

## Post-Deployment Stabilization (Days 1-7)

### Day 1: Intensive Monitoring
- Monitor all services 24/7
- Log all issues
- Verify alerts working
- Test incident response

### Days 2-5: Performance Tuning
- Analyze slow queries
- Review resource utilization
- Optimize configuration
- Fix minor issues

### Days 6-7: Handoff to Operations
- Complete documentation
- Train ops team
- Finalize runbooks
- Declare "production stable"

---

## Sign-Off & Approval

**Deployment completed and verified.**

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Infrastructure Lead | _________ | _____ | _________ |
| Security Lead | _________ | _____ | _________ |
| Database Admin | _________ | _____ | _________ |
| Operations Lead | _________ | _____ | _________ |

**Deployment Status:** ✅ COMPLETE and OPERATIONAL

**Go-Live Date:** _____________

**Estimated Time to Full Stability:** 7 days

