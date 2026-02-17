# Vault Integration Testing Guide

**Document Version:** 1.0  
**Date:** 2024  
**Purpose:** Validate Vault integration before production deployment  
**Estimated Time:** 1-2 hours for full testing  

---

## Overview

This guide documents testing procedures for HashiCorp Vault integration with the justnews application. Before production deployment, verify all Vault operations work correctly.

**Prerequisites:**
- Vault server running and accessible
- Vault CLI installed (`which vault`)
- Appropriate Vault credentials (admin or authenticated user)
- AppRole or Kubernetes authentication method configured
- Test secrets already created in Vault

---

## Part 1: Vault Connectivity Verification

### 1.1 Basic Connection Test

**Objective:** Verify Vault server is reachable and responding

```bash
# Test 1: Ping Vault health endpoint
curl -s https://vault.prod.internal:8200/v1/sys/health | jq .

# Expected output (unsealed):
# {
#   "initialized": true,
#   "sealed": false,
#   "standby": false,
#   "performance_standby": false,
#   "replication_performance_secondary": false,
#   "replication_dr_secondary": false,
#   "version": "1.15.0"
# }
```

**Verification Checklist:**
- [ ] Vault returns 200 status code
- [ ] `initialized` is `true`
- [ ] `sealed` is `false`
- [ ] `version` field exists

### 1.2 TLS Certificate Validation

**Objective:** Verify Vault TLS certificate is valid and trusted

```bash
# Test 2: Check certificate expiry and validity
curl -sI https://vault.prod.internal:8200/v1/sys/health | grep -i ssl

# Or more detailed:
openssl s_client -connect vault.prod.internal:8200 -showcerts </dev/null 2>/dev/null | \
  openssl x509 -noout -dates -subject
```

**Verification Checklist:**
- [ ] Certificate is not expired
- [ ] Certificate subject matches Vault hostname
- [ ] Certificate chain is valid (if self-signed, CA cert available)

### 1.3 DNS Resolution

**Objective:** Ensure Vault hostname resolves correctly

```bash
# Test 3: Verify DNS
nslookup vault.prod.internal
dig vault.prod.internal
```

**Verification Checklist:**
- [ ] Hostname resolves to correct IP
- [ ] DNS query time acceptable (< 100ms)

---

## Part 2: Authentication Testing

### 2.1 AppRole Authentication (Development/Staging)

**Objective:** Test AppRole authentication method

**Prerequisites:**
- AppRole auth method enabled (`vault auth list` shows `approle/`)
- Role ID and Secret ID generated

**Test Procedure:**

```bash
# Step 1: Set environment variables
export VAULT_ADDR=https://vault.prod.internal:8200
export VAULT_ROLE_ID="your-role-id"
export VAULT_SECRET_ID="your-secret-id"
export VAULT_NAMESPACE="your-namespace"  # if using namespaces

# Step 2: Authenticate with AppRole
VAULT_TOKEN=$(curl -s -X POST \
  "${VAULT_ADDR}/v1/auth/approle/login" \
  -d "{\"role_id\":\"${VAULT_ROLE_ID}\",\"secret_id\":\"${VAULT_SECRET_ID}\"}" | \
  jq -r '.auth.client_token')

echo "Vault Token: $VAULT_TOKEN"

# Step 3: Verify token works
curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/auth/approle/role/justnews-prod" | jq .

# Expected: Role details without error
```

**Verification Checklist:**
- [ ] Authentication request succeeds (200 status)
- [ ] Token is returned (`client_token` field)
- [ ] Token is not empty string
- [ ] Token can be used for subsequent requests
- [ ] Token TTL is reasonable (check `.auth.lease_duration`)

### 2.2 Kubernetes Authentication (Production)

**Objective:** Test Kubernetes authentication method

**Prerequisites:**
- Kubernetes auth method enabled
- Service account created and bound to role
- Running inside Kubernetes cluster

**Test Procedure (from pod):**

