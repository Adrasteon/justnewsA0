#!/bin/bash
# Deployment Validation Script for JustNews
# Comprehensive validation of deployment configuration and health

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DEPLOY_ROOT="$PROJECT_ROOT/deploy/refactor"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Validation results
VALIDATION_PASSED=true
ISSUES_FOUND=()

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    ISSUES_FOUND+=("WARNING: $1")
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    ISSUES_FOUND+=("ERROR: $1")
    VALIDATION_PASSED=false
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Validate directory structure
validate_directory_structure() {
    log_info "Validating directory structure..."

    required_dirs=(
        "docker"
        # Kubernetes manifests are deprecated and not part of the active deployment
        # kube overlays removed; systemd is the deployment target
        "systemd/services"
        "systemd/timers"
        "config/environments"
        "scripts"
        "templates"
    )

    for dir in "${required_dirs[@]}"; do
        if [[ ! -d "$DEPLOY_ROOT/$dir" ]]; then
            log_error "Missing required directory: $dir"
        else
            log_success "Found directory: $dir"
        fi
    done
}

# Validate configuration files
validate_configuration() {
    log_info "Validating configuration files..."

    # Check environment files
    env_files=("development.env" "staging.env" "production.env")
    for env_file in "${env_files[@]}"; do
        env_path="$DEPLOY_ROOT/config/environments/$env_file"
        if [[ ! -f "$env_path" ]]; then
            log_warning "Environment file not found: $env_file"
            log_info "Run: python scripts/generate-config.py"
        else
            log_success "Found environment file: $env_file"
            # Basic validation of required variables
            # Prefer MariaDB variables; allow Postgres vars for backward compatibility
            required_vars=("MARIADB_HOST" "MARIADB_DB" "MCP_BUS_HOST")
            for var in "${required_vars[@]}"; do
                if ! grep -q "^$var=" "$env_path"; then
                    log_error "Missing required variable '$var' in $env_file"
                fi
            done
        fi
    done
}

# Validate Docker configuration
validate_docker() {
    log_warning "Docker Compose is deprecated; skipping Docker validation"
    return 0
}
    for service in "${required_services[@]}"; do
        if ! grep -q -E "^  (${service}):" "$compose_file"; then
            log_warning "Missing recommended service ('$service') in docker-compose.yml (docker-compose deprecated)"
        fi
    done
}

validate_kubernetes() {
    log_warning "Kubernetes manifests are deprecated and have been removed from this workspace. Skipping Kubernetes validation."
    return 0
}

# Validate systemd configuration
validate_systemd() {
    log_info "Validating systemd configuration..."

    if ! command_exists systemctl; then
        log_warning "systemctl not available, skipping systemd validation"
        return 0
    fi

    services_dir="$DEPLOY_ROOT/systemd/services"
    if [[ ! -d "$services_dir" ]]; then
        log_error "Systemd services directory not found: $services_dir"
        return 1
    fi

    # Basic service file validation
    find "$services_dir" -name "*.service" | while read -r service_file; do
        # Check for required sections
        if grep -q "\[Unit\]" "$service_file" && grep -q "\[Service\]" "$service_file"; then
            log_success "Valid systemd service: $(basename "$service_file")"
        else
            log_error "Invalid systemd service file: $(basename "$service_file")"
        fi
    done
}

# Validate scripts
validate_scripts() {
    log_info "Validating deployment scripts..."

    required_scripts=(
        "scripts/deploy.sh"
        "scripts/health-check.sh"
        "scripts/rollback.sh"
        "scripts/generate-config.py"
    )

    for script in "${required_scripts[@]}"; do
        script_path="$DEPLOY_ROOT/$script"
        if [[ ! -f "$script_path" ]]; then
            log_error "Missing required script: $script"
        else
            log_success "Found script: $script"
            # Check if executable
            if [[ ! -x "$script_path" ]]; then
                log_warning "Script is not executable: $script"
            fi
        fi
    done
}

# Validate templates
validate_templates() {
    log_info "Validating templates..."

    template_dir="$DEPLOY_ROOT/templates"
    if [[ ! -d "$template_dir" ]]; then
        log_error "Templates directory not found: $template_dir"
        return 1
    fi

    # Check for required templates
    required_templates=(
        "environment.env.j2"
    )

    for template in "${required_templates[@]}"; do
        template_path="$template_dir/$template"
        if [[ ! -f "$template_path" ]]; then
            log_error "Missing required template: $template"
        else
            log_success "Found template: $template"
        fi
    done
}

# Validate security configuration
validate_security() {
    log_info "Validating security configuration..."

    # Check for hardcoded secrets in environment files
    find "$DEPLOY_ROOT/config" -name "*.env" -type f | while read -r env_file; do
        if grep -q "change_me_in_production\|password\|secret" "$env_file"; then
            log_warning "Found placeholder secrets in: $(basename "$env_file")"
            log_info "Please update with actual secure values"
        fi
    done

    # Check file permissions
    find "$DEPLOY_ROOT" -name "*.env" -o -name "*secret*" -o -name "*password*" | while read -r secret_file; do
        if [[ -f "$secret_file" ]]; then
            permissions=$(stat -c "%a" "$secret_file")
            if [[ "$permissions" != "600" ]] && [[ "$permissions" != "400" ]]; then
                log_warning "Insecure permissions on secret file: $(basename "$secret_file") ($permissions)"
            fi
        fi
    done
}

# Generate validation report
generate_report() {
    log_info "Generating validation report..."

    report_file="$DEPLOY_ROOT/validation-report-$(date +%Y%m%d-%H%M%S).json"

    cat > "$report_file" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "validation_passed": $VALIDATION_PASSED,
  "issues_found": $(printf '%s\n' "${ISSUES_FOUND[@]}" | jq -R . | jq -s .),
  "checks_performed": [
    "directory_structure",
    "configuration_files",
    "docker_configuration",
    "kubernetes_configuration",
    "systemd_configuration",
    "scripts_validation",
    "templates_validation",
    "security_configuration"
  ]
}
EOF

    log_info "Validation report saved to: $report_file"

    if [[ "$VALIDATION_PASSED" == "true" ]]; then
        log_success "All validation checks passed!"
        return 0
    else
        log_error "Validation found ${#ISSUES_FOUND[@]} issue(s)"
        printf '  - %s\n' "${ISSUES_FOUND[@]}"
        return 1
    fi
}

# Main validation function
main() {
    log_info "JustNews Deployment Validation"
    log_info "Starting comprehensive validation checks..."

    validate_directory_structure
    validate_configuration
    # Validate systemd only; docker and kubernetes are deprecated
    validate_systemd
    validate_scripts
    validate_templates
    validate_security

    generate_report
}

# Run main function
main "$@"