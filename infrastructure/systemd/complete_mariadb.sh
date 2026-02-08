#!/bin/bash
# JustNews MariaDB+ChromaDB Completion Script
# Completes the existing MariaDB+ChromaDB setup by adding missing components

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_SRC_DIR="$SCRIPT_DIR/examples"

echo "🚀 JustNews MariaDB+ChromaDB Completion Script"
echo "==============================================="

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "❌ This script should NOT be run as root. Please run as a regular user with sudo access."
   exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}📋 Checking current MariaDB+ChromaDB status...${NC}"

# Check if MariaDB is running
if ! systemctl is-active --quiet mariadb; then
    echo -e "${RED}❌ MariaDB service is not running${NC}"
    echo "Starting MariaDB..."
    sudo systemctl start mariadb
    sudo systemctl enable mariadb
fi

echo -e "${GREEN}✅ MariaDB is running${NC}"

# Check if ChromaDB is running
if ! systemctl is-active --quiet chromadb; then
    echo -e "${YELLOW}⚠️  ChromaDB service is not running${NC}"
    echo "Starting ChromaDB..."
    sudo systemctl start chromadb
    sudo systemctl enable chromadb
    sleep 5
fi

if systemctl is-active --quiet chromadb; then
    echo -e "${GREEN}✅ ChromaDB is running${NC}"
else
    echo -e "${RED}❌ ChromaDB failed to start${NC}"
    exit 1
fi

# Check existing databases
echo -e "${BLUE}📊 Checking existing databases...${NC}"
EXISTING_DBS=$(mysql -u justnews -pjustnews_password -e "SHOW DATABASES;" 2>/dev/null | grep -E "^justnews" || true)

if echo "$EXISTING_DBS" | grep -q "^justnews$"; then
    echo -e "${GREEN}✅ justnews database exists${NC}"
else
    echo -e "${RED}❌ justnews database missing${NC}"
    exit 1
fi

if echo "$EXISTING_DBS" | grep -q "^justnews_analytics$"; then
    echo -e "${GREEN}✅ justnews_analytics database exists${NC}"
else
    echo -e "${YELLOW}📝 justnews_analytics database needs to be created${NC}"
    sudo mysql -u root << EOF
CREATE DATABASE IF NOT EXISTS justnews_analytics CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON justnews_analytics.* TO 'justnews'@'localhost';
FLUSH PRIVILEGES;
EOF
    echo -e "${GREEN}✅ justnews_analytics database created${NC}"
fi

# Initialize database schema
echo -e "${BLUE}🏗️  Initializing database schema...${NC}"

