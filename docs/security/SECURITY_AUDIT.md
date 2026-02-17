# Production Security Audit Checklist
## For Pre-Deployment Validation

**Document Version:** 1.0  
**Last Updated:** 2024  
**Frequency:** Before each production deployment  
**Owner:** Security Team + DevOps Lead  

---

## Pre-Audit Requirements

- [ ] **Deployment plan approved** by Security Lead
- [ ] **All infrastructure services running** properly
- [ ] **Vault integration tested** and operational
- [ ] **TLS certificates installed** and valid
- [ ] **Backup procedures tested** successfully
- [ ] **Network connectivity verified** for all services

**Prerequisite Check Script:**
```bash
# Run before starting audit
infrastructure/scripts/pre-audit-check.sh
```

---

## 1. File System Security

### 1.1 Configuration Files

- [ ] **Verify file permissions for secrets:**
  ```bash
  stat /etc/justnews/.env.prod
  # Expected: -rw------- (0600) owned by justnews-app:justnews-app
  ```
  - [ ] File mode is exactly `600` (readable/writable by owner only)
  - [ ] Owner is `justnews-app` user
  - [ ] Group is `justnews-app` group
  - [ ] No other users have read access

- [ ] **Check for plaintext secrets in files:**
  ```bash
  grep -E 'PASSWORD|API_KEY|SECRET|TOKEN' /etc/justnews/.env.prod | grep -v '\$VAULT'
  # Should return NO results (all should use $VAULT references)
  ```
  - [ ] No hardcoded passwords found
  - [ ] No API keys in plaintext
  - [ ] No encryption keys in files
  - [ ] All secrets use `${VAULT_*}` references

- [ ] **Verify no secrets in application code:**
  ```bash
  git log --all -i -S 'password=' -- '*.py' | head -20
  # Should return very old commits (if any)
  ```
  - [ ] No recent commits with hardcoded credentials
  - [ ] Review any secrets found with team lead

### 1.2 Application Directory

- [ ] **Verify application directory ownership:**
  ```bash
  stat /app
  # Expected: drwxr-xr-x owned by justnews-app
  ```
  - [ ] Owner is `root` or `justnews-app`
  - [ ] Permissions allow service read/write (755 or 750)
  - [ ] No world-writable directories

- [ ] **Check database backups location:**
  ```bash
  stat /var/backups/justnews/ 2>/dev/null || echo "Path not yet created"
  ```
  - [ ] Backups stored outside application directory
  - [ ] Backup directory permissions are `700`
  - [ ] Only backup user + root can access

- [ ] **Verify log directory permissions:**
  ```bash
  stat /var/log/justnews/
  ```
  - [ ] Log directory owner is `justnews-app`
  - [ ] Permissions are `750` (no world read)
  - [ ] Log files are `640` (no world read)

### 1.3 System-wide File Integrity

- [ ] **Enable file monitoring (if auditd available):**
  ```bash
  sudo auditctl -w /etc/justnews/ -p wa -k justnews_config
  sudo auditctl -w /app/ -p wa -k justnews_app
  ```
  - [ ] Configuration files are monitored for writes
  - [ ] Application files are monitored for writes
  - [ ] Audit logs are being collected

---

## 2. Network & Connectivity Security

### 2.1 Service Network Isolation

- [ ] **Verify internal Docker network:**
  ```bash
  docker network ls | grep justnews
  docker network inspect justnews-network | grep Subnet
  ```
  - [ ] Internal network exists (should be 172.18.0.0/16 or similar)
  - [ ] All services connected to internal network
  - [ ] Network is not accessible from host

- [ ] **Check exposed ports (should be minimal):**
  ```bash
  sudo netstat -tulpn | grep -E ':(8000|8001|3306|3307)'
  # or: docker ps --format "table {{.Names}}\t{{.Ports}}"
  ```
  - [ ] Only necessary ports exposed
  - [ ] SSH only: port 22 open
  - [ ] Web API: port 8000 (reverse proxy only)
  - [ ] No direct vLLM/ChromaDB/MariaDB ports exposed
  - [ ] All internal services on 127.0.0.1 or internal network

