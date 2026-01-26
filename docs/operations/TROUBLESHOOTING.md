--- title: Troubleshooting and Diagnostics description: Comprehensive troubleshooting guide for JustNews infrastructure,
Vault, MariaDB, ChromaDB, and systemd services ---

# Troubleshooting and Diagnostics

This guide covers diagnosing and resolving common issues in the JustNews infrastructure, including Vault, MariaDB,
ChromaDB, and systemd integration.

## Quick Health Check

```bash

## Check all systemd services

sudo systemctl status vault mariadb chromadb

## Check database connectivity

bash scripts/run_with_env.sh python check_databases.py

## Check environment variables are loaded

bash scripts/run_with_env.sh env | grep "MARIADB\|CHROMADB"

## Check secrets availability

bash scripts/fetch_secrets_to_env.sh && echo "Vault connection successful"

```bash

## Systemd Service Issues

### Service Won't Start

#### Vault won't start

```bash

## Check logs

sudo journalctl -u vault -n 50 -f

## Common issues:

## 1. Port already in use

sudo ss -tlnp | grep 8200

## 2. Missing config file

sudo ls -lh /etc/vault.d/vault.hcl

## 3. Fix permissions

sudo chown vault:vault /var/lib/vault
sudo chmod 700 /var/lib/vault

## 4. Restart

sudo systemctl restart vault

```

#### MariaDB won't start

```bash

## Check logs

sudo journalctl -u mariadb -n 50 -f

## Common issues:

## 1. Port already in use

sudo ss -tlnp | grep 3306

## 2. Corrupted InnoDB files

sudo rm -rf /var/lib/mysql/ib_logfile* /var/lib/mysql/ibdata1
sudo systemctl restart mariadb

## 3. Missing mysql user

sudo useradd -r -s /bin/false mysql

## 4. Check disk space

df -h /var/lib/mysql

```bash

#### ChromaDB won't start

```bash

## Check logs

sudo journalctl -u chromadb -n 50 -f

## Common issues:

## 1. Python binary mismatch

bash scripts/run_with_env.sh which chroma

## 2. Missing dependencies

bash scripts/run_with_env.sh pip list | grep chroma

## 3. Port binding issue

sudo ss -tlnp | grep 3307

## 4. Conda environment not activated

conda info --envs

## 5. Restart service

sudo systemctl restart chromadb

```

### Service Started but Not Responsive

#### Vault responding with errors

```bash

## Check if unsealed

vault status

## If sealed:

vault operator unseal

## (Enter unseal keys from /etc/justnews/vault-init.json)

## If still broken, check listener config

grep -A 5 "listener \"tcp\"" /etc/vault.d/vault.hcl

## Restart and monitor

sudo systemctl restart vault && sleep 2 && vault status

```bash

#### MariaDB not accepting connections

```bash

## Check if socket exists

ls -lh /var/run/mysqld/mysql.sock

## Test with mysql client

mysql -h 127.0.0.1 -u root -e "SELECT 1;" 2>&1

## If socket error, restart:

sudo systemctl restart mariadb

## If still broken, check mysql user/group

sudo chown mysql:mysql /var/run/mysqld
sudo chmod 755 /var/run/mysqld

```

#### ChromaDB not responding

```bash

## Test HTTP endpoint

curl -v <http://localhost:3307/api/v2/heartbeat>

## If timeout, check if process running

ps aux | grep chroma

## Check port is listening

ss -tlnp | grep 3307

## If not listening, check logs

sudo journalctl -u chromadb -n 20

## Restart with verbose output

sudo systemctl stop chromadb
bash scripts/run_with_env.sh chroma run --host 0.0.0.0 --port 3307 --verbose

```bash

## Environment and Configuration Issues

### Environment Variables Not Found

```bash

## Verify global.env files exist

ls -lh /etc/justnews/global.env
ls -lh ./global.env

## Check which file is loaded first

bash scripts/run_with_env.sh bash -x <<'EOF'
source /etc/justnews/global.env 2>/dev/null || source ./global.env
echo "Loaded global.env successfully"
EOF

## Verify specific variable

bash scripts/run_with_env.sh echo "$MARIADB_HOST:$MARIADB_PORT"

## Debug wrapper script line by line

bash -x scripts/run_with_env.sh env | head -20

```

### Wrong Python Interpreter Used

```bash

## Check what python is active

which python
echo $PYTHON_BIN

## Verify they match

bash scripts/run_with_env.sh which python

## If mismatch, check global.env

grep "PYTHON_BIN\|CANONICAL_ENV" /etc/justnews/global.env

## Force correct interpreter

/home/adra/miniconda3/envs/justnews-py312/bin/python -c "import sys; print(sys.prefix)"

```bash

