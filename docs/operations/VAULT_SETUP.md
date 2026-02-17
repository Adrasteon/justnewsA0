--- title: Vault Setup and Administration description: HashiCorp Vault OSS setup, configuration, and ongoing
administration ---

# Vault Setup and Administration Guide

This guide covers setting up and managing HashiCorp Vault for JustNews secrets management.

## Overview

JustNews uses **Vault OSS** (open-source, self-hosted) for storing and rotating secrets:

- **Database credentials** (MariaDB password)

- **Proxy credentials** (PIA SOCKS5)

- **API keys** (admin access)

- **Service tokens** (if needed)

### Architecture

```

┌─────────────────────────────────────┐
│  Vault Server (systemd service)     │
│  - Address: 127.0.0.1:8200          │
│  - Storage: Raft (local disk)       │
│  - UI: Enabled at <http://localhost>  │
└──────────┬──────────────────────────┘
           │
    ┌──────┴──────────┐
    │                 │
┌───────────────┐  ┌──────────────────┐
│  AppRole      │  │  Admin Token     │
│  (services)   │  │  (setup/mgt)     │
└───────────────┘  └──────────────────┘
    │                 │
    v                 v
┌─────────────────────────────────────┐
│  KV v2 Engine: secret/justnews      │
│  - MARIADB_PASSWORD                 │
│  - PIA_SOCKS5_*                     │
│  - ADMIN_API_KEY                    │
└─────────────────────────────────────┘
    │
    └──→ fetch_secrets_to_env.sh
         Writes: /run/justnews/secrets.env
         Read by: run_with_env.sh

```

## Installation & First-Time Setup

### Prerequisites

```bash

## Verify system has jq

which jq || sudo apt install -y jq

## Verify curl is available

which curl || sudo apt install -y curl

```bash

### Step 1: Install Vault

```bash

## Add HashiCorp repository

curl <https://apt.releases.hashicorp.com/gpg> | sudo apt-key add -
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] <https://apt.releases.hashicorp.com> $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/hashicorp.list > /dev/null

## Install

sudo apt update
sudo apt install -y vault jq

## Verify

vault version

```

### Step 2: Create Configuration Directory

```bash
sudo mkdir -p /etc/vault.d /var/lib/vault
sudo chown vault:vault /var/lib/vault

## Create config file

sudo tee /etc/vault.d/vault.hcl > /dev/null <<'EOF'
storage "raft" {
  path    = "/var/lib/vault"
  node_id = "vault-local"
}

listener "tcp" {
  address         = "127.0.0.1:8200"
  cluster_address = "127.0.0.1:8201"
  tls_disable     = 1
}

ui = true
api_addr     = "http://127.0.0.1:8200"
cluster_addr = "http://127.0.0.1:8201"
disable_mlock = true
EOF

sudo chmod 644 /etc/vault.d/vault.hcl

```bash

### Step 3: Create Systemd Service

Vault service is installed by the package. Enable and start it:

```bash
sudo systemctl enable vault
sudo systemctl start vault
sudo systemctl status vault

```

### Step 4: Initialize Vault

```bash
export VAULT_ADDR="http://127.0.0.1:8200"

## Initialize (creates unseal key and root token)

vault operator init -key-shares=1 -key-threshold=1 -format=json | tee /tmp/vault-init.json

## Extract credentials

UNSEAL_KEY=$(jq -r '.unseal_keys_hex[0]' /tmp/vault-init.json)
ROOT_TOKEN=$(jq -r '.root_token' /tmp/vault-init.json)

## Store securely

sudo cp /tmp/vault-init.json /etc/justnews/vault-init.json
sudo chmod 600 /etc/justnews/vault-init.json

## Verify location

sudo ls -lh /etc/justnews/vault-init.json

```

### Step 5: Unseal Vault

```bash

## Load credentials

UNSEAL_KEY=$(jq -r '.unseal_keys_hex[0]' /etc/justnews/vault-init.json)

## Unseal

vault operator unseal "$UNSEAL_KEY"

## Verify

vault status

```

**Expected output:**

```

Key                     Value
---                     -----
Seal Type               shamir
Initialized             true
Sealed                  false
Total Shares            1
Threshold               1
...

```

## Configuration: AppRole Setup

### Step 1: Create Policy

```bash
export VAULT_TOKEN=$(jq -r '.root_token' /etc/justnews/vault-init.json)
export VAULT_ADDR="http://127.0.0.1:8200"

vault policy write justnews-read - <<'EOF'
path "secret/data/justnews" {
  capabilities = ["read", "list"]
}
path "secret/metadata/justnews" {
  capabilities = ["read", "list"]
}
path "sys/internal/ui/mounts/secret/*" {
  capabilities = ["read"]
}
EOF

vault policy list  # Verify

```