- [ ] **Verify no unnecessary listening ports:**
  ```bash
  sudo netstat -tulpn | grep LISTEN | wc -l
  # Should be minimal (typically < 10)
  ```
  - [ ] List all listening ports
  - [ ] Verify each port is intentional
  - [ ] Document any unexpected listeners

### 2.2 DNS & Service Discovery

- [ ] **Verify all service hostnames resolve:**
  ```bash
  for host in mariadb.prod.internal chromadb.prod.internal vllm.prod.internal; do
    nslookup $host
  done
  ```
  - [ ] MariaDB hostname resolves correctly
  - [ ] ChromaDB hostname resolves correctly
  - [ ] vLLM hostname resolves correctly
  - [ ] DNS configured in /etc/resolv.conf or Docker

- [ ] **Check reverse DNS (if applicable):**
  ```bash
  nslookup $(hostname -I)
  ```
  - [ ] Reverse DNS lookup works (optional but recommended)

### 2.3 Network Policies

- [ ] **Verify firewall rules (UFW/iptables):**
  ```bash
  sudo ufw status
  # or: sudo iptables -L -n
  ```
  - [ ] Inbound SSH (22) allowed from trusted IPs
  - [ ] Inbound HTTP/HTTPS (80/443) allowed
  - [ ] All other inbound traffic blocked by default
  - [ ] Outbound HTTPS allowed for HuggingFace, Vault
  - [ ] No unnecessary service ports exposed

- [ ] **Check VPN/Bastion requirements:**
  - [ ] SSH key-based auth (no passwords)
  - [ ] MFA enabled for all human access
  - [ ] Bastion host for production access
  - [ ] Jump-through-host documented

---

## 3. Access Control & Authentication

### 3.1 Operating System Access

- [ ] **Verify user accounts:**
  ```bash
  getent passwd | grep -E 'justnews|root|admin'
  ```
  - [ ] `justnews-app` service user exists
  - [ ] Service user has no shell (`/usr/sbin/nologin`)
  - [ ] Service user has no sudo access
  - [ ] Dedicated ops user (if applicable) for manual access

- [ ] **Check SSH configuration:**
  ```bash
  sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication'
  ```
  - [ ] Root SSH login disabled: `PermitRootLogin no`
  - [ ] Password authentication disabled: `PasswordAuthentication no`
  - [ ] Key-based auth only (no passwords)
  - [ ] MFA/2FA enabled in PAM
  - [ ] SSH runs on non-standard port (22 acceptable if firewalled)

- [ ] **Verify sudo access:**
  ```bash
  sudo visudo -c  # syntax check
  sudo grep -E '^%|^justnews' /etc/sudoers.d/*
  ```
  - [ ] Only necessary users in sudoers
  - [ ] All sudo commands logged
  - [ ] Ops team has minimal sudo scope
  - [ ] Password required for sudo
  - [ ] NOPASSWD entries reviewed and justified

### 3.2 API Authentication

- [ ] **Verify API key validation:**
  ```bash
  curl -X GET http://localhost:8000/api/status -H "X-API-Key: invalid" -w "\nHTTP %{http_code}\n"
  # Expected: 401 Unauthorized or similar rejection
  ```
  - [ ] Invalid API key rejected
  - [ ] API requires valid key for protected endpoints
  - [ ] API keys rotated regularly
  - [ ] API key generation logged and audited

- [ ] **Check rate limiting enforcement:**
  ```bash
  for i in {1..150}; do
    curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/resources
  done | sort | uniq -c
  # Should show 429 (Too Many Requests) in response codes
  ```
  - [ ] Rate limiting is active
  - [ ] Lock-out response is 429
  - [ ] Client receives Retry-After header
  - [ ] Rate limit whitelist configured

### 3.3 Database Access Control

- [ ] **Verify database user privileges:**
  ```bash
  mysql -h mariadb -u root -p$MARIADB_ROOT_PASSWORD -e "SELECT User, Host, Super_priv FROM mysql.user \G"
  ```
  - [ ] `justnews_prod` user exists
  - [ ] User NOT a Super_grantee (no GRANT privilege)
  - [ ] User has only required database access
  - [ ] No remote root access (root@localhost only)
  - [ ] No anonymous users

