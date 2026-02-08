#!/bin/bash

################################################################################
# JustNews Monitoring Infrastructure Quick Deploy
# 
# This script automates the complete deployment of Prometheus, Grafana, and
# Node Exporter with pre-configured dashboards from the USB drive.
#
# Usage: sudo bash scripts/deploy_monitoring.sh [--skip-install] [--skip-start]
#
# Options:
#   --skip-install    Skip package installation (use if already installed)
#   --skip-start      Install but don't start services
#   --help           Show this help message
################################################################################

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
USB_PATH="${USB_PATH:-/media/adra/37f1914d-e5fd-48ca-8c24-22d5f4e2e9dd}"
USB_MONITORING="${USB_PATH}/etc/justnews/monitoring"
INSTALL_PATH="/etc/justnews/monitoring"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-}"
SKIP_INSTALL=${SKIP_INSTALL:-false}
SKIP_START=${SKIP_START:-false}

# Functions
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
    exit 1
}

print_header() {
    echo -e "\n${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}\n"
}

show_help() {
    grep "^# " "$0" | head -20
    exit 0
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
    fi
}

check_usb() {
    if [[ ! -d "$USB_MONITORING" ]]; then
        log_error "USB drive not found at: $USB_MONITORING"
    fi
    
    if [[ ! -f "$USB_MONITORING/prometheus.yml" ]]; then
        log_error "Prometheus config not found at: $USB_MONITORING/prometheus.yml"
    fi
    
    if [[ ! -f "$USB_MONITORING/grafana.ini" ]]; then
        log_error "Grafana config not found at: $USB_MONITORING/grafana.ini"
    fi
    
    log_success "USB drive detected at: $USB_MONITORING"
}

install_packages() {
    if [[ "$SKIP_INSTALL" == "true" ]]; then
        log_warning "Skipping package installation (--skip-install)"
        return 0
    fi
    
    print_header "Step 1: Installing Packages"
    
    log_info "Updating package lists..."
    apt-get update > /dev/null 2>&1 || log_error "Failed to update package lists"
    
    log_info "Installing Prometheus..."
    apt-get install -y prometheus > /dev/null 2>&1 || log_error "Failed to install prometheus"
    
    log_info "Installing Grafana..."
    apt-get install -y grafana > /dev/null 2>&1 || log_error "Failed to install grafana"
    
    log_info "Installing Node Exporter..."
    apt-get install -y prometheus-node-exporter > /dev/null 2>&1 || log_error "Failed to install node-exporter"
    
    log_success "Packages installed successfully"
}

copy_configs() {
    print_header "Step 2: Copying Configuration Files"
    
    log_info "Creating directory structure at: $INSTALL_PATH"
    mkdir -p "$INSTALL_PATH/grafana/provisioning"/{datasources,dashboards}
    mkdir -p "$INSTALL_PATH/grafana/dashboards"
    
    log_info "Ensuring /etc/grafana directories exist..."
    mkdir -p /etc/grafana/provisioning/{datasources,dashboards}
    
    log_info "Copying Prometheus configuration..."
    cp "$USB_MONITORING/prometheus.yml" "$INSTALL_PATH/" || log_error "Failed to copy prometheus.yml"
    
    log_info "Copying Grafana configuration..."
    cp "$USB_MONITORING/grafana.ini" "$INSTALL_PATH/" || log_error "Failed to copy grafana.ini (to $INSTALL_PATH)"
    cp "$USB_MONITORING/grafana.ini" "/etc/grafana/grafana.ini" || log_error "Failed to copy grafana.ini (to /etc/grafana)"
    
    log_info "Copying Grafana provisioning configs..."
    cp -r "$USB_MONITORING/grafana/provisioning/"* "$INSTALL_PATH/grafana/provisioning/" 2>/dev/null || \
        log_error "Failed to copy provisioning configs (to $INSTALL_PATH)"
    cp -r "$USB_MONITORING/grafana/provisioning/"* "/etc/grafana/provisioning/" 2>/dev/null || \
        log_error "Failed to copy provisioning configs (to /etc/grafana/provisioning)"
    
    log_info "Copying Grafana dashboards..."
    cp -r "$USB_MONITORING/grafana/dashboards/"* "$INSTALL_PATH/grafana/dashboards/" 2>/dev/null || \
        log_warning "Failed to copy dashboards (to $INSTALL_PATH, continuing anyway)"
    cp -r "$USB_MONITORING/grafana/dashboards/"* "/etc/grafana/provisioning/dashboards/" 2>/dev/null || \
        log_warning "Failed to copy dashboards (to /etc/grafana/provisioning/dashboards, continuing anyway)"

    # Ensure dashboards provider YAML points to standard provisioning path
    if [[ -f "/etc/grafana/provisioning/dashboards/justnews.yaml" ]]; then
        log_info "Normalizing dashboards provider path in justnews.yaml"
        sed -i 's#^\s*path:\s*/etc/justnews/monitoring/grafana/dashboards#      path: /etc/grafana/provisioning/dashboards#' \
            "/etc/grafana/provisioning/dashboards/justnews.yaml" || \
            log_warning "Failed to normalize dashboards provider path"
    fi
    
    log_success "Configuration files copied successfully"
}