```bash
# Step 1: Set environment
export VAULT_ADDR=https://vault.prod.internal:8200
export VAULT_AUTH_PATH=kubernetes
export VAULT_NAMESPACE="prod"
export VAULT_ROLE=justnews-prod
export K8S_TOKEN_PATH=/var/run/secrets/kubernetes.io/serviceaccount/token

# Step 2: Authenticate with Kubernetes method
K8S_JWT=$(cat ${K8S_TOKEN_PATH})

VAULT_TOKEN=$(curl -s -X POST \
  "${VAULT_ADDR}/v1/auth/${VAULT_AUTH_PATH}/login" \
  -d "{\"jwt\":\"${K8S_JWT}\",\"role\":\"${VAULT_ROLE}\"}" | \
  jq -r '.auth.client_token')

echo "Vault Token: $VAULT_TOKEN"

# Step 3: Verify token
curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/sys/leases/lookup" | jq .
```

**Verification Checklist:**
- [ ] Kubernetes JWT file available at expected path
- [ ] Authentication succeeds with JWT
- [ ] Token returned and valid
- [ ] Token permissions match expected role

### 2.3 Token Validation

**Objective:** Verify token properties and TTL

```bash
# Test: Check token properties
curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/auth/token/lookup-self" | jq .

# Expected output includes:
# {
#   "data": {
#     "accessor": "...",
#     "creation_time": ...,
#     "creation_ttl": ...,
#     "orphan": false,
#     "ttl": ...,
#     "policies": ["prod/justnews"]
#   }
# }
```

**Verification Checklist:**
- [ ] Token TTL is reasonable (check `.data.ttl`)
- [ ] Policies match expected role (check `.data.policies`)
- [ ] Token is not orphaned
- [ ] Token has valid creation time

---

## Part 3: Secret Path Testing

### 3.1 List Available Secrets

**Objective:** Verify all required secrets exist

```bash
# List all secrets in prod database section
curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  -X LIST \
  "${VAULT_ADDR}/v1/secret/prod/mariadb" | jq .

# Expected: List of secret keys (e.g., password, replication_password)
```

**Verification Checklist for Each Secret:**
- [ ] Secret path exists
- [ ] Secret is readable (200 response)
- [ ] Secret contains expected keys
- [ ] Secret value is not empty

### 3.2 Test Individual Secret Retrieval

**Objective:** Retrieve and verify each production secret

**Database Secrets:**

```bash
# Test: Retrieve MariaDB password
curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/secret/data/prod/mariadb" | jq '.data.data.password'

# Expected: Non-empty string value

# Verify password is usable
mysql -h mariadb.prod.internal \
  -u justnews_prod \
  -p"$(curl -s -H "X-Vault-Token: ${VAULT_TOKEN}" \
      "${VAULT_ADDR}/v1/secret/data/prod/mariadb" | \
      jq -r '.data.data.password')" \
  -e "SELECT 1;"

# Expected: No errors, returns "1"
```

**HuggingFace Token:**

```bash
# Test: Retrieve HF token
HF_TOKEN=$(curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/secret/data/prod/huggingface" | \
  jq -r '.data.data.token')

# Verify token works (100 MB download test)
curl -s -H "Authorization: Bearer ${HF_TOKEN}" \
  https://huggingface.co/api/models/Qwen/Qwen2.5-14B-Instruct-AWQ | \
  jq '.id'

# Expected: Returns model ID "Qwen/Qwen2.5-14B-Instruct-AWQ"
```

**Encryption Keys:**

```bash
# Test: Retrieve encryption key
curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/secret/data/prod/encryption" | jq '.data.data.key'

# Verify key length (AES-256 = 32 bytes, 64 hex chars)
KEY_LENGTH=$(curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/secret/data/prod/encryption" | \
  jq -r '.data.data.key' | wc -c)

echo "Key length: $KEY_LENGTH chars (expected 64)"
```

**All Production Secrets Checklist:**
- [ ] `secret/prod/mariadb/password` - readable, non-empty
- [ ] `secret/prod/mariadb/replication_password` - readable, non-empty
- [ ] `secret/prod/huggingface/token` - readable, non-empty, valid
- [ ] `secret/prod/encryption/key` - readable, correct length
- [ ] `secret/prod/django/secret_key` - readable, non-empty
- [ ] `secret/prod/jwt/secret` - readable, non-empty
- [ ] `secret/prod/email/*` - readable, non-empty
- [ ] `secret/prod/sentry/dsn` - readable, non-empty
- [ ] `secret/prod/datadog/*` - readable, non-empty
- [ ] `secret/prod/slack/webhook_url` - readable, non-empty
- [ ] `secret/prod/pagerduty/key` - readable, non-empty

---

## Part 4: Secret Rotation Testing