### Step 2: Enable KV v2 Secrets Engine

```bash
vault secrets enable -version=2 -path=secret kv
vault secrets list  # Verify

```

### Step 3: Enable and Configure AppRole

```bash

## Enable AppRole auth method

vault auth enable approle

## Create role for JustNews services

vault write auth/approle/role/justnews \
  token_num_uses=0 \
  token_ttl=3600 \
  token_max_ttl=86400 \
  policies="justnews-read"

## Verify

vault read auth/approle/role/justnews

```bash

### Step 4: Generate and Store AppRole Credentials

```bash

## Get role ID

ROLE_ID=$(vault read -field=role_id auth/approle/role/justnews/role-id)
echo "$ROLE_ID"  # Save this

## Generate secret ID (one-time use, store immediately)

SECRET_ID=$(vault write -field=secret_id -f auth/approle/role/justnews/secret-id)
echo "$SECRET_ID"  # Save this

## Store credentials with restricted access

sudo bash -c "echo '$ROLE_ID' > /etc/justnews/approle_role_id"
sudo bash -c "echo '$SECRET_ID' > /etc/justnews/approle_secret_id"
sudo chmod 640 /etc/justnews/approle_*

## Create symlinks for compatibility with fetch script

sudo ln -sf /etc/justnews/approle_role_id /etc/justnews/vault_role_id
sudo ln -sf /etc/justnews/approle_secret_id /etc/justnews/vault_secret_id

## Verify

sudo ls -lh /etc/justnews/approle_* /etc/justnews/vault_*

```

### Step 5: Seed Initial Secrets

```bash

## Create the main secret for JustNews

vault kv put secret/justnews \
  MARIADB_PASSWORD="secure_password_here" \
  PIA_SOCKS5_HOST="proxy.example.com" \
  PIA_SOCKS5_PORT="1080" \
  PIA_SOCKS5_USER="pia_username" \
  PIA_SOCKS5_PASS="pia_password" \
  ADMIN_API_KEY="secure_admin_key"

## Verify

vault kv get secret/justnews

```bash

## Testing AppRole Access

```bash

## Test login with AppRole

ROLE_ID=$(cat /etc/justnews/approle_role_id)
SECRET_ID=$(cat /etc/justnews/approle_secret_id)

vault write -format=json auth/approle/login \
  role_id="$ROLE_ID" \
  secret_id="$SECRET_ID" | jq '.auth.client_token'

## This token will be valid for 1 hour, allowing secret reads

```

## Fetch Secrets Script

The `scripts/fetch_secrets_to_env.sh` script automates secret retrieval:

```bash

## Fetch secrets from Vault → /run/justnews/secrets.env

bash scripts/fetch_secrets_to_env.sh

## Verify output

sudo cat /run/justnews/secrets.env

## Expected permissions

sudo ls -lh /run/justnews/secrets.env  # Should be mode 0640

```bash

### How It Works

1. Reads AppRole credentials from `/etc/justnews/approle_*`

1. Authenticates with Vault via AppRole login

1. Fetches secrets from `secret/justnews`

1. Writes key=value pairs to `/run/justnews/secrets.env` (ephemeral tmpfs)

1. Sets permissions to 0640 (readable by root and group)

## Runtime Integration with run_with_env.sh

The `scripts/run_with_env.sh` wrapper automatically layers secrets:

```bash

## Sources:

## 1. /etc/justnews/global.env (system defaults)

## 2. /run/justnews/secrets.env (Vault secrets)

## 3. /etc/justnews/secrets.env (optional local override)

## 4. ./secrets.env (repo-local, for dev)

bash scripts/run_with_env.sh python check_databases.py

## All secrets are available to the command

```

## Ongoing Administration

### Viewing Secrets

```bash
export VAULT_TOKEN=$(jq -r '.root_token' /etc/justnews/vault-init.json)
export VAULT_ADDR="http://127.0.0.1:8200"

## List all secrets

vault kv list secret/justnews

## View entire secret

vault kv get secret/justnews

## Get a specific field

vault kv get -field=MARIADB_PASSWORD secret/justnews

```

### Updating Secrets

```bash

## Patch a single field (keeps other fields)

vault kv patch secret/justnews MARIADB_PASSWORD="new_password"

## Or use the script to reload

bash scripts/fetch_secrets_to_env.sh

```

### Rotating AppRole Secret ID

AppRole secret IDs should be rotated periodically:

```bash
export VAULT_TOKEN=$(jq -r '.root_token' /etc/justnews/vault-init.json)
export VAULT_ADDR="http://127.0.0.1:8200"

## Generate new secret ID

NEW_SECRET_ID=$(vault write -field=secret_id -f auth/approle/role/justnews/secret-id)

## Store it

sudo bash -c "echo '$NEW_SECRET_ID' > /etc/justnews/approle_secret_id"
sudo chmod 640 /etc/justnews/approle_secret_id

## Test with fetch script

bash scripts/fetch_secrets_to_env.sh

```bash

### Rekeying Vault (Advanced)

If you need to change the unseal key (rare, only in compromised scenarios):

```bash
export VAULT_TOKEN=$(jq -r '.root_token' /etc/justnews/vault-init.json)
export VAULT_ADDR="http://127.0.0.1:8200"

## Start rekey

vault operator rekey -init -key-shares=1 -key-threshold=1

## Complete rekey (requires old unseal key)

UNSEAL_KEY=$(jq -r '.unseal_keys_hex[0]' /etc/justnews/vault-init.json)
vault operator rekey -nonce=<nonce-from-init> "$UNSEAL_KEY"

## Store new key in vault-init.json

```

## Troubleshooting

### Vault Won't Start

```bash

## Check config syntax

sudo vault config validate -config=/etc/vault.d/vault.hcl

## View logs

sudo journalctl -u vault -n 50 --no-pager

## Common issues:

## - disable_mlock not set → Error on startup

## - cluster_address missing → "Cluster address must be set"

## - Wrong permissions on /var/lib/vault → Permission denied

```bash

### AppRole Login Fails

```bash

## Verify credentials exist and are readable

sudo cat /etc/justnews/approle_role_id
sudo cat /etc/justnews/approle_secret_id

## Test login manually

vault write auth/approle/login \
  role_id="$(cat /etc/justnews/approle_role_id)" \
  secret_id="$(cat /etc/justnews/approle_secret_id)"

## Check policy

vault policy read justnews-read

```

### Secret Path Issues

```bash

## Verify KV engine is mounted

vault secrets list

## Verify secret exists

vault kv list secret/justnews
vault kv get secret/justnews

## If missing, recreate

vault kv put secret/justnews MARIADB_PASSWORD="..."

```

### Fetch Script Fails

```bash

## Check VAULT_ADDR and credentials

export VAULT_ADDR="http://127.0.0.1:8200"
bash -x scripts/fetch_secrets_to_env.sh 2>&1 | head -20

## Common issues:

## - /etc/justnews/approle_* not readable (check permissions)

## - /run/justnews not writable (check tmpfs mount)

## - Vault not running or wrong port

```

### Directory Permissions

```bash

## Ensure directories exist with correct permissions

sudo mkdir -p /etc/justnews /run/justnews
sudo chmod 755 /etc/justnews
sudo chmod 750 /run/justnews

## Approle files should be 640

sudo chmod 640 /etc/justnews/approle_*

## Vault init file should be 600

sudo chmod 600 /etc/justnews/vault-init.json

```bash

## Backup and Recovery

### Backup Vault State

```bash

## Backup Raft storage (while Vault is running)

sudo cp -r /var/lib/vault ~/vault-backup-$(date +%Y%m%d)

## Backup init/credentials

sudo cp /etc/justnews/vault-init.json ~/vault-init-$(date +%Y%m%d).json

```

### Restore from Backup

```bash

## Stop Vault

sudo systemctl stop vault

## Restore Raft storage

sudo rm -rf /var/lib/vault
sudo cp -r ~/vault-backup-YYYYMMDD /var/lib/vault
sudo chown -R vault:vault /var/lib/vault

## Start Vault

sudo systemctl start vault

## Unseal with stored key

vault operator unseal $(jq -r '.unseal_keys_hex[0]' /etc/justnews/vault-init.json)

```bash

## Security Considerations

1. **Root Token**: Store securely, disable after setup if possible

1. **Unseal Key**: Critical for recovery; store in secure location (NOT same as root token)

1. **AppRole Credentials**: Rotate secret IDs regularly

1. **Network**: Consider TLS for production (tls_cert_file, tls_key_file)

1. **Access Control**: Use firewall rules to restrict Vault port access

1. **Audit Logging**: Enable Vault audit backend for compliance

```bash

## Enable audit logging

vault audit enable file file_path=/var/log/vault/audit.log

```

## References

- [HashiCorp Vault OSS Documentation](https://www.vaultproject.io/docs)

- [AppRole Authentication](https://www.vaultproject.io/docs/auth/approle)

- [KV Secrets Engine](https://www.vaultproject.io/docs/secrets/kv)