- [ ] **Check database query logging:**
  ```bash
  mysql -h mariadb -u root -p$MARIADB_ROOT_PASSWORD -e "SHOW VARIABLES LIKE 'log_%';"
  ```
  - [ ] General query log enabled (or slow query log)
  - [ ] Log rotation configured
  - [ ] Sensitive statements (passwords) masked in logs

### 3.4 Service-to-Service Authentication

- [ ] **Verify ChromaDB authentication:**
  - [ ] ChromaDB auth token set in environment
  - [ ] Token verified in ChromaDB logs
  - [ ] Token not logged in application logs
  - [ ] Token rotated regularly

- [ ] **Check vLLM authentication (if required):**
  - [ ] vLLM running with auth (if applicable)
  - [ ] Authentication method documented
  - [ ] No direct unauthenticated API exposure

---

## 4. Transport Security (TLS/HTTPS)

### 4.1 Certificate Installation

- [ ] **Verify TLS certificates:**
  ```bash
  openssl x509 -in /etc/justnews/certs/server.crt -text -noout
  ```
  - [ ] Certificate file exists and is readable
  - [ ] Certificate is valid (not self-signed unless internal)
  - [ ] Common Name (CN) matches domain
  - [ ] Subject Alternative Names (SAN) include all hostnames
  - [ ] Certificate expiry > 30 days: `notAfter` field
  - [ ] Certificate chain valid: `openssl verify` succeeds

- [ ] **Check certificate key permissions:**
  ```bash
  stat /etc/justnews/certs/server.key
  ```
  - [ ] Key file permissions are `600` (read-only by owner)
  - [ ] Key owner is root or justnews-app
  - [ ] Key is not world-readable
  - [ ] Key matches certificate

- [ ] **Verify CA certificate:**
  ```bash
  stat /etc/justnews/certs/ca.crt
  openssl verify -CAfile /etc/justnews/certs/ca.crt /etc/justnews/certs/server.crt
  ```
  - [ ] CA certificate file exists
  - [ ] CA file is readable by application
  - [ ] Certificate validates against CA
  - [ ] CA certificate is current (not expired)

### 4.2 TLS Configuration

- [ ] **Check TLS version and ciphers:**
  ```bash
  openssl s_client -connect localhost:8000 -tls1_2 </dev/null
  # Should connect successfully; try -tls1_0 (should fail)
  ```
  - [ ] TLS 1.2+ required (TLS 1.0/1.1 disabled)
  - [ ] Strong ciphers enabled (no weak ciphers like DES, MD5)
  - [ ] Forward secrecy enabled (ECDHE preferred)
  - [ ] HSTS header present: `Strict-Transport-Security`

- [ ] **Verify HTTPS enforcement:**
  ```bash
  curl -i http://localhost:8000/ 2>/dev/null | grep -i location
  # Should redirect to https
  ```
  - [ ] HTTP requests redirect to HTTPS
  - [ ] HSTS header enforces future HTTPS
  - [ ] HSTS max-age >= 31536000 (1 year)

### 4.3 Service-to-Service TLS

- [ ] **Verify database TLS (if enforced):**
  ```bash
  mysql -h mariadb -u root -p$MARIADB_ROOT_PASSWORD -e "SHOW VARIABLES LIKE 'require_secure_transport';"
  ```
  - [ ] Secure transport required: ON
  - [ ] Local socket connections allowed (if needed)
  - [ ] Remote connections require TLS

- [ ] **Check application-ChromaDB TLS:**
  - [ ] ChromaDB traffic encrypted (if over network)
  - [ ] Application verifies ChromaDB certificate (if TLS enforced)

---

## 5. Data Protection & Encryption

### 5.1 Encryption at Rest

- [ ] **Verify database encryption:**
  ```bash
  mysql -h mariadb -u root -p$MARIADB_ROOT_PASSWORD -e "SHOW VARIABLES LIKE 'encrypted%';"
  ```
  - [ ] Encryption enabled (if using InnoDB with options)
  - [ ] Encryption key set in configuration
  - [ ] Encryption covers all sensitive data

