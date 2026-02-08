# Vault Troubleshooting Guide

**Document Version:** 1.0  
**Date:** 2024  
**Purpose:** Troubleshoot Vault connectivity and integration issues  

---

## Quick Diagnostic Commands

```bash
# Is Vault running?
curl -s https://vault.prod.internal:8200/v1/sys/health | jq .

# Can we reach Vault at all?
curl -v https://vault.prod.internal:8200/v1/sys/health

# Check network connectivity
nc -zv vault.prod.internal 8200

# Check DNS
dig vault.prod.internal
nslookup vault.prod.internal
```

---

## Common Issues & Solutions

### Issue 1: Connection Refused

**Symptom:**
```
curl: (7) Failed to connect to vault.prod.internal port 8200: Connection refused
```

**Diagnosis:**
1. Is Vault server running?
   ```bash
   systemctl status vault  # or docker ps | grep vault
   ```
2. Is it listening on the right port?
   ```bash
   netstat -tulpn | grep 8200
   ```
3. Is the hostname correct?
   ```bash
   ping vault.prod.internal
   ```

**Solution:**
- If Vault not running: `systemctl start vault` or restart Docker container
- If port wrong: Update `VAULT_ADDR` environment variable
- If DNS fails: Update `/etc/hosts` or DNS settings

**Prevention:**
- Vault should have `Restart=always` in systemd
- Monitor Vault process with health checks

---

### Issue 2: TLS Certificate Error

**Symptom:**
```
curl: (60) SSL certificate problem: unable to get local issuer certificate
or
SSL: CERTIFICATE_VERIFY_FAILED
```

**Diagnosis:**
1. Check certificate validity:
   ```bash
   openssl s_client -connect vault.prod.internal:8200 -showcerts </dev/null 2>/dev/null | \
     openssl x509 -noout -dates -subject
   ```
2. Check if CA is trusted:
   ```bash
   openssl verify -CAfile /etc/ssl/certs/ca-bundle.crt \
     /path/to/vault/cert.crt
   ```

**Solution (For Testing Only):**
```bash
# Temporarily skip TLS verification
export VAULT_SKIP_VERIFY=true
curl https://vault.prod.internal:8200/v1/sys/health

# Or with curl
curl -k https://vault.prod.internal:8200/v1/sys/health
```

**Proper Solution (Production):**
1. If self-signed: Add CA to trusted store
   ```bash
   # Copy CA certificate
   sudo cp vault-ca.crt /usr/local/share/ca-certificates/
   sudo update-ca-certificates
   ```
2. If Let's Encrypt: Ensure certificate not expired
   ```bash
   certbot renew --dry-run
   ```