### 4.1 Manual Secret Rotation

**Objective:** Test secret rotation process

```bash
# Step 1: Create new secret version
curl -s -X POST \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/secret/data/prod/mariadb" \
  -d '{
    "data": {
      "password": "new_test_password_12345",
      "replication_password": "new_repl_password_12345"
    }
  }' | jq .

# Step 2: Verify new version created (metadata.version incremented)
curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/secret/metadata/prod/mariadb" | jq '.data.versions'

# Step 3: Retrieve and verify new secret
curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/secret/data/prod/mariadb" | \
  jq '.data.data.password'

# Step 4: Restore old secret (for testing, use previous version)
# In KV 2.0: curl -s -X POST \
#   -H "X-Vault-Token: ${VAULT_TOKEN}" \
#   "${VAULT_ADDR}/v1/secret/undelete/prod/mariadb" \
#   -d '{"versions":[1]}'
```

**Verification Checklist:**
- [ ] New version created successfully
- [ ] Version number incremented
- [ ] New secret value retrievable
- [ ] Rotation timestamp recorded in metadata

### 4.2 Scheduled Rotation Policy

**Objective:** Verify rotation policy is configured

```bash
# Check if rotation policy exists
vault policy list | grep -i rotate

# If policy exists, read it
vault policy read prod/rotate-secrets

# Expected policy should grant permissions to:
# - Update secret values (secret/data/prod/*)
# - Read secret metadata (secret/metadata/prod/*)
# - Create secret versions (implicit in KV 2.0 update)
```

**Verification Checklist:**
- [ ] Rotation policy exists
- [ ] Policy grants appropriate permissions
- [ ] Policy can be executed by service account

---

## Part 5: Token Refresh Testing

### 5.1 Token Lifecycle

**Objective:** Verify tokens refresh correctly before expiry

```bash
# Step 1: Get current token TTL
TTL_RESPONSE=$(curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/auth/token/lookup-self")

CURRENT_TTL=$(echo "$TTL_RESPONSE" | jq '.data.ttl')
echo "Current TTL: ${CURRENT_TTL} seconds"

# Step 2: Renew token
curl -s -X POST \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/auth/token/renew-self" | jq '.'

# Step 3: Verify new TTL (should be reset to initial TTL)
RENEWED_TTL=$(curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/auth/token/lookup-self" | \
  jq '.data.ttl')

echo "Renewed TTL: ${RENEWED_TTL} seconds"

# Expected: RENEWED_TTL > CURRENT_TTL (typically much higher)
```

**Verification Checklist:**
- [ ] Token TTL retrieved successfully
- [ ] Token renewal succeeds
- [ ] TTL reset after renewal
- [ ] Token remains valid for new operations

### 5.2 Token Expiry Handling

**Objective:** Test behavior when token expires

```bash
# Warn: This is destructive - only test with throwaway token!
# Step 1: Create a special short-lived token for testing
TEST_TOKEN=$(curl -s -X POST \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/auth/token/create" \
  -d '{"ttl":"10s"}' | jq -r '.auth.client_token')

# Step 2: Wait for expiry (if using 10s TTL, wait 11 seconds)
echo "Waiting 11 seconds for token to expire..."
sleep 11

# Step 3: Try to use expired token (should fail)
curl -s \
  -H "X-Vault-Token: ${TEST_TOKEN}" \
  "${VAULT_ADDR}/v1/secret/data/prod/mariadb" | jq .

# Expected: 403 error with "permission denied" message
```

**Verification Checklist:**
- [ ] Short-lived token created successfully
- [ ] Token expires after TTL expires
- [ ] Expired token rejected with 403 error
- [ ] Error message is clear ("permission denied" or "invalid token")

---

## Part 6: Integration with Application

### 6.1 Test Fetch Secrets Script

**Objective:** Verify `fetch_secrets_to_env.sh` script works