- [ ] **Check application-level encryption:**
  - [ ] Encryption key from Vault (not in code)
  - [ ] Algorithm: AES-256-GCM
  - [ ] Key rotation policy documented
  - [ ] Encrypted fields clearly documented

### 5.2 Backup Encryption

- [ ] **Verify backup encryption setup:**
  ```bash
  ls -la /var/backups/justnews/
  file /var/backups/justnews/*.backup*
  ```
  - [ ] Backup files exist
  - [ ] Backup files are encrypted (use `file` to verify)
  - [ ] Encryption key stored separately from backups
  - [ ] Backup retention policy enforced

- [ ] **Test backup restoration:**
  ```bash
  # Attempt restore to staging environment
  infrastructure/scripts/restore-from-backup.sh --backup latest --environment staging
  ```
  - [ ] Restore script executes without errors
  - [ ] Restored database validates checksums
  - [ ] Data integrity verified post-restore

### 5.3 Secret Rotation

- [ ] **Check secret rotation schedule:**
  ```bash
  vault policy read /policies/prod/rotate-secrets.hcl
  # or check: grep -i rotation infrastructure/scripts/rotate-secrets.sh
  ```
  - [ ] Rotation schedule documented (e.g., every 90 days)
  - [ ] Rotation script tested successfully
  - [ ] Automated rotation triggers (if possible)
  - [ ] Manual rotation documented with clear steps

- [ ] **Verify no hardcoded secrets anywhere:**
  ```bash
  # Search codebase for secrets
  git log --all -i -S 'VAULT_MARIADB_PASSWORD' --oneline
  grep -r '\$VAULT_' /app --include='*.py' --include='*.sh' | grep -v 'environment'
  ```
  - [ ] All secrets use environment variable references
  - [ ] No secrets in git history (or marked as false positive)
  - [ ] Old commits with secrets reviewed and noted

---

## 6. Logging & Audit Trail

### 6.1 Application Logging

- [ ] **Verify log files exist and are rotating:**
  ```bash
  ls -la /var/log/justnews/
  tail -20 /var/log/justnews/app.log
  ```
  - [ ] Log files exist for all services
  - [ ] Log files are JSON formatted (if configured)
  - [ ] Logs are readable and recent
  - [ ] Log files have proper permissions (640)

- [ ] **Check log rotation configuration:**
  ```bash
  cat /etc/logrotate.d/justnews
  ```
  - [ ] Log rotation configured (daily, weekly, or size-based)
  - [ ] Old logs compressed
  - [ ] Retention policy enforced (e.g., 30+ days)
  - [ ] Post-rotation script runs (e.g., service restart if needed)

- [ ] **Verify centralized logging (if configured):**
  - [ ] Logs forwarded to central server
  - [ ] Central server uses secure transport (TLS)
  - [ ] Logs include timestamps and source identification
  - [ ] Log aggregation working and accessible

### 6.2 Audit Trail

- [ ] **Check database audit logging:**
  ```bash
  mysql -h mariadb -u root -p$MARIADB_ROOT_PASSWORD -e "SHOW VARIABLES LIKE '%audit%';"
  ls -la /var/log/ | grep -i audit
  ```
  - [ ] Audit plugin enabled (if available)
  - [ ] Audit log file created and writable
  - [ ] Sensitive operations logged (DELETE, UPDATE, DROP)
  - [ ] Audit logs not world-readable

- [ ] **Verify Vault audit logging:**
  ```bash
  vault audit list
  ```
  - [ ] Vault audit devices enabled
  - [ ] All secret access logged
  - [ ] Audit logs include who, what, when
  - [ ] Audit logs cannot be modified (immutable)

- [ ] **Check SSH access logging:**
  ```bash
  grep SSH /var/log/auth.log | tail -10
  ```
  - [ ] SSH login attempts logged
  - [ ] Successful and failed logins recorded
  - [ ] Logs include timestamp and source IP
  - [ ] Failed attempts trigger alerting (if configured)