# Check if schema already exists
TABLE_COUNT=$(mysql -u justnews -pjustnews_password -D justnews -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'justnews';" -B -N 2>/dev/null || echo "0")

if [[ "$TABLE_COUNT" -gt 0 ]]; then
    echo -e "${GREEN}✅ Database schema already initialized${NC}"
else
    echo -e "${YELLOW}📝 Initializing database schema...${NC}"

    # Run the MariaDB initialization SQL
    if [[ -f "$SCRIPT_DIR/../docker/init-mariadb.sql" ]]; then
        mysql -u justnews -pjustnews_password -D justnews < "$SCRIPT_DIR/../docker/init-mariadb.sql"
        echo -e "${GREEN}✅ Database schema initialized${NC}"
    else
        echo -e "${RED}❌ init-mariadb.sql not found${NC}"
        exit 1
    fi
fi

# Verify database access
echo -e "${BLUE}🔍 Verifying database access...${NC}"

# Test justnews database
if mysql -u justnews -pjustnews_password -D justnews -e "SELECT 1;" >/dev/null 2>&1; then
    echo -e "${GREEN}✅ justnews database accessible${NC}"
else
    echo -e "${RED}❌ Cannot access justnews database${NC}"
    exit 1
fi

# Test ChromaDB connectivity (prefer the auth/identity endpoint which is
# present on modern Chroma builds; fall back to /api/v1/health or root.)
CHROMA_HOST=${CHROMADB_HOST:-localhost}
# Default to the canonical Chroma port (3307) if not explicitly set
CHROMA_PORT_VAL=${CHROMADB_PORT:-${CHROMA_PORT:-3307}}
if curl -fsS "http://${CHROMA_HOST}:${CHROMA_PORT_VAL}/api/v2/auth/identity" >/dev/null 2>&1; then
    echo -e "${GREEN}✅ ChromaDB accessible${NC}"
else
    if curl -fsS "http://${CHROMA_HOST}:${CHROMA_PORT_VAL}/api/v1/health" >/dev/null 2>&1 || curl -fsS "http://${CHROMA_HOST}:${CHROMA_PORT_VAL}/" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ ChromaDB accessible (alternate endpoint)${NC}"
    else
        echo -e "${RED}❌ Cannot access ChromaDB${NC}"
        exit 1
    fi
fi

# Update environment files
echo -e "${BLUE}📝 Updating environment files...${NC}"

# Copy updated environment files to /etc/justnews/
sudo mkdir -p /etc/justnews
shopt -s nullglob
for src in "$ENV_SRC_DIR"/*.env "$ENV_SRC_DIR"/*.env.example; do
    base="$(basename "$src")"
    if [[ "$base" == *.env.example ]]; then
        dest_name="${base%.env.example}.env"
    else
        dest_name="$base"
    fi
    sudo cp "$src" "/etc/justnews/$dest_name"
done
shopt -u nullglob

echo -e "${GREEN}✅ Environment files updated${NC}"

# Create database backup script
echo -e "${BLUE}💾 Setting up backup configuration...${NC}"

sudo mkdir -p /var/backups/mariadb
sudo chown mysql:mysql /var/backups/mariadb

# Create backup script
sudo tee /usr/local/bin/justnews-mariadb-backup.sh > /dev/null << 'EOF'
#!/bin/bash
# JustNews MariaDB Backup Script

BACKUP_DIR="/var/backups/mariadb"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "📦 Creating MariaDB backups..."

# Backup justnews database
mysqldump -u justnews -pjustnews_password justnews > "$BACKUP_DIR/justnews_$TIMESTAMP.sql"
gzip "$BACKUP_DIR/justnews_$TIMESTAMP.sql"

echo "✅ Backup created:"
echo "   $BACKUP_DIR/justnews_$TIMESTAMP.sql.gz"

# Clean up old backups (keep last 7 days)
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete

echo "🧹 Old backups cleaned up"
EOF

sudo chmod +x /usr/local/bin/justnews-mariadb-backup.sh

# Setup daily backup cron job
if ! sudo crontab -l | grep -q justnews-mariadb-backup; then
    echo "Setting up daily backup cron job..."
    (sudo crontab -l ; echo "0 2 * * * /usr/local/bin/justnews-mariadb-backup.sh") | sudo crontab -
    echo -e "${GREEN}✅ Daily backup cron job configured${NC}"
else
    echo -e "${GREEN}✅ Daily backup cron job already exists${NC}"
fi

# Final verification
echo -e "${BLUE}🎯 Final verification...${NC}"

echo "Database Status:"
echo "  justnews: $(mysql -u justnews -pjustnews_password -D justnews -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'justnews';" -B -N 2>/dev/null || echo "0") tables"

echo "ChromaDB Status:"
# Prefer the modern identity endpoint, fall back to v1/health or root
if curl -fsS "http://${CHROMA_HOST}:${CHROMA_PORT_VAL}/api/v2/auth/identity" >/dev/null 2>&1; then
    echo "  ChromaDB: ✅ Running (identity endpoint)"
elif curl -fsS "http://${CHROMA_HOST}:${CHROMA_PORT_VAL}/api/v1/health" >/dev/null 2>&1 || curl -fsS "http://${CHROMA_HOST}:${CHROMA_PORT_VAL}/" >/dev/null 2>&1; then
    echo "  ChromaDB: ✅ Running (alternate endpoint)"
else
    echo "  ChromaDB: ❌ Not responding"
fi

echo ""
echo -e "${GREEN}🎉 MariaDB+ChromaDB completion successful!${NC}"
echo ""
echo "Summary of changes:"
echo "  ✅ Verified existing justnews database"
echo "  ✅ Created justnews_analytics database"
echo "  ✅ Initialized database schema"
echo "  ✅ Verified ChromaDB connectivity"
echo "  ✅ Updated environment files with correct credentials"
echo "  ✅ Configured automated backups"
echo ""
echo "Environment files location: /etc/justnews/"
echo "Backup location: /var/backups/mariadb/"
echo "Backup script: /usr/local/bin/justnews-mariadb-backup.sh"
echo ""
echo "Next steps:"
echo "  1. Enable systemd services: sudo ./infrastructure/systemd/scripts/enable_all.sh enable"
echo "  2. Start all services: sudo ./infrastructure/systemd/scripts/enable_all.sh start"
echo "  3. Health check: sudo ./infrastructure/systemd/scripts/health_check.sh"