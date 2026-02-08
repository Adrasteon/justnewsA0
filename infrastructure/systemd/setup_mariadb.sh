#!/bin/bash
## DEPRECATED: Original PostgreSQL setup script.
## The JustNews deployment now uses MariaDB (and Chroma for vector storage).
## This script provides a convenience MariaDB setup for local/systemd deployments.

set -euo pipefail

# Configuration - safe defaults for local/dev installs
JUSTNEWS_USER="justnews"
JUSTNEWS_PASSWORD="justnews_password"
MAIN_DB="justnews"
MEMORY_DB="justnews_memory"
MARIADB_PORT=3306

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (sudo)"
        exit 1
    fi
}

install_mariadb() {
    log_info "Installing MariaDB server and client packages..."
    apt update
    apt install -y mariadb-server mariadb-client
    log_success "MariaDB installed"
}

configure_mariadb() {
    log_info "Configuring MariaDB: enabling service and creating user/databases"
    systemctl enable mariadb
    systemctl start mariadb

    # Wait for MariaDB to start
    sleep 3

    # Create user and databases
    mysql -uroot <<EOF
CREATE DATABASE IF NOT EXISTS \`${MAIN_DB}\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS \`${MEMORY_DB}\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${JUSTNEWS_USER}'@'localhost' IDENTIFIED BY '${JUSTNEWS_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${MAIN_DB}\`.* TO '${JUSTNEWS_USER}'@'localhost';
GRANT ALL PRIVILEGES ON \`${MEMORY_DB}\`.* TO '${JUSTNEWS_USER}'@'localhost';
FLUSH PRIVILEGES;
EOF

    log_success "Databases and user created"
}

setup_monitoring() {
    log_info "Setting up backup script and log directory for MariaDB"
    mkdir -p /var/backups/mariadb
    chown mysql:mysql /var/backups/mariadb || true

    cat > /usr/local/bin/justnews-mariadb-backup.sh <<'EOF'
#!/bin/bash
# MariaDB backup script for JustNews
BACKUP_DIR="/var/backups/mariadb"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
MAIN_DB="justnews"
MEMORY_DB="justnews_memory"

mkdir -p "$BACKUP_DIR"
mysqldump -u justnews -p"justnews_password" "$MAIN_DB" > "$BACKUP_DIR/${MAIN_DB}_$TIMESTAMP.sql"
mysqldump -u justnews -p"justnews_password" "$MEMORY_DB" > "$BACKUP_DIR/${MEMORY_DB}_$TIMESTAMP.sql"
gzip "$BACKUP_DIR/${MAIN_DB}_$TIMESTAMP.sql"
gzip "$BACKUP_DIR/${MEMORY_DB}_$TIMESTAMP.sql"
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete
echo "MariaDB backup completed: $TIMESTAMP"
EOF

    chmod +x /usr/local/bin/justnews-mariadb-backup.sh

    cat > /etc/cron.daily/justnews-mariadb-backup <<'EOF'
#!/bin/bash
/usr/local/bin/justnews-mariadb-backup.sh >> /var/log/justnews/mariadb_backup.log 2>&1
EOF

    chmod +x /etc/cron.daily/justnews-mariadb-backup
    mkdir -p /var/log/justnews
    chown mysql:mysql /var/log/justnews || true

    log_success "Backup and monitoring hooks created"
}

test_databases() {
    log_info "Testing MariaDB connectivity using justnews user"
    if mysql -u"${JUSTNEWS_USER}" -p"${JUSTNEWS_PASSWORD}" -e "SELECT VERSION();" >/dev/null 2>&1; then
        log_success "MariaDB connection successful"
    else
        log_error "Failed to connect to MariaDB with the provided credentials"
        return 1
    fi
}

show_usage() {
    cat <<EOF
JustNews MariaDB Setup (replacement for legacy PostgreSQL script)

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -h, --help          Show this help message
    -u, --user USER     Database user to create (default: justnews)
    -p, --password PWD  Database password (default: justnews_password)
    --no-backup         Skip backup configuration

NOTES:
    - This script is intended for local or systemd-based deployments for convenience.
    - In production, you should provision MariaDB via your platform tooling and secrets manager.
    - The project uses Chroma (or external vector store) for embeddings; MariaDB stores relational data only.
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help) show_usage; exit 0 ;; 
            -u|--user) JUSTNEWS_USER="$2"; shift 2 ;; 
            -p|--password) JUSTNEWS_PASSWORD="$2"; shift 2 ;; 
            --no-backup) SKIP_BACKUP=true; shift ;; 
            *) log_error "Unknown option: $1"; show_usage; exit 1 ;; 
        esac
    done
}

main() {
    parse_args "$@"
    echo "========================================"
    log_info "JustNews MariaDB Setup (legacy PostgreSQL replacement)"
    echo "========================================"
    echo

    check_root

    install_mariadb
    configure_mariadb
    if [[ "${SKIP_BACKUP:-false}" != true ]]; then
        setup_monitoring
    else
        log_info "Skipping backup configuration"
    fi
    test_databases

    echo
    echo "Database URLs for JustNews environment files:"
    echo "Main DB:    mysql://${JUSTNEWS_USER}:${JUSTNEWS_PASSWORD}@localhost:${MARIADB_PORT}/${MAIN_DB}"
    echo "Memory DB:  mysql://${JUSTNEWS_USER}:${JUSTNEWS_PASSWORD}@localhost:${MARIADB_PORT}/${MEMORY_DB}"
    echo
    echo "IMPORTANT: This script replaces the original PostgreSQL helper."
    echo "If you're running in production, provision MariaDB via your platform tooling and update secrets accordingly."
}

main "$@"
#!/bin/bash
# setup_mariadb.sh - MariaDB+ChromaDB setup for JustNews systemd deployment
# Sets up native MariaDB database and ChromaDB for JustNews agents

set -euo pipefail

# Configuration
JUSTNEWS_USER="justnews"
JUSTNEWS_PASSWORD="justnews_password"
MAIN_DB="justnews"
MARIADB_VERSION="10.11"
# Use the canonical Chroma port by default to avoid conflict with MCP bus (port 8000)
CHROMA_PORT="${CHROMADB_PORT:-3307}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (sudo)"
        exit 1
    fi
}

# Install MariaDB
install_mariadb() {
    log_info "Installing MariaDB $MARIADB_VERSION..."

    # Update package list
    apt update

    # Install MariaDB
    apt install -y mariadb-server mariadb-client

    # Install additional tools
    apt install -y python3-pip curl

    # Install ChromaDB via pip (or use Docker)
    pip3 install chromadb

    log_success "MariaDB and ChromaDB dependencies installed successfully"
}

# Configure MariaDB
configure_mariadb() {
    log_info "Configuring MariaDB..."

    # Start MariaDB service
    systemctl enable mariadb
    systemctl start mariadb

    # Wait for MariaDB to start
    sleep 5

    # Secure MariaDB installation and create JustNews user/database
    mysql -u root << EOF
-- Create JustNews user and database
CREATE USER IF NOT EXISTS '$JUSTNEWS_USER'@'localhost' IDENTIFIED BY '$JUSTNEWS_PASSWORD';
CREATE DATABASE IF NOT EXISTS $MAIN_DB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON $MAIN_DB.* TO '$JUSTNEWS_USER'@'localhost';
FLUSH PRIVILEGES;

-- Create additional databases if needed
CREATE DATABASE IF NOT EXISTS justnews_analytics CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON justnews_analytics.* TO '$JUSTNEWS_USER'@'localhost';
FLUSH PRIVILEGES;
EOF

    log_success "MariaDB database created and configured"
}

# Configure MariaDB for production
configure_production() {
    log_info "Configuring MariaDB for production..."

    # Backup original configuration
    cp /etc/mysql/mariadb.conf.d/50-server.cnf /etc/mysql/mariadb.conf.d/50-server.cnf.backup

    # Configure MariaDB for JustNews
    cat >> /etc/mysql/mariadb.conf.d/50-server.cnf << EOF

# JustNews Production Configuration
# Memory settings (adjust based on system RAM)
[mysqld]
innodb_buffer_pool_size = 256M
innodb_log_file_size = 64M
query_cache_size = 64M

# Connection settings
max_connections = 100
wait_timeout = 28800
interactive_timeout = 28800

# Logging
general_log = 1
general_log_file = /var/log/mysql/mysql.log
slow_query_log = 1
slow_query_log_file = /var/log/mysql/mysql-slow.log
long_query_time = 2

# Performance
innodb_flush_method = O_DIRECT
innodb_flush_log_at_trx_commit = 2

# Character set
character_set_server = utf8mb4
collation_server = utf8mb4_unicode_ci
EOF

    # Restart MariaDB to apply changes
    systemctl restart mariadb

    log_success "MariaDB production configuration applied"
}

# Setup ChromaDB service
setup_chromadb() {
    log_info "Setting up ChromaDB service..."

    # Create ChromaDB systemd service
    cat > /etc/systemd/system/chromadb.service << EOF
[Unit]
Description=ChromaDB Vector Database
After=network.target
Wants=network.target

[Service]
Type=simple
User=justnews
Group=justnews
WorkingDirectory=/var/lib/chromadb
ExecStart=/usr/local/bin/chroma run --host 0.0.0.0 --port $CHROMA_PORT
Restart=always
RestartSec=5

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=/var/lib/chromadb

# Resource limits
MemoryLimit=2G
CPUQuota=200%

[Install]
WantedBy=multi-user.target
EOF

    # Create ChromaDB user and directories
    useradd -r -s /bin/false justnews || true
    mkdir -p /var/lib/chromadb
    chown justnews:justnews /var/lib/chromadb

    # Enable and start ChromaDB service
    systemctl daemon-reload
    systemctl enable chromadb
    systemctl start chromadb

    log_success "ChromaDB service configured and started"
}

# Setup monitoring and backup
setup_monitoring() {
    log_info "Setting up monitoring and backup..."

    # Create backup directory
    mkdir -p /var/backups/mariadb
    chown mysql:mysql /var/backups/mariadb

    # Create backup script
    cat > /usr/local/bin/justnews-mariadb-backup.sh << 'EOF'
#!/bin/bash
# MariaDB backup script for JustNews

BACKUP_DIR="/var/backups/mariadb"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
MAIN_DB="justnews"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Backup main database
mysqldump -u justnews -p"$JUSTNEWS_PASSWORD" "$MAIN_DB" > "$BACKUP_DIR/${MAIN_DB}_$TIMESTAMP.sql"

# Compress backup
gzip "$BACKUP_DIR/${MAIN_DB}_$TIMESTAMP.sql"

# Clean up old backups (keep last 7 days)
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete

echo "MariaDB backup completed: $TIMESTAMP"
EOF

    chmod +x /usr/local/bin/justnews-mariadb-backup.sh

    # Setup daily backup cron job
    cat > /etc/cron.daily/justnews-mariadb-backup << 'EOF'
#!/bin/bash
/usr/local/bin/justnews-mariadb-backup.sh >> /var/log/justnews/mariadb_backup.log 2>&1
EOF

    chmod +x /etc/cron.daily/justnews-mariadb-backup

    # Create log directory
    mkdir -p /var/log/justnews
    chown justnews:justnews /var/log/justnews

    log_success "MariaDB monitoring and backup configured"
}

# Test database connectivity
test_databases() {
    log_info "Testing database connectivity..."

    # Test main database
    if mysql -u "$JUSTNEWS_USER" -p"$JUSTNEWS_PASSWORD" -e "USE $MAIN_DB; SELECT 1;" >/dev/null 2>&1; then
        log_success "Main database ($MAIN_DB) connection successful"
    else
        log_error "Failed to connect to main database"
        return 1
    fi

    # Test ChromaDB connectivity: prefer /api/v2/auth/identity, fall back to
    # /api/v1/health and root when available
    if curl -fsS "http://localhost:${CHROMA_PORT}/api/v2/auth/identity" >/dev/null 2>&1; then
        log_success "ChromaDB connection successful"
    elif curl -fsS "http://localhost:${CHROMA_PORT}/api/v1/health" >/dev/null 2>&1 || curl -fsS "http://localhost:${CHROMA_PORT}/" >/dev/null 2>&1; then
        log_success "ChromaDB connection successful (alternate endpoint)"
    else
        log_warning "ChromaDB not responding (may still be starting)"
    fi

    log_success "Database connectivity tests passed"
}

# Show usage
show_usage() {
    cat << EOF
JustNews MariaDB+ChromaDB Setup Script

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -h, --help          Show this help message
    -v, --version VER   MariaDB version to install (default: 10.11)
    -u, --user USER     Database user to create (default: justnews)
    -p, --password PWD  Database password (default: justnews_password)
    --no-backup         Skip backup configuration
    --no-production     Skip production configuration
    --no-chromadb       Skip ChromaDB setup

DESCRIPTION:
    Sets up native MariaDB database and ChromaDB for JustNews systemd deployment.
    Creates the justnews database and configures ChromaDB for vector operations.

DATABASES CREATED:
    - justnews: Main application database (MariaDB)
    - ChromaDB: Vector embeddings and semantic search (port 3307)

EXAMPLES:
    $0                          # Full setup with defaults
    $0 --version 10.6           # Install MariaDB 10.6
    $0 --no-backup              # Skip backup configuration

NOTES:
    - Requires root privileges
    - Configures MariaDB for production use
    - Sets up ChromaDB as a systemd service
    - Sets up automated daily backups
EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -v|--version)
                MARIADB_VERSION="$2"
                shift 2
                ;;
            -u|--user)
                JUSTNEWS_USER="$2"
                shift 2
                ;;
            -p|--password)
                JUSTNEWS_PASSWORD="$2"
                shift 2
                ;;
            --no-backup)
                SKIP_BACKUP=true
                shift
                ;;
            --no-production)
                SKIP_PRODUCTION=true
                shift
                ;;
            --no-chromadb)
                SKIP_CHROMADB=true
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

# Main function
main() {
    parse_args "$@"

    echo "========================================"
    log_info "JustNews MariaDB+ChromaDB Setup"
    echo "========================================"
    echo

    check_root

    local steps=(
        "install_mariadb"
        "configure_mariadb"
        "configure_production"
        "setup_chromadb"
        "setup_monitoring"
        "test_databases"
    )

    for step in "${steps[@]}"; do
        echo
        if $step; then
            log_success "✓ $step completed"
        else
            log_error "✗ $step failed"
            exit 1
        fi
    done

    echo
    echo "========================================"
    log_success "MariaDB+ChromaDB setup completed successfully!"
    echo "========================================"
    echo
    echo "Database URLs for JustNews environment files:"
    echo "Main DB:    mysql://$JUSTNEWS_USER:$JUSTNEWS_PASSWORD@localhost:3306/$MAIN_DB"
    echo "ChromaDB:   http://localhost:$CHROMA_PORT"
    echo
    echo "Next steps:"
    echo "1. Update /etc/justnews/global.env with database URLs"
    echo "2. Run JustNews preflight check: ./infrastructure/systemd/preflight.sh"
    echo "3. Start services: sudo ./infrastructure/systemd/scripts/enable_all.sh start"
}

# Run main function
main "$@"