### 6.3 API Request Logging

- [ ] **Verify API request logging is enabled:**
  ```bash
  grep -i 'log.*request' /var/log/justnews/app.log | head -5
  ```
  - [ ] API requests logged with method, path, status, duration
  - [ ] User/client identification in logs
  - [ ] Sensitive parameters masked in logs (passwords, tokens)
  - [ ] Error requests logged with full stack trace

---

## 7. Secrets Management (Vault Integration)

### 7.1 Vault Configuration

- [ ] **Verify Vault connection:**
  ```bash
  curl -s https://vault.prod.internal:8200/v1/sys/health | jq
  # Expected: "initialized": true, "sealed": false, "standby": false
  ```
  - [ ] Vault server responding on correct address
  - [ ] Vault is unsealed and operational
  - [ ] Vault not in standby mode
  - [ ] TLS certificate valid

- [ ] **Check Vault authentication:**
  ```bash
  vault auth list
  vault auth show kubernetes (or approle, etc.)
  ```
  - [ ] Authentication method enabled (Kubernetes preferred in prod)
  - [ ] Service account bound correctly
  - [ ] Auth method has appropriate TTL settings
  - [ ] No default/deprecated auth methods enabled

### 7.2 Secret Policies

- [ ] **Verify policy assignments:**
  ```bash
  vault token lookup
  vault policy list
  vault policy read prod/justnews-prod-policy
  ```
  - [ ] Service account has correct policy attached
  - [ ] Policy grants read access to required secrets
  - [ ] Policy does NOT grant write/delete/sudo access
  - [ ] Policy includes TTL settings
  - [ ] Policies are least-privilege

- [ ] **Check secret engine configuration:**
  ```bash
  vault secrets list
  vault secrets list secret/prod/
  ```
  - [ ] KV 2.0 secrets engine (recommended over 1.0)
  - [ ] Secrets stored in predictable paths
  - [ ] Metadata and version history tracked
  - [ ] Appropriate TTL settings

### 7.3 Secret Retrieval

- [ ] **Test secret fetch script:**
  ```bash
  infrastructure/scripts/fetch_secrets_to_env.sh --dry-run
  # Should print what would be fetched without writing
  infrastructure/scripts/fetch_secrets_to_env.sh
  # Should successfully populate /etc/justnews/.env.prod
  ```
  - [ ] Script runs without errors
  - [ ] All required secrets retrieved
  - [ ] Environment variables properly formatted
  - [ ] File permissions reset to 600 after write
  - [ ] Script is idempotent (safe to run multiple times)

- [ ] **Verify secret retrieval audit:**
  ```bash
  vault audit logs show secret/prod/
  # or check logs manually
  ```
  - [ ] Secret access logged in Vault audit
  - [ ] Service account logged as accessor
  - [ ] Timestamp and method recorded
  - [ ] No secrets printed in logs

---

## 8. Service Operational Security

### 8.1 Service Configuration

- [ ] **Verify service startup files:**
  ```bash
  systemctl status justnews-app
  systemctl cat justnews-app.service | grep -E 'User=|ProtectSystem=|NoNewPrivileges='
  ```
  - [ ] Service runs as `justnews-app` (not root)
  - [ ] `ProtectSystem=strict` or similar hardening enabled
  - [ ] `NoNewPrivileges=yes` set
  - [ ] `PrivateTmp=yes` (isolated /tmp)
  - [ ] `ReadOnlyPaths=` configured for sensitive dirs

- [ ] **Check service isolation (AppArmor/SELinux):**
  ```bash
  aa-status | grep -i justnews  # AppArmor
  getenforce  # SELinux (should be Enforcing or Permissive in prod)
  ```
  - [ ] Mandatory access control enabled (AppArmor or SELinux)
  - [ ] Profile/policy for justnews service active
  - [ ] Profile is in Enforce mode (not Complain)
  - [ ] Denials logged and reviewed

### 8.2 Resource Limits