```bash
# Step 1: Ensure script exists and is executable
ls -la infrastructure/scripts/fetch_secrets_to_env.sh
chmod +x infrastructure/scripts/fetch_secrets_to_env.sh

# Step 2: Test script in dry-run mode
./infrastructure/scripts/fetch_secrets_to_env.sh --dry-run

# Expected output shows what secrets would be fetched

# Step 3: Verify script authenticates with Vault
export VAULT_ADDR=https://vault.prod.internal:8200
export VAULT_NAMESPACE=prod
export VAULT_AUTH_METHOD=approle
export VAULT_ROLE_ID="your-role-id"
export VAULT_SECRET_ID="your-secret-id"

./infrastructure/scripts/fetch_secrets_to_env.sh

# Expected: Script succeeds, creates /etc/justnews/.env.prod

# Step 4: Verify output file permissions and content
ls -la /etc/justnews/.env.prod
head -20 /etc/justnews/.env.prod

# Expected: File permissions 600, content includes interpolated secrets
grep -E '^\MARIADB_PASSWORD=' /etc/justnews/.env.prod | grep -v '\$VAULT'

# Should NOT show $VAULT_ references - all should be interpolated
```

**Verification Checklist:**
- [ ] Script exists and is executable
- [ ] Dry-run mode works correctly
- [ ] Script authenticates with Vault
- [ ] Output file created with correct permissions (600)
- [ ] Secrets interpolated (no $VAULT_* variables remain)
- [ ] All required variables present
- [ ] No errors or warnings in output

### 6.2 Test Django Configuration

**Objective:** Verify Django can use secrets from environment

```bash
# Step 1: Set environment from generated file
export $(grep -v '^#' /etc/justnews/.env.prod | xargs)

# Step 2: Test Django import
python3 << 'EOF'
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'justnews_publisher.settings'
import django
try:
    django.setup()
    from django.conf import settings
    print(f"✓ Django configured")
    print(f"  DEBUG: {settings.DEBUG}")
    print(f"  SECRET_KEY: {settings.SECRET_KEY[:20]}...")
    print(f"  ALLOWED_HOSTS: {settings.ALLOWED_HOSTS}")
    print(f"  DATABASE: {settings.DATABASES['default']['NAME']}")
except Exception as e:
    print(f"✗ Django configuration error: {e}")
EOF
```

**Verification Checklist:**
- [ ] Django imports successfully
- [ ] SECRET_KEY loaded from Vault
- [ ] Database configuration correct
- [ ] ALLOWED_HOSTS configured
- [ ] No missing environment variable errors

### 6.3 Test Database Connection

**Objective:** Verify MariaDB connection using Vault credentials

```bash
# Step 1: Extract MariaDB credentials from environment
DB_HOST=$(grep MARIADB_HOST /etc/justnews/.env.prod | cut -d= -f2)
DB_USER=$(grep MARIADB_USER /etc/justnews/.env.prod | cut -d= -f2)
DB_PASS=$(grep MARIADB_PASSWORD /etc/justnews/.env.prod | cut -d= -f2)
DB_NAME=$(grep MARIADB_DB /etc/justnews/.env.prod | cut -d= -f2)

# Step 2: Test connection
mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" -e "USE $DB_NAME; SELECT COUNT(*) FROM information_schema.tables;"

# Expected: Shows table count without errors
```

**Verification Checklist:**
- [ ] Database host resolved
- [ ] Database credentials valid
- [ ] Connection succeeds
- [ ] Database accessible
- [ ] Tables enumerable

---

## Part 7: Error Scenarios

### 7.1 Test Invalid Credentials

**Objective:** Verify proper error handling for invalid credentials

```bash
# Test invalid AppRole credentials
curl -s -X POST \
  "${VAULT_ADDR}/v1/auth/approle/login" \
  -d '{"role_id":"invalid","secret_id":"invalid"}' | jq '.errors'

# Expected: Error message about invalid credentials
```

**Verification Checklist:**
- [ ] Invalid credentials rejected
- [ ] Error message is clear
- [ ] No sensitive information leaked in error message
- [ ] Proper HTTP status code (403)

### 7.2 Test Missing Secret

**Objective:** Verify error handling for missing secrets

```bash
# Test retrieving non-existent secret
curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/secret/data/prod/nonexistent" | jq '.errors'

# Expected: 404 error with "secret not found" message
```

**Verification Checklist:**
- [ ] Missing secret returns 404 (not found)
- [ ] Error message is clear
- [ ] No server crash or 500 error

### 7.3 Test Insufficient Permissions

**Objective:** Verify permission denial errors

```bash
# Try to access secret outside policy scope
curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/secret/data/staging/mariadb" | jq '.errors'

# Expected: 403 error with "permission denied"
```

**Verification Checklist:**
- [ ] Cross-environment access denied
- [ ] 403 (forbidden) status code returned
- [ ] Error message clear