**Prevention:**
- Set certificate expiry reminders
- Automate certificate renewal (certbot, acme.sh)
- Use trusted CA (Let's Encrypt free)

---

### Issue 3: Authentication Failed - AppRole

**Symptom:**
```
{"errors":["invalid role name"],"request_id":"...","lease_id":"","lease_duration":0}
```

**Diagnosis:**
1. Verify Role ID exists:
   ```bash
   vault read auth/approle/role/justnews-prod
   ```
2. Check AppRole auth method enabled:
   ```bash
   vault auth list | grep approle
   ```
3. Verify credentials:
   ```bash
   echo "VAULT_ROLE_ID: $VAULT_ROLE_ID"
   echo "VAULT_SECRET_ID: $VAULT_SECRET_ID"
   # Should not be empty
   ```

**Solution:**
```bash
# If role doesn't exist, create it
vault write auth/approle/role/justnews-prod \
  token_ttl=1h \
  token_policies="prod/justnews"

# Generate new credentials
vault write -f auth/approle/role/justnews-prod/secret-id

# Get role ID
vault read auth/approle/role/justnews-prod/role-id
```

**Prevention:**
- Document Role ID and Secret ID location
- Store credentials separately (Secret ID in environment, not code)
- Regularly verify token policies

---

### Issue 4: Authentication Failed - Kubernetes

**Symptom:**
```
{"errors":["invalid JWT"],"request_id":"...","lease_id":"","lease_duration":0}
```

**Diagnosis:**
1. Verify K8s auth method enabled:
   ```bash
   vault auth list | grep kubernetes
   ```
2. Check if running in pod:
   ```bash
   cat /var/run/secrets/kubernetes.io/serviceaccount/token | head -c 50
   # Should show JWT token
   ```
3. Check service account binding:
   ```bash
   vault read auth/kubernetes/role/justnews-prod
   ```

**Solution:**
```bash
# If auth method not enabled
vault auth enable kubernetes

# Configure K8s auth (requires service account with permissions)
vault write auth/kubernetes/config \
  host=https://kubernetes.default.svc.cluster.local:443 \
  token_reviewer_jwt="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
  kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt

# Create role
vault write auth/kubernetes/role/justnews-prod \
  bound_service_account_names=justnews \
  bound_service_account_namespaces=default \
  policies="prod/justnews" \
  ttl=1h
```

**Prevention:**
- Verify K8s cluster connectivity from Vault
- Test JWT token validity before deployment
- Document service account requirements

---

### Issue 5: Permission Denied

**Symptom:**
```
{"errors":["permission denied"],"request_id":"...","lease_id":"","lease_duration":0}
```

**Diagnosis:**
1. Check token policies:
   ```bash
   vault token lookup -format=json | jq '.data.policies'
   ```
2. Check policy contents:
   ```bash
   vault policy read prod/justnews
   ```
3. Verify secret path is allowed:
   ```bash
   grep "secret/prod" /etc/vault/policies/prod.hcl
   ```

**Solution:**
1. Add policy grant:
   ```bash
   # Edit policy
   vault policy write prod/justnews - <<EOF
   path "secret/data/prod/*" {
     capabilities = ["read", "list"]
   }
   path "secret/metadata/prod/*" {
     capabilities = ["read", "list"]
   }
   EOF
   ```
2. Re-authenticate with new token
   ```bash
   unset VAULT_TOKEN
   # Re-authenticate
   ```

**Prevention:**
- Grant least-privilege policies
- Document what each service needs to access
- Review policies quarterly

---

### Issue 6: Token Expired

**Symptom:**
```
{"errors":["permission denied"],"request_id":"...","lease_id":"","lease_duration":0}
# Or more specifically:
curl error: 403 Forbidden with "invalid token"
```

**Diagnosis:**
1. Check token TTL:
   ```bash
   vault token lookup -format=json | jq '.data.ttl'
   ```
2. Check if token still exists:
   ```bash
   vault token lookup -format=json
   # If 404, token is definitely expired
   ```

**Solution:**
1. Renew token:
   ```bash
   vault token renew
   ```
2. If renewal fails, re-authenticate:
   ```bash
   vault login -method=approle -path=auth/approle role_id=... secret_id=...
   ```

**Prevention:**
- Set token TTL longer than expected service runtime
- Implement automatic token renewal in application
- Monitor token expiry in logs

---

### Issue 7: Secret Not Found

**Symptom:**
```
{"errors":["secret not found"],"request_id":"...","lease_id":"","lease_duration":0}
```

**Diagnosis:**
1. List available secrets:
   ```bash
   vault list secret/prod/
   ```
2. Check exact path:
   ```bash
   vault list secret/data/prod/mariadb/
   ```
3. Verify secret exists:
   ```bash
   vault read secret/data/prod/mariadb
   ```

**Solution:**
1. Create missing secret:
   ```bash
   vault write secret/data/prod/mariadb \
     password="..." \
     replication_password="..."
   ```
2. Verify creation:
   ```bash
   vault read secret/data/prod/mariadb
   ```

**Prevention:**
- Document all required secrets
- Create pre-deployment secret validation script
- Test all secret paths in integration tests

---

### Issue 8: Vault Sealed

**Symptom:**
```
{"sealed":true,"t":3,"n":5,"progress":0,...}
```

**Diagnosis:**
1. Check status:
   ```bash
   curl https://vault.prod.internal:8200/v1/sys/health | jq '.sealed'
   # If true, Vault is sealed
   ```

**Solution (Emergency Only):**
```bash
# Unseal with recovery keys (only for development!)
vault operator unseal <key1>
vault operator unseal <key2>
vault operator unseal <key3>

# In production, use auto-unseal or stored recovery key
```

**Prevention:**
- Use auto-unseal (AWS KMS, Google KMS, etc.)
- Or stored recovery key in secure location
- Never expose recovery keys
- Monitor Vault seal status

---

### Issue 9: Service Timeout

**Symptom:**
```
curl: (28) Connection timed out after 30000 milliseconds
```

**Diagnosis:**
1. Check network connectivity:
   ```bash
   ping -c 1 vault.prod.internal
   traceroute vault.prod.internal
   ```
2. Check Vault CPU/memory:
   ```bash
   top  # or docker stats
   ```
3. Check active connections:
   ```bash
   netstat -an | grep 8200 | wc -l
   ```

**Solution:**
1. If network: Check firewall rules, routing
2. If resource-constrained: Increase memory/CPU
3. If overloaded: Increase `max_lease_duration`

**Prevention:**
- Monitor Vault resource usage
- Set connection timeouts in clients
- Load test before production

---

### Issue 10: fetch_secrets_to_env.sh Fails

**Symptom:**
```
Error: Could not authenticate to Vault
or
Error: Missing required environment variables
```

**Diagnosis:**
1. Check required variables:
   ```bash
   echo "VAULT_ADDR: $VAULT_ADDR"
   echo "VAULT_ROLE_ID: $VAULT_ROLE_ID"
   echo "VAULT_SECRET_ID: $VAULT_SECRET_ID"
   # All should be non-empty
   ```
2. Check script permissions:
   ```bash
   ls -la infrastructure/scripts/fetch_secrets_to_env.sh
   # Should be executable
   ```
3. Test manually:
   ```bash
   curl -X POST \
     "$VAULT_ADDR/v1/auth/approle/login" \
     -d "{\"role_id\":\"$VAULT_ROLE_ID\",\"secret_id\":\"$VAULT_SECRET_ID\"}" | jq .
   ```

**Solution:**
1. Ensure all required variables set:
   ```bash
   export VAULT_ADDR=https://vault.prod.internal:8200
   export VAULT_ROLE_ID="..."
   export VAULT_SECRET_ID="..."
   ```
2. Run with verbose output:
   ```bash
   bash -x infrastructure/scripts/fetch_secrets_to_env.sh
   ```
3. Check output file:
   ```bash
   ls -la /etc/justnews/.env.prod
   grep MARIADB_PASSWORD /etc/justnews/.env.prod
   ```

**Prevention:**
- Source all required variables before script
- Add error checking in script
- Test in non-production first

---

### Issue 11: Wrong Secrets Cached

**Symptom:**
```
Application using stale secrets after rotation
or
Environment variables not updated after rotation
```

**Diagnosis:**
1. Check environment variable:
   ```bash
   echo $MARIADB_PASSWORD
   ```
2. Check file modification time:
   ```bash
   stat /etc/justnews/.env.prod
   ```
3. Check service environment:
   ```bash
   systemctl show -p Environment justnews-app.service | grep MARIADB
   ```

**Solution:**
1. Re-run secret fetch:
   ```bash
   infrastructure/scripts/fetch_secrets_to_env.sh
   ```
2. Restart service:
   ```bash
   systemctl restart justnews-app.service
   ```
3. Verify new secrets:
   ```bash
   systemctl show -p Environment justnews-app.service | grep MARIADB
   ```

**Prevention:**
- Implement secret rotation notification
- Automatically restart service after secret update
- Use systemd timer to refresh secrets periodically

---

### Issue 12: Database Password Authentication Fails

**Symptom:**
```
Access denied for user 'justnews_prod'@'mariadb.prod.internal'
or
mysql: [Warning] Using a password on the command line interface can be insecure.
ERROR 1045 (28000): Access denied for user 'justnews_prod'@'localhost'
```

**Diagnosis:**
1. Verify password from Vault:
   ```bash
   curl -s -H "X-Vault-Token: $VAULT_TOKEN" \
     "$VAULT_ADDR/v1/secret/data/prod/mariadb" | \
     jq '.data.data.password'
   ```
2. Check if password contains special characters:
   ```bash
   # Look for quotes, backslashes, dollar signs, backticks
   ```
3. Test directly:
   ```bash
   mysql -h mariadb.prod.internal -u justnews_prod -p"$(vault kv get -field=password secret/prod/mariadb)" -e "SELECT 1;"
   ```

**Solution:**
1. Escape special characters properly:
   ```bash
   # Ensure quotes are handled correctly in environment file
   PASSWORD="$(vault kv get -field=password secret/prod/mariadb)"
   # Use single quotes when interpolating
   echo 'mysql ... -p'"'"'$PASSWORD'"'"''
   ```
2. Regenerate password without special chars (if allowed):
   ```bash
   # Ask DBA to set simple password without |&;'"`$\
   ```

**Prevention:**
- Document password character restrictions
- Generate passwords without special shell characters
- Test password before storing in Vault

---

### Issue 13: Help! Everything is broken

**Emergency Troubleshooting:**

```bash
# Step 1: Verify basic connectivity
curl -k https://vault.prod.internal:8200/v1/sys/health
# If this fails, Vault is down - restart it

# Step 2: Check authentication
curl -k -X POST \
  https://vault.prod.internal:8200/v1/auth/approle/login \
  -d '{"role_id":"ROLE_ID","secret_id":"SECRET_ID"}'
# If this fails, credentials wrong or auth method broken

# Step 3: Verify secret paths
vault list secret/prod/
# If empty, secrets not created

# Step 4: Fallback to plaintext (Emergency Only!)
# If Vault completely broken and need to get services running:
# Create /etc/justnews/.env.prod manually with hardcoded secrets
# (This is DANGEROUS and should only be temporary!)

# Step 5: Contact Vault Administrator
# If still broken after above steps, escalate
```

---

## Integration Test Script

To run automated Vault integration tests:

```bash
bash infrastructure/scripts/test_vault_integration.sh --verbose --failfast
```

---

## Common Vault Commands Reference

```bash
# Authentication
vault login -method=approle -path=auth/approle role_id=... secret_id=...
vault login -method=kubernetes role=justnews-prod
vault logout

# Token management
vault token create -ttl=1h
vault token renew
vault token lookup
vault token lookup-self

# Secrets
vault list secret/prod/
vault read secret/data/prod/mariadb
vault write secret/data/prod/mariadb password="..."
vault kv get secret/prod/mariadb
vault kv put secret/prod/mariadb password="..."

# Policies
vault policy list
vault policy read prod/justnews
vault policy write prod/justnews @policy.hcl

# Admin
vault status
vault health
vault audit list
vault audit enable file file_path=/vault/logs/audit.log
vault audit log
```

---

## When to Escalate

**Contact System:** Escalate to DevOps/Infrastructure Team

**Conditions:**
1. Vault cluster is down
2. All recovery keys are lost
3. Database password needed but Vault unreachable
4. Storage backend corrupted
5. Multiple simultaneous authentication failures
6. TLS certificate expired and can't be renewed

**Emergency Contact Info:**
- DevOps on-call: \_\_\_\_\_\_\_\_\_\_\_
- CTO/Escalation: \_\_\_\_\_\_\_\_\_\_\_

---

## Testing Your Fix

After applying any fix above:

```bash
# Re-run the problematic operation
# 1. Test authentication
vault status

# 2. Read a test secret
vault read secret/data/prod/test

# 3. Check token
vault token lookup-self

# 4. If using fetch script
infrastructure/scripts/fetch_secrets_to_env.sh --dry-run
infrastructure/scripts/fetch_secrets_to_env.sh

# 5. Verify environment
grep -c '\$VAULT' /etc/justnews/.env.prod
# Should return 0 (no uninterpolated Vault references)
```

---

## Document Updates

**Last Updated:** February 2024  
**Next Review:** Post-production deployment or upon new issues  

Record issues discovered below for documentation improvement:

| Date | Issue | Resolution | Prevention |
|------|-------|----------|-----------|
| | | | |
| | | | |