- [ ] **Verify memory and CPU limits:**
  ```bash
  cat /sys/fs/cgroup/memory/docker/*/memory.limit_in_bytes
  # or: docker inspect justnews-app --format '{{.HostConfig.Memory}}'
  ```
  - [ ] App memory limit set (e.g., 2GB)
  - [ ] vLLM memory limit set (e.g., 30GB)
  - [ ] ChromaDB memory limit set (e.g., 6GB)
  - [ ] CPU limits prevent runaway usage

- [ ] **Check process limits:**
  ```bash
  cat /etc/security/limits.conf | grep -i justnews
  # or: ulimit -a (in running context)
  ```
  - [ ] File descriptor limit set appropriately
  - [ ] Process limit set appropriately
  - [ ] Core dump limit disabled (or limited)

### 8.3 Service Dependencies

- [ ] **Verify service startup order (systemd):**
  ```bash
  grep -E '^\[Unit\]|After=|Before=|Requires=' /etc/systemd/system/justnews*.service
  ```
  - [ ] All dependencies declared (`After=`, `Requires=`)
  - [ ] Startup order is correct (DB before app)
  - [ ] Timeout settings appropriate
  - [ ] Restart policies configured

- [ ] **Test graceful shutdown:**
  ```bash
  systemctl stop justnews-app --dry-run
  # Then actually stop
  systemctl stop justnews-app
  sleep 2
  systemctl status justnews-app
  # Expected: service stop complete
  ```
  - [ ] Service shuts down gracefully
  - [ ] No errors logged during shutdown
  - [ ] Connections properly closed
  - [ ] No orphaned processes

---

## 9. Vulnerability & Patch Management

### 9.1 System Packages

- [ ] **Check installed software versions:**
  ```bash
  dpkg -l | grep -E 'openssl|openssh|curl'
  pip list | grep -E 'django|pydantic|cryptography'
  ```
  - [ ] OpenSSL version is current (no known CVEs)
  - [ ] SSH version is current
  - [ ] All critical packages are up-to-date
  - [ ] Known vulnerabilities documented and mitigated

- [ ] **Verify patch management process:**
  - [ ] Patch schedule documented
  - [ ] Testing process for patches defined
  - [ ] Automatic updates configured (if acceptable)
  - [ ] Critical patches prioritized
  - [ ] Security advisories monitored

### 9.2 Application Dependencies

- [ ] **Scan Python packages for vulnerabilities:**
  ```bash
  pip-audit  # if installed
  # or: safety check (legacy)
  ```
  - [ ] No known vulnerabilities in dependencies
  - [ ] Dependency versions frozen in requirements.txt
  - [ ] Last update to dependencies within 90 days
  - [ ] All transitive dependencies reviewed

- [ ] **Check for deprecated libraries:**
  ```bash
  grep -r 'import.*deprecated' /app --include='*.py'
  ```
  - [ ] No deprecated libraries in use
  - [ ] Old imports replaced with modern alternatives
  - [ ] Deprecation warnings addressed

### 9.3 Code Review for Security

- [ ] **Verify recent code reviews included security checks:**
  ```bash
  git log --oneline --all --grep='security\|security review\|CVE' | head -10
  ```
  - [ ] Recent PRs mention security review
  - [ ] Known CVEs addressed
  - [ ] OWASP top 10 considered
  - [ ] Peer review completed before merge

---

## 10. Backup & Disaster Recovery

### 10.1 Backup Configuration

- [ ] **Verify backup schedule:**
  ```bash
  crontab -l | grep backup
  # or: systemctl list-timers | grep backup
  ```
  - [ ] Backups scheduled (daily recommended)
  - [ ] Backup time during low-traffic window
  - [ ] Full backup frequency (weekly or daily)
  - [ ] Incremental backup frequency documented

- [ ] **Check backup location and storage:**
  ```bash
  ls -lh /var/backups/justnews/
  ```
  - [ ] Backups stored on separate system (preferable)
  - [ ] Backup location is not /app (separate from app code)
  - [ ] Backup storage has sufficient disk space
  - [ ] Backups on different physical disk (redundancy)

### 10.2 Backup Verification