### Conda Environment Not Activated

```bash

## List available environments

conda info --envs

## Verify justnews-py312 exists

conda env list | grep justnews-py312

## Activate manually

conda activate justnews-py312

## Check which python is active

which python

## Show python prefix

python -c "import sys; print(sys.prefix)"

```

## Secrets Management Issues

### Vault Connection Fails

```bash

## Check if Vault is running

sudo systemctl status vault

## Check if unsealed

vault status

## Verify VAULT_ADDR is set correctly

echo $VAULT_ADDR

## Should output: <http://127.0.0.1:8200>

## Test raw connection

curl -v <http://127.0.0.1:8200/v1/sys/health>

## If timeouts, check firewall

sudo firewall-cmd --list-ports
sudo ufw status

```bash

### Unseal Key Lost

```bash

## Check if vault-init.json exists

sudo cat /etc/justnews/vault-init.json | jq .

## Extract unseal keys

UNSEAL_KEY=$(sudo cat /etc/justnews/vault-init.json | jq -r '.unseal_keys_b64[0]')
vault operator unseal $UNSEAL_KEY

## If lost permanently:

## 1. You will need to perform disaster recovery

## 2. Save Raft storage backup

sudo cp -r /var/lib/vault /var/lib/vault.backup

## 3. Reinitialize Vault (loses all data)

vault operator init

```

### fetch_secrets_to_env.sh Fails

```bash

## Check AppRole credentials exist

ls -lh /etc/justnews/approle_role_id /etc/justnews/approle_secret_id

## Read them (requires sudo)

sudo cat /etc/justnews/approle_role_id
sudo cat /etc/justnews/approle_secret_id

## Verify Vault is unsealed

vault status

## Test AppRole auth manually

ROLE_ID=$(sudo cat /etc/justnews/approle_role_id)
SECRET_ID=$(sudo cat /etc/justnews/approle_secret_id)
curl -X POST \
  -d "{\"role_id\":\"$ROLE_ID\",\"secret_id\":\"$SECRET_ID\"}" \
  <http://127.0.0.1:8200/v1/auth/approle/login>

## If fails, check AppRole policy exists

vault policy read approle-policy

```bash

### Secrets Not Available at Runtime

```bash

## Manually fetch secrets

bash scripts/fetch_secrets_to_env.sh

## Verify file created

sudo ls -lh /run/justnews/secrets.env

## Check contents (requires sudo)

sudo cat /run/justnews/secrets.env | head

## Verify permissions (should be 640)

sudo stat /run/justnews/secrets.env | grep Access

## Test secret is in environment

bash scripts/run_with_env.sh echo "$MARIADB_PASSWORD"

```

## Database Issues

### MariaDB Connection Fails

```bash

## Test raw connection (requires mysql client)

mysql -h 127.0.0.1 -u justnews -p"<password>" -e "SELECT 1;"

## If password fails, check in Vault

bash scripts/run_with_env.sh echo "$MARIADB_PASSWORD"

## Verify database exists

mysql -u root -e "SHOW DATABASES;" | grep justnews

## Check user permissions

mysql -u root -e "SELECT user, host FROM mysql.user;" | grep justnews

## If not found, recreate user

mysql -u root -e "CREATE USER 'justnews'@'127.0.0.1' IDENTIFIED BY 'password';"
mysql -u root -e "GRANT ALL PRIVILEGES ON justnews.* TO 'justnews'@'127.0.0.1';"
mysql -u root -e "FLUSH PRIVILEGES;"

```bash

### MariaDB Service Running but Slow

```bash

## Check performance

mysql -u justnews -p -e "SHOW PROCESSLIST;"

## Check running queries

mysql -u justnews -p -e "SELECT * FROM INFORMATION_SCHEMA.PROCESSLIST;"

## Check table locks

mysql -u justnews -p -D justnews -e "SHOW OPEN TABLES;"

## Optimize tables

mysql -u justnews -p -D justnews -e "OPTIMIZE TABLE articles, entities, article_entities;"

## Check index usage

mysql -u justnews -p -D justnews -e "SHOW INDEX FROM articles;"

## Monitor size

du -sh /var/lib/mysql/justnews

```

### ChromaDB Connection Fails