---

## Part 8: Audit and Logging

### 8.1 Verify Audit Logging

**Objective:** Verify all Vault operations are logged

```bash
# Test: Check Vault audit logs
curl -s \
  -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/sys/audit" | jq '.

'

# Should show active audit devices (file, syslog, etc.)

# Check audit log file (if file backend)
tail -20 /vault/logs/audit.log | jq '.
'
```

**Verification Checklist:**
- [ ] Audit devices enabled
- [ ] Audit logs being written
- [ ] Secret access logged with:
  - [ ] Timestamp
  - [ ] Auth method used
  - [ ] Secret path accessed
  - [ ] User/service account
  - [ ] Result (success/failure)

### 8.2 Sensitive Data Redaction

**Objective:** Verify secrets not logged in plain text

```bash
# Check that actual secret values not in application logs
grep -r "MARIADB_PASSWORD=" /var/log/justnews/ || echo "✓ No plaintext passwords in logs"

# Check application log format
tail -20 /var/log/justnews/app.log | jq '.environment_vars' || echo "✓ Environment vars masked in logs"
```

**Verification Checklist:**
- [ ] Secret values not logged in application logs
- [ ] Vault operations logged with metadata only
- [ ] Log aggregation doesn't capture environment variables
- [ ] No secrets in error messages

---

## Testing Checklist Summary

### Pre-Testing
- [ ] Vault server running and healthy
- [ ] Vault CLI installed and configured
- [ ] Test vault credentials available
- [ ] Network access to Vault verified
- [ ] TLS certificate valid or CA configured
- [ ] Test secrets created in Vault

### Authentication
- [ ] AppRole authentication works
- [ ] Kubernetes authentication works (if applicable)
- [ ] Token properties valid
- [ ] Token TTL reasonable

### Secrets Management
- [ ] All required secrets accessible
- [ ] Each secret value valid
- [ ] Secret retrieval works correctly
- [ ] No permission errors

### Rotation
- [ ] Manual rotation works
- [ ] New versions created successfully
- [ ] Version history maintained
- [ ] Old versions retrievable

### Application Integration
- [ ] `fetch_secrets_to_env.sh` script works
- [ ] Django configuration loads correctly
- [ ] Database connection successful
- [ ] Environment variables interpolated

### Error Handling
- [ ] Invalid credentials rejected properly
- [ ] Missing secrets return 404
- [ ] Permission denied returns 403
- [ ] Error messages clear and non-leaking

### Audit & Logging
- [ ] Audit logging enabled
- [ ] All access logged
- [ ] Secrets not logged in plaintext
- [ ] Proper log redaction

---

## Test Execution Script

Run all tests automatically:

```bash
bash infrastructure/scripts/test_vault_integration.sh --verbose
```

For details, see [test_vault_integration.sh](../../infrastructure/scripts/test_vault_integration.sh)

---

## Troubleshooting

For detailed troubleshooting steps, see [VAULT_TROUBLESHOOTING.md](VAULT_TROUBLESHOOTING.md)

Common issues:
- **Connection refused:** Vault address or port incorrect
- **TLS certificate error:** CA not trusted, use `--tls-skip-verify` for testing only
- **Authentication failed:** Role ID or Secret ID incorrect
- **Permission denied:** Policy doesn't grant required access
- **Timeout:** Network connectivity issue or Vault overloaded

---

## Sign-Off

**Testing Completed By:** \_\_\_\_\_\_\_\_\_\_\_  
**Date:** \_\_\_\_\_\_\_\_\_\_\_  
**Result:** ✅ PASS / ❌ FAIL  

**All Tests Passed:** ✓ Yes / ✗ No  
**Outstanding Issues:** \_\_\_\_\_\_\_\_\_\_\_  

**Approved for Production:** ✓ Yes / ✗ No (Requires all tests passing)

---

## References

- [Vault Documentation](https://www.vaultproject.io/docs)
- [AppRole Auth](https://www.vaultproject.io/docs/auth/approle)
- [Kubernetes Auth](https://www.vaultproject.io/docs/auth/kubernetes)
- [KV Secrets Engine](https://www.vaultproject.io/docs/secrets/kv)
- [Vault Audit Logging](https://www.vaultproject.io/docs/audit)
- [Secret Rotation Best Practices](https://www.vaultproject.io/docs/concepts/secret-engine)