- [ ] **Test backup integrity:**
  ```bash
  gzip -t /var/backups/justnews/*.gz  # Test gzip integrity
  # Test restore process
  ```
  - [ ] Backup files are valid and not corrupted
  - [ ] Checksum verification successful
  - [ ] Backup can be extracted without errors
  - [ ] Sample data verified post-extraction

- [ ] **Verify restore capability:**
  ```bash
  # Perform mock restore to staging
  infrastructure/scripts/restore-from-backup.sh --backup latest --environment staging --dry-run
  ```
  - [ ] Restore script successful
  - [ ] Database validates after restore
  - [ ] Data completeness verified
  - [ ] Restore time documented (SLA requirement?)

### 10.3 Recovery Point Objective (RPO)

- [ ] **Verify backup RPO meets requirements:**
  - [ ] Backup frequency: \_\_\_ (e.g., hourly, daily)
  - [ ] Maximum data loss acceptable: \_\_\_ (hours)
  - [ ] Backup schedule meets RPO: ✓ Yes / ✗ No
  - [ ] Monitoring alerts if backup misses window

### 10.4 Recovery Time Objective (RTO)

- [ ] **Verify recovery time is acceptable:**
  ```bash
  # Document recovery time from recent test
  # Restore from backup took: _____ minutes
  # Service recovery took: _____ minutes
  # Total RTO: _____ minutes
  ```
  - [ ] RTO target: \_\_\_ (e.g., < 4 hours)
  - [ ] Actual RTO meets target: ✓ Yes / ✗ No
  - [ ] RTO documented and communicated
  - [ ] Failover procedures updated if necessary

---

## 11. Monitoring & Alerting

### 11.1 Service Monitoring

- [ ] **Verify monitoring is active:**
  ```bash
  curl -s http://localhost:9090/-/healthy  # Prometheus
  # or: systemctl status prometheus
  ```
  - [ ] Monitoring system running
  - [ ] Metrics being collected
  - [ ] Dashboards accessible
  - [ ] Historical metrics retained

- [ ] **Check alert rules:**
  ```bash
  cat /etc/prometheus/rules.d/justnews-alerts.yml
  ```
  - [ ] Alert rules defined for critical metrics
  - [ ] Alert thresholds appropriate
  - [ ] Alert notification channels configured
  - [ ] Test alert successfully triggered and received

### 11.2 Health Check Endpoints

- [ ] **Verify application health check:**
  ```bash
  curl -s http://localhost:8000/health | jq
  ```
  - [ ] Health endpoint responds correctly
  - [ ] Includes all service status
  - [ ] Response time acceptable
  - [ ] Detailed health info available at `/health/detailed`

- [ ] **Test service healthchecks:**
  ```bash
  docker exec mariadb mysqladmin -u root -p$MARIADB_ROOT_PASSWORD ping
  curl -s http://chromadb:8000 | jq '.api_version'
  curl -s http://vllm:8000/v1/models
  ```
  - [ ] MariaDB responds to health check
  - [ ] ChromaDB responds to health check
  - [ ] vLLM responds to health check
  - [ ] Each service has documented health command

### 11.3 Log Monitoring

- [ ] **Verify log aggregation:**
  - [ ] Logs centralized in single system
  - [ ] Search functionality available and fast
  - [ ] Historical logs retained (30+ days)
  - [ ] Log parsing working correctly

- [ ] **Check error alerting:**
  - [ ] Error patterns trigger alerts
  - [ ] Critical errors escalated immediately
  - [ ] Alert log contains recent errors
  - [ ] Noise filtering applied (no alert fatigue)

---

## 12. Security Compliance

### 12.1 Standard Compliance (if applicable)

- [ ] **Check compliance requirements:**
  - [ ] GDPR applicable: ✓ Yes / ✗ No
  - [ ] HIPAA applicable: ✓ Yes / ✗ No
  - [ ] PCI-DSS applicable: ✓ Yes / ✗ No
  - [ ] SOC 2 applicable: ✓ Yes / ✗ No
  - [ ] Other: \_\_\_\_\_\_\_\_\_\_\_

- [ ] **Verify data handling compliance (if required):**
  - [ ] Data classification applied
  - [ ] PII protected (encryption, access control)
  - [ ] Data retention policies enforced
  - [ ] Data deletion procedures working