```bash

## Test HTTP endpoint

curl -v <http://localhost:3307/api/v2/heartbeat>

## If timeout, check if service is running

sudo systemctl status chromadb

## Check logs

sudo journalctl -u chromadb -n 20 -f

## Verify port is open

ss -tlnp | grep 3307

## Test with Python client

python -c "
import chromadb
try:
    client = chromadb.HttpClient(host='localhost', port=3307)
    print('Connection successful')
    print(f'Collections: {[c.name for c in client.list_collections()]}')
except Exception as e:
    print(f'Error: {e}')
"

## If ModuleNotFoundError, activate conda environment

conda activate justnews-py312
python -c "import chromadb; print(chromadb.__version__)"

```bash

### ChromaDB Collection Missing

```bash

## List collections

python -c "
import chromadb
client = chromadb.HttpClient(host='localhost', port=3307)
print(f'Collections: {[c.name for c in client.list_collections()]}')
"

## Create articles collection

python -c "
import chromadb
client = chromadb.HttpClient(host='localhost', port=3307)
try:
    collection = client.get_collection(name='articles')
    print('Collection exists')
except:
    collection = client.create_collection(name='articles')
    print('Collection created')
"

## Or use the bootstrap script

bash scripts/run_with_env.sh python scripts/chroma_bootstrap.py \
  --host localhost --port 3307 --collection articles

```

### ChromaDB Query Performance Slow

```bash

## Check ChromaDB memory usage

ps aux | grep chroma | grep -v grep

## Monitor in real-time

top -p <chromadb-pid>

## Check if running out of memory (systemd limit)

sudo systemctl cat chromadb | grep MemoryLimit

## Increase memory if needed

sudo systemctl edit chromadb

## Add or modify: MemoryLimit=4G

## Restart

sudo systemctl restart chromadb

```bash

## Application Runtime Issues

### Python Import Errors

```bash

## Verify PYTHONPATH is set

bash scripts/run_with_env.sh echo "$PYTHONPATH"

## Test imports

bash scripts/run_with_env.sh python -c "import agents; print('Import successful')"

## If import fails, check conda environment

conda activate justnews-py312
python -c "import chromadb; import pymysql; print('All imports successful')"

## If ModuleNotFoundError, reinstall dependencies

conda activate justnews-py312
conda install --file requirements.txt

```

### Protocol Buffers / SentencePiece Errors

#### "Descriptors cannot be created directly" Error

If you see an error like `TypeError: Descriptors cannot be created directly` when loading models (especially Mistral/Llama):

1. **Check Protobuf Version**: We require a custom-built protobuf package for Python 3.12 compatibility.
   ```bash
   conda list protobuf
   # Should show version 4.25.x from 'local' channel, NOT 5.x or 6.x from conda-forge
   ```

2. **Re-install Custom Protobuf**:
   If the version is incorrect or missing:
   ```bash
   # Build local package
   conda build conda/recipes/protobuf
   
   # Install local package
   conda install -n justnews-py312 --use-local protobuf=4.25.8 -y
   ```

3. **Check SentencePiece Version**:
   Must be `>=0.2.1` to be compatible with the newer protobuf descriptors.
   ```bash
   conda list sentencepiece
   # If < 0.2.1:
   pip install "sentencepiece>=0.2.1"
   ```

4. **Verify Imports**:
   ```bash
   python -c "from transformers import AutoTokenizer; print('Success')"
   ```

### Database Permission Denied

```bash

## Check global.env variables

bash scripts/run_with_env.sh env | grep MARIADB

## Verify user has permissions

mysql -u root -e "SHOW GRANTS FOR 'justnews'@'127.0.0.1';"

## Grant all if needed

mysql -u root -e "GRANT ALL PRIVILEGES ON justnews.* TO 'justnews'@'127.0.0.1';"
mysql -u root -e "FLUSH PRIVILEGES;"

## Test connection with correct credentials

bash scripts/run_with_env.sh python -c "
import pymysql
import os
conn = pymysql.connect(
    host=os.getenv('MARIADB_HOST'),
    user=os.getenv('MARIADB_USER'),
    password=os.getenv('MARIADB_PASSWORD'),
    database=os.getenv('MARIADB_DB')
)
print('Connection successful')
conn.close()
"

```

## Disk Space and Resource Issues

### Vault Storage Growing Too Large

```bash

## Check Raft storage size

du -sh /var/lib/vault

## List files

ls -lh /var/lib/vault/

## If too large, consider Raft compaction (advanced)

vault operator raft list-peers

## For production, consider separate storage backend

```

### MariaDB Storage Growing Too Large