setup_directories() {
    print_header "Step 3: Setting Up Directories and Permissions"
    
    log_info "Creating Prometheus data directory..."
    mkdir -p /var/lib/prometheus
    chown prometheus:prometheus /var/lib/prometheus
    chmod 755 /var/lib/prometheus
    
    log_info "Creating Grafana data directory..."
    mkdir -p /var/lib/grafana
    chown grafana:grafana /var/lib/grafana
    chmod 755 /var/lib/grafana
    
    log_info "Creating Grafana logs directory..."
    mkdir -p /var/log/grafana
    chown grafana:grafana /var/log/grafana
    chmod 755 /var/log/grafana

    log_info "Creating Grafana runtime directory..."
    mkdir -p /run/grafana
    chown grafana:grafana /run/grafana
    chmod 755 /run/grafana
    
    log_info "Creating Node Exporter textfile directory..."
    mkdir -p /var/lib/node_exporter/textfile_collector
    chown nobody:nogroup /var/lib/node_exporter/textfile_collector
    
    log_info "Setting permissions on monitoring configs..."
    chmod 644 "$INSTALL_PATH/prometheus.yml"
    chmod 644 "$INSTALL_PATH/grafana.ini"
    chmod 755 "$INSTALL_PATH/grafana/provisioning"
    chmod 644 "$INSTALL_PATH/grafana/provisioning"/*/*.y*ml 2>/dev/null || true
    chmod 755 "$INSTALL_PATH/grafana/dashboards"
    chmod 644 "$INSTALL_PATH/grafana/dashboards"/*.json 2>/dev/null || true
    
    # Also set permissions for /etc/grafana
    chmod 644 "/etc/grafana/grafana.ini" 2>/dev/null || true
    chmod 755 "/etc/grafana/provisioning" 2>/dev/null || true
    chmod 644 "/etc/grafana/provisioning"/*/*.y*ml 2>/dev/null || true
    chmod 755 "/etc/grafana/provisioning/dashboards" 2>/dev/null || true
    chmod 644 "/etc/grafana/provisioning/dashboards"/*.json 2>/dev/null || true
    
    log_success "Directories and permissions configured"
}

create_systemd_units() {
    print_header "Step 4: Creating Systemd Units"
    
    log_info "Creating Prometheus systemd unit..."
    cat > /etc/systemd/system/prometheus.service << 'EOF'
[Unit]
Description=Prometheus Monitoring System
Documentation=https://prometheus.io/docs/
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=prometheus
Group=prometheus
ProtectSystem=full
ProtectHome=yes
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes

# Read configuration from /etc/justnews/monitoring
ExecStart=/usr/bin/prometheus \
  --config.file=/etc/justnews/monitoring/prometheus.yml \
  --storage.tsdb.path=/var/lib/prometheus \
  --storage.tsdb.retention.time=30d \
  --web.enable-lifecycle

SyslogIdentifier=prometheus
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF
    
    log_info "Creating Grafana systemd unit..."
    cat > /etc/systemd/system/grafana-server.service << 'EOF'
[Unit]
Description=Grafana instance
Documentation=http://docs.grafana.org
Wants=network-online.target
After=network-online.target
After=postgresql.service mariadb.service mysql.service influxdb.service

[Service]
EnvironmentFile=/etc/default/grafana-server
User=grafana
Group=grafana
Type=simple
Restart=on-failure
RestartSec=10s
WorkingDirectory=/usr/share/grafana
RuntimeDirectory=grafana
RuntimeDirectoryMode=0750
ExecStart=/usr/share/grafana/bin/grafana server \
                            --config=${CONF_FILE} \
                            --pidfile=${PID_FILE_DIR}/grafana-server.pid \
                            --packaging=deb \
                            cfg:default.paths.logs=${LOG_DIR} \
                            cfg:default.paths.data=${DATA_DIR} \
                            cfg:default.paths.plugins=${PLUGINS_DIR} \
                            cfg:default.paths.provisioning=${PROVISIONING_CFG_DIR}

LimitNOFILE=10000
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
EOF
    
    log_info "Creating Node Exporter systemd unit..."
    cat > /etc/systemd/system/prometheus-node-exporter.service << 'EOF'
[Unit]
Description=Prometheus Node Exporter
Documentation=https://github.com/prometheus/node_exporter
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=prometheus
Group=prometheus
ProtectSystem=full
ProtectHome=yes
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
ReadWritePaths=/var/lib/node_exporter/textfile_collector

ExecStart=/usr/bin/prometheus-node-exporter \
  --collector.textfile.directory=/var/lib/node_exporter/textfile_collector \
  --web.listen-address=127.0.0.1:9100

SyslogIdentifier=node-exporter
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd to recognize new units
    systemctl daemon-reload || log_error "Failed to reload systemd"
    
    log_success "Systemd units created"
}

enable_services() {
    print_header "Step 5: Enabling Services"
    
    log_info "Enabling Prometheus..."
    systemctl enable prometheus > /dev/null 2>&1 || log_error "Failed to enable prometheus"
    
    log_info "Enabling Grafana..."
    systemctl enable grafana-server > /dev/null 2>&1 || log_error "Failed to enable grafana-server"
    
    log_info "Enabling Node Exporter..."
    systemctl enable prometheus-node-exporter > /dev/null 2>&1 || log_error "Failed to enable node-exporter"
    
    log_success "Services enabled for auto-start on boot"
}

start_services() {
    if [[ "$SKIP_START" == "true" ]]; then
        log_warning "Skipping service startup (--skip-start)"
        return 0
    fi
    
    print_header "Step 6: Starting Services"
    
    log_info "Starting Prometheus..."
    systemctl start prometheus || log_error "Failed to start prometheus"
    sleep 2
    
    log_info "Starting Grafana..."
    systemctl start grafana-server || log_error "Failed to start grafana-server"
    sleep 2
    
    log_info "Starting Node Exporter..."
    systemctl start prometheus-node-exporter || log_error "Failed to start node-exporter"
    sleep 1
    
    log_success "Services started"
}

wait_for_services() {
    print_header "Step 7: Waiting for Services to Be Ready"
    
    log_info "Waiting for Prometheus to be ready..."
    local count=0
    while ! curl -s http://127.0.0.1:9090/-/healthy > /dev/null 2>&1; do
        count=$((count + 1))
        if [ $count -gt 30 ]; then
            log_warning "Prometheus took too long to start, continuing anyway..."
            break
        fi
        sleep 1
    done
    log_success "Prometheus is ready"
    
    log_info "Waiting for Grafana to be ready..."
    count=0
    while ! curl -s http://127.0.0.1:3000/api/health > /dev/null 2>&1; do
        count=$((count + 1))
        if [ $count -gt 30 ]; then
            log_warning "Grafana took too long to start, continuing anyway..."
            break
        fi
        sleep 1
    done
    log_success "Grafana is ready"
    
    log_info "Waiting for Node Exporter to be ready..."
    curl -s http://127.0.0.1:9100/metrics > /dev/null 2>&1 || log_warning "Node Exporter not responding"
    log_success "Node Exporter is ready"
}

verify_deployment() {
    print_header "Step 8: Verifying Deployment"
    
    log_info "Checking Prometheus status..."
    if systemctl is-active --quiet prometheus; then
        log_success "Prometheus is running"
    else
        log_error "Prometheus is not running"
    fi
    
    log_info "Checking Grafana status..."
    if systemctl is-active --quiet grafana-server; then
        log_success "Grafana is running"
    else
        log_error "Grafana is not running"
    fi
    
    log_info "Checking Node Exporter status..."
    if systemctl is-active --quiet prometheus-node-exporter; then
        log_success "Node Exporter is running"
    else
        log_error "Node Exporter is not running"
    fi
    
    log_info "Checking configuration files..."
    [[ -f "$INSTALL_PATH/prometheus.yml" ]] && log_success "Prometheus config found" || log_error "Prometheus config missing"
    [[ -f "$INSTALL_PATH/grafana.ini" ]] && log_success "Grafana config found" || log_error "Grafana config missing"
    [[ -d "$INSTALL_PATH/grafana/dashboards" ]] && log_success "Dashboard directory found" || log_error "Dashboard directory missing"
}

set_grafana_password() {
    print_header "Step 9: Configuring Grafana Security"
    
    # Generate strong password if not provided
    if [[ -z "$GRAFANA_PASSWORD" ]]; then
        GRAFANA_PASSWORD=$(openssl rand -base64 24)
        log_warning "Generated random Grafana admin password"
    fi
    
    log_info "Setting Grafana admin password..."
    if grafana-cli admin reset-admin-password "$GRAFANA_PASSWORD" > /dev/null 2>&1; then
        log_success "Grafana admin password set"
        echo -e "\n${YELLOW}GRAFANA ADMIN PASSWORD:${NC} $GRAFANA_PASSWORD\n"
    else
        log_warning "Failed to set Grafana password via CLI (may need to do manually)"
    fi
}

verify_targets() {
    print_header "Step 10: Verifying Prometheus Targets"
    
    log_info "Waiting a moment for Prometheus to scrape targets..."
    sleep 5
    
    log_info "Checking Prometheus targets..."
    if curl -s http://127.0.0.1:9090/api/v1/targets?state=active 2>/dev/null | grep -q "prometheus"; then
        log_success "Prometheus targets are being scraped"
    else
        log_warning "Prometheus targets may not be scraped yet (check http://localhost:9090/targets)"
    fi
}

display_summary() {
    print_header "Deployment Complete! ✅"
    
    cat << EOF

📊 MONITORING INFRASTRUCTURE DEPLOYED

Services Status:
  • Prometheus:      Running on http://127.0.0.1:9090 (internal)
  • Grafana:         Running on http://localhost:3000
  • Node Exporter:   Running on http://127.0.0.1:9100 (internal)

Configuration:
  • Prometheus config:    $INSTALL_PATH/prometheus.yml
  • Grafana config:       $INSTALL_PATH/grafana.ini
  • Dashboards:          $INSTALL_PATH/grafana/dashboards/
  • Data storage:        /var/lib/prometheus (Prometheus)
    • Data storage:        /var/lib/grafana (Grafana)

Access Dashboards:
  📈 Grafana:       http://localhost:3000
     Default user:  admin
     Password:      (see above if set)

  📊 Prometheus:    http://localhost:9090
     Targets:       http://localhost:9090/targets
     Metrics:       http://localhost:9090/metrics

Dashboards Available:
  ✓ System Overview (fleet health, GPU, network, errors)
  ✓ JustNews Operations (service health, agents, crawler)
  ✓ Business Metrics (processing rates, crawl quality)
  ✓ Ingest/Archive (article pipeline)
  ✓ Parity Analysis (extraction quality)

Next Steps:
  1. Change Grafana admin password (if default was used)
  2. Verify dashboards are loading data (may take 1-2 minutes)
  3. Check Prometheus targets: http://localhost:9090/targets
  4. Configure AlertManager and notifications (optional)

Documentation:
  • Setup guide:        docs/operations/MONITORING_INFRASTRUCTURE.md
  • Troubleshooting:    docs/operations/TROUBLESHOOTING.md
  • All documentation:  docs/DOCUMENTATION_INDEX.md

Service Management:
  • Check status:       sudo systemctl status prometheus
  • View logs:          sudo journalctl -u prometheus -f
  • Restart service:    sudo systemctl restart prometheus

════════════════════════════════════════════════════════════════════════════════

EOF
}

# Main execution
main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-install)
                SKIP_INSTALL=true
                shift
                ;;
            --skip-start)
                SKIP_START=true
                shift
                ;;
            --help)
                show_help
                ;;
            *)
                log_error "Unknown option: $1"
                ;;
        esac
    done
    
    print_header "JustNews Monitoring Infrastructure Quick Deploy"
    
    check_root
    check_usb
    install_packages
    copy_configs
    setup_directories
    create_systemd_units
    enable_services
    start_services
    wait_for_services
    verify_deployment
    set_grafana_password
    verify_targets
    display_summary
}

# Run main function
main "$@"