### 12.2 Documentation

- [ ] **Security documentation complete:**
  - [ ] Threat model documented
  - [ ] Security architecture reviewed
  - [ ] Known limitations documented
  - [ ] Incident response pla n documented
  - [ ] Runbooks for common scenarios complete

---

## 13. Post-Deployment Actions

### 13.1 Immediate After Deployment

- [ ] **Run full integration test suite:**
  ```bash
  cd /app && python -m pytest tests/integration/ -v
  ```
  - [ ] All tests passing
  - [ ] No warnings or deprecations
  - [ ] Performance baseline met

- [ ] **Execute monitoring validation:**
  ```bash
  infrastructure/scripts/validate-monitoring.sh
  ```
  - [ ] All metrics being collected
  - [ ] Alerting working correctly
  - [ ] Dashboards displaying data
  - [ ] Historical data retention verified

- [ ] **Manual smoke tests:**
  - [ ] Login works
  - [ ] Create/Read/Update/Delete operations succeed
  - [ ] Search functionality works
  - [ ] Export functionality works

### 13.2 Week 1 Stabilization

- [ ] **Day 1-2: Intensive monitoring**
  - [ ] On-call team actively monitoring
  - [ ] Escalation procedures tested
  - [ ] Known issues documented
  - [ ] Performance baselines validated

- [ ] **Day 3-5: Performance optimization**
  - [ ] Slow query analysis
  - [ ] DB query optimization
  - [ ] Cache hit rates reviewed
  - [ ] Resource utilization optimized

- [ ] **Day 6-7: Hardening**
  - [ ] Fine-tune alert thresholds
  - [ ] Disable verbose logging if appropriate
  - [ ] Complete documentation updates
  - [ ] Handoff to ops team

### 13.3 Post-Deployment Review

- [ ] **Schedule security review:**
  - [ ] Review date: \_\_\_\_\_\_\_\_
  - [ ] Security team lead: \_\_\_\_\_\_\_\_
  - [ ] Audit findings documented: ✓ Yes / ✗ No
  - [ ] Issues prioritized for remediation

- [ ] **Update incident response:** 
  - [ ] Procedures updated for new environment
  - [ ] Contacts updated
  - [ ] Escalation paths verified
  - [ ] On-call team trained

---

## Audit Results Summary

**Audit Date:** \_\_\_\_\_\_\_\_\_\_\_  
**Auditor:** \_\_\_\_\_\_\_\_\_\_\_  
**Security Lead Sign-Off:** \_\_\_\_\_\_\_\_\_\_\_ (Signature)  

**Overall Security Posture:** 
- [ ] ✅ **PASS** - All critical items verified, deployment approved
- [ ] ⚠️ **PASS with conditions** - See "Outstanding Issues" below
- [ ] ❌ **FAIL** - Critical security issues must be remediated before deployment

**Total Checklist Items:** \_\_\_ (out of ~200)  
**Items Passed:** \_\_\_  
**Items Failed:** \_\_\_  
**Items Not Applicable:** \_\_\_  

**Outstanding Issues (If Any):**

1. **Issue:** \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_
   - **Severity:** Critical / High / Medium / Low
   - **Remediation:** \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_
   - **Target Date:** \_\_\_\_\_\_\_\_\_\_\_

2. (Add more as needed)

**Approved For Deployment:** ✓ Yes / ✗ No

**Next Audit Scheduled:** \_\_\_\_\_\_\_\_\_\_\_ (Frequency: Post-patch, quarterly, or per compliance requirement)

---

## References

- Production Readiness Guide: `docs/operations/PRODUCTION_READINESS.md`
- Service Operations: `docs/operations/SERVICE_OPERATIONS.md`
- Monitoring Setup: `docs/operations/MONITORING.md`
- Security Architecture: `infrastructure/docs/SECURITY_ARCHITECTURE.md`
- Incident Response: `docs/operations/INCIDENT_RESPONSE.md`

---

**Document History:**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024 | Security Team | Initial release for production deployment |