```bash

## Check database size

mysql -u root -e "
SELECT table_schema AS 'Database',
ROUND(SUM(data_length + index_length) / 1024 / 1024 / 1024, 2) AS 'Size (GB)'
FROM information_schema.tables
GROUP BY table_schema;
"

## Check individual table sizes

mysql -u justnews -p -D justnews -e "
SELECT table_name, ROUND(((data_length + index_length) / 1024 / 1024), 2) AS 'Size (MB)'
FROM information_schema.tables
WHERE table_schema = 'justnews'
ORDER BY (data_length + index_length) DESC;
"

## Remove old articles

mysql -u justnews -p -D justnews -e "DELETE FROM articles WHERE created_at < DATE_SUB(NOW(), INTERVAL 90 DAY);"

## Optimize tables to reclaim space

mysql -u justnews -p -D justnews -e "OPTIMIZE TABLE articles;"

## Check available disk space

df -h /var/lib/mysql

```bash

### ChromaDB Storage Growing Too Large

```bash

## Check ChromaDB data directory

du -sh ~/.chroma  # or wherever ChromaDB stores data

## List tenants

python -c "
import chromadb
client = chromadb.HttpClient(host='localhost', port=3307)
print('Tenants:', client.list_tenants())
"

## Delete old collections if needed

python -c "
import chromadb
client = chromadb.HttpClient(host='localhost', port=3307)

## client.delete_collection(name='old_collection')

"

```

## Monitoring and Observability

### Check Service Status

```bash

## Full status report

sudo systemctl status vault mariadb chromadb

## Detailed service info

systemctl show vault
systemctl show mariadb
systemctl show chromadb

## Check service dependencies

sudo systemctl list-dependencies vault
sudo systemctl list-dependencies mariadb
sudo systemctl list-dependencies chromadb

```bash

### Monitor Resource Usage

```bash

## Real-time monitoring

watch -n 1 'sudo systemctl status vault mariadb chromadb'

## Memory usage

ps aux | grep -E 'vault|mysqld|chroma' | grep -v grep

## CPU usage

top -p $(pgrep -d, -f 'vault|mysqld|chroma')

## Disk usage

df -h /var/lib/vault /var/lib/mysql

```

### View Service Logs

```bash

## Recent logs for Vault

sudo journalctl -u vault -n 50

## Tail vault logs live

sudo journalctl -u vault -f

## Recent logs with timestamps

sudo journalctl -u vault --no-pager -n 100 -o short-iso

## Filter for errors

sudo journalctl -u vault -p err

## View all service logs

sudo journalctl -u vault -u mariadb -u chromadb -n 200

```bash

## Emergency Recovery

### Vault Emergency Procedure

```bash

## If Vault is corrupted beyond recovery:

## 1. Backup existing data

sudo cp -r /var/lib/vault /var/lib/vault.backup.$(date +%s)

## 2. Stop Vault

sudo systemctl stop vault

## 3. Backup init credentials

sudo cp /etc/justnews/vault-init.json /etc/justnews/vault-init.json.backup

## 4. Clear storage (DESTRUCTIVE)

sudo rm -rf /var/lib/vault/*

## 5. Restart Vault

sudo systemctl start vault

## 6. Reinitialize

vault operator init > /tmp/vault-init.txt
cat /tmp/vault-init.txt | sudo tee /etc/justnews/vault-init.json

## 7. Unseal

vault operator unseal (use keys from init output)

## 8. Reseed secrets

vault auth enable approle
vault write auth/approle/role/justnews ...
vault kv put secret/justnews ...

```

### MariaDB Emergency Procedure

```bash

## If MariaDB is corrupted:

## 1. Stop MariaDB

sudo systemctl stop mariadb

## 2. Backup data

sudo cp -r /var/lib/mysql /var/lib/mysql.backup.$(date +%s)

## 3. Check table integrity

sudo mysqld --user=mysql --datadir=/var/lib/mysql --innodb_force_recovery=1

## 4. If force recovery helps, dump and restore

mysqldump -u root --all-databases > /tmp/backup.sql

## 5. Clear data files

sudo rm -rf /var/lib/mysql/*
sudo rm -rf /var/lib/mysql/ib*

## 6. Restart

sudo systemctl restart mariadb

## 7. Restore from backup

mysql -u root < /tmp/backup.sql

```

## Getting Help

1. **Check Logs**: Always start with `sudo journalctl -u <service> -n 50`

1. **Verify Services**: Run `sudo systemctl status vault mariadb chromadb`

1. **Test Connectivity**: Use `check_databases.py` to validate full stack

1. **Consult Docs**:

- Vault: `docs/operations/VAULT_SETUP.md`

- Setup: `docs/operations/SETUP_GUIDE.md`

- Environment: `docs/operations/ENVIRONMENT_CONFIG.md`

1. **Enable Debug**: Set `set -x`in shell scripts or`--verbose` in commands
