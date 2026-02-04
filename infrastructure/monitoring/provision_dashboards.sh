#!/bin/bash

####################################################################################################
# JustNews Grafana Dashboard Provisioning Script
####################################################################################################
# Purpose:      Automatically provision all 5 JustNews enterprise dashboards into Grafana
# Usage:        ./provision_dashboards.sh [--grafana-url URL] [--dry-run]
# Author:       JustNews DevOps
# Last Updated: February 3, 2026
####################################################################################################

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARDS_DIR="$(cd "${SCRIPT_DIR}/../../monitoring/dashboards/generated" && pwd)"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-admin}"
DRY_RUN="${DRY_RUN:-false}"
VERBOSE="${VERBOSE:-false}"
DATASOURCE_NAME="Prometheus"

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
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_verbose() {
    if [[ "${VERBOSE}" == "true" ]]; then
        echo -e "${BLUE}[DEBUG]${NC} $1"
    fi
}

####################################################################################################
# Check Prerequisites
####################################################################################################

check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check for required commands
    local required_commands=("curl" "jq")
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            log_error "Required command not found: $cmd"
            exit 1
        fi
    done

    # Check dashboard directory exists
    if [[ ! -d "${DASHBOARDS_DIR}" ]]; then
        log_error "Dashboards directory not found: ${DASHBOARDS_DIR}"
        exit 1
    fi

    # Check dashboard files exist
    local dashboards=(
        "system_health_dashboard.json"
        "request_performance_dashboard.json"
        "pipeline_quality_dashboard.json"
        "agent_status_dashboard.json"
        "operational_overview_dashboard.json"
    )

    for dash in "${dashboards[@]}"; do
        if [[ ! -f "${DASHBOARDS_DIR}/${dash}" ]]; then
            log_error "Dashboard file not found: ${DASHBOARDS_DIR}/${dash}"
            exit 1
        fi
    done

    log_success "Prerequisites check passed"
}

####################################################################################################
# Check Grafana Connectivity
####################################################################################################

check_grafana_connection() {
    log_info "Checking Grafana connectivity..."

    local response
    response=$(curl -s -w "\n%{http_code}" -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
        "${GRAFANA_URL}/api/health" || true)

    local http_code
    http_code=$(echo "$response" | tail -n 1)

    if [[ "${http_code}" != "200" ]]; then
        log_error "Cannot connect to Grafana at ${GRAFANA_URL}"
        log_error "HTTP Status Code: ${http_code}"
        log_error "Make sure Grafana is running and accessible"
        exit 1
    fi

    log_success "Connected to Grafana at ${GRAFANA_URL}"
}

####################################################################################################
# Get or Create Datasource
####################################################################################################

get_or_create_datasource() {
    log_info "Checking Prometheus datasource..."

    # Try to get existing datasource
    local datasource_response
    datasource_response=$(curl -s -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
        "${GRAFANA_URL}/api/datasources/name/${DATASOURCE_NAME}" || true)

    local datasource_id
    datasource_id=$(echo "$datasource_response" | jq -r '.id // empty' 2>/dev/null || true)

    if [[ -n "${datasource_id}" ]]; then
        log_success "Found existing Prometheus datasource (ID: ${datasource_id})"
        echo "${datasource_id}"
        return 0
    fi

    log_warning "Prometheus datasource not found, attempting to create..."

    # Create datasource
    local create_response
    create_response=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
        "${GRAFANA_URL}/api/datasources" \
        -d '{
            "name": "'"${DATASOURCE_NAME}"'",
            "type": "prometheus",
            "url": "http://localhost:9090",
            "access": "proxy",
            "isDefault": true,
            "jsonData": {
                "timeInterval": "15s"
            }
        }' || true)

    datasource_id=$(echo "$create_response" | jq -r '.id // empty' 2>/dev/null || true)

    if [[ -n "${datasource_id}" ]]; then
        log_success "Created Prometheus datasource (ID: ${datasource_id})"
        echo "${datasource_id}"
    else
        log_error "Failed to create Prometheus datasource"
        log_verbose "Response: $create_response"
        exit 1
    fi
}

####################################################################################################
# Create JustNews Dashboard Folder
####################################################################################################

create_dashboard_folder() {
    log_info "Ensuring JustNews dashboard folder exists..."

    # Try to get existing folder
    local folder_response
    folder_response=$(curl -s -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
        "${GRAFANA_URL}/api/folders" | jq '.[] | select(.title=="JustNews") // empty' || true)

    local folder_id
    folder_id=$(echo "$folder_response" | jq -r '.id // empty' 2>/dev/null || true)

    if [[ -n "${folder_id}" ]]; then
        log_success "Found existing folder (ID: ${folder_id})"
        echo "${folder_id}"
        return 0
    fi

    log_verbose "Creating JustNews folder..."

    # Create folder
    local create_response
    create_response=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
        "${GRAFANA_URL}/api/folders" \
        -d '{
            "title": "JustNews",
            "description": "JustNews Enterprise Dashboards"
        }' || true)

    folder_id=$(echo "$create_response" | jq -r '.id // empty' 2>/dev/null || true)

    if [[ -n "${folder_id}" ]]; then
        log_success "Created JustNews folder (ID: ${folder_id})"
        echo "${folder_id}"
    else
        log_error "Failed to create JustNews folder"
        log_verbose "Response: $create_response"
        exit 1
    fi
}

####################################################################################################
# Import Dashboard
####################################################################################################

import_dashboard() {
    local dashboard_file="$1"
    local folder_id="$2"
    local datasource_id="$3"

    local dashboard_name
    dashboard_name=$(basename "$dashboard_file" .json)

    log_info "Importing dashboard: ${dashboard_name}..."

    # Read dashboard file
    if [[ ! -f "${dashboard_file}" ]]; then
        log_error "Dashboard file not found: ${dashboard_file}"
        return 1
    fi

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_verbose "[DRY-RUN] Would import: ${dashboard_name}"
        jq empty "${dashboard_file}" >/dev/null 2>&1 && log_success "[DRY-RUN] Dashboard JSON validated"
        return 0
    fi

    # Import dashboard with simple curl request
    local import_response
    import_response=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
        "${GRAFANA_URL}/api/dashboards/db" \
        -d @<(jq '.folderId = '"${folder_id}"' | .overwrite = true' "${dashboard_file}") || true)

    # Check for success
    if echo "$import_response" | jq -e '.id' >/dev/null 2>&1; then
        local dashboard_id
        dashboard_id=$(echo "$import_response" | jq -r '.id // empty')
        log_success "Imported dashboard: ${dashboard_name} (ID: ${dashboard_id})"
        return 0
    else
        log_error "Failed to import dashboard: ${dashboard_name}"
        log_verbose "Response: $import_response"
        return 1
    fi
}

####################################################################################################
# List Imported Dashboards
####################################################################################################

list_dashboards() {
    log_info "Listing imported JustNews dashboards..."

    local dashboards
    dashboards=$(curl -s -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
        "${GRAFANA_URL}/api/dashboards" | jq '.[] | select(.tags[] | contains("enterprise")) | {title, uid, tags}' 2>/dev/null || true)

    if [[ -z "${dashboards}" ]]; then
        log_warning "No enterprise dashboards found"
        return 1
    fi

    echo "$dashboards" | while read -r line; do
        if [[ -n "${line}" ]]; then
            echo "  $line"
        fi
    done

    return 0
}

####################################################################################################
# Verify Dashboards
####################################################################################################

verify_dashboards() {
    log_info "Verifying dashboard imports..."

    local dashboard_uids=(
        "system-health-premium"
        "request-performance-premium"
        "pipeline-quality-premium"
        "agent-status-premium"
        "operational-overview-premium"
    )

    local success_count=0
    local fail_count=0

    for uid in "${dashboard_uids[@]}"; do
        local response
        response=$(curl -s -w "\n%{http_code}" -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
            "${GRAFANA_URL}/api/dashboards/uid/${uid}" 2>/dev/null || true)

        local http_code
        http_code=$(echo "$response" | tail -n 1)

        if [[ "${http_code}" == "200" ]]; then
            local title
            title=$(echo "$response" | head -n -1 | jq -r '.dashboard.title // "Unknown"')
            log_success "Verified: ${title} (UID: ${uid})"
            ((success_count++))
        else
            log_warning "Not found: ${uid}"
            ((fail_count++))
        fi
    done

    log_info "Dashboard Verification: ${success_count} found, ${fail_count} missing"

    if [[ ${fail_count} -eq 0 ]]; then
        return 0
    else
        return 1
    fi
}

####################################################################################################
# Print Summary
####################################################################################################

print_summary() {
    echo ""
    echo "=========================================="
    echo "Dashboard Provisioning Summary"
    echo "=========================================="
    echo ""
    echo "Grafana URL: ${GRAFANA_URL}"
    echo "Datasource: ${DATASOURCE_NAME}"
    echo "Dashboards Directory: ${DASHBOARDS_DIR}"
    echo ""
    echo "Dashboards Provisioned:"
    echo "  1. System Health & Infrastructure (system-health-premium)"
    echo "  2. Request Performance & Throughput (request-performance-premium)"
    echo "  3. Pipeline Quality & Publishing (pipeline-quality-premium)"
    echo "  4. Agent Health & Status (agent-status-premium)"
    echo "  5. Operational Overview (operational-overview-premium)"
    echo ""
    echo "Next Steps:"
    echo "  1. Access Grafana: ${GRAFANA_URL}"
    echo "  2. Go to Dashboards → Browse"
    echo "  3. Navigate to the JustNews folder"
    echo "  4. Open each dashboard to verify data is flowing"
    echo ""
    echo "Documentation:"
    echo "  See ../DASHBOARD_GUIDE_ENTERPRISE.md for full usage guide"
    echo ""
    echo "=========================================="
}

####################################################################################################
# Parse Command Line Arguments
####################################################################################################

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --grafana-url)
                GRAFANA_URL="$2"
                shift 2
                ;;
            --grafana-user)
                GRAFANA_USER="$2"
                shift 2
                ;;
            --grafana-password)
                GRAFANA_PASSWORD="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN="true"
                shift
                ;;
            -v|--verbose)
                VERBOSE="true"
                shift
                ;;
            -h|--help)
                print_help
                exit 0
                ;;
            *)
                log_error "Unknown argument: $1"
                print_help
                exit 1
                ;;
        esac
    done
}

####################################################################################################
# Print Help
####################################################################################################

print_help() {
    cat << EOF
JustNews Grafana Dashboard Provisioning Script

Usage: ./provision_dashboards.sh [OPTIONS]

Options:
    --grafana-url URL           Grafana base URL (default: http://localhost:3000)
    --grafana-user USER         Grafana username (default: admin)
    --grafana-password PASSWORD Grafana password (default: admin)
    --dry-run                   Show what would be done without making changes
    -v, --verbose               Enable verbose logging
    -h, --help                  Show this help message

Environment Variables:
    GRAFANA_URL                 Override --grafana-url
    GRAFANA_USER                Override --grafana-user
    GRAFANA_PASSWORD            Override --grafana-password
    DRY_RUN                     Override --dry-run
    VERBOSE                     Override -v/--verbose

Examples:
    # Provision with defaults (localhost:3000, admin:admin)
    ./provision_dashboards.sh

    # Provision to remote Grafana instance
    ./provision_dashboards.sh --grafana-url https://grafana.example.com

    # Dry run to see what will happen
    ./provision_dashboards.sh --dry-run

    # Verbose output
    ./provision_dashboards.sh -v

EOF
}

####################################################################################################
# Main Function
####################################################################################################

main() {
    echo ""
    log_info "JustNews Grafana Dashboard Provisioning Script"
    echo ""

    # Parse command line arguments
    parse_args "$@"

    # Check prerequisites
    check_prerequisites

    # Check Grafana connection
    check_grafana_connection

    # Get or create datasource
    local datasource_id
    datasource_id=$(get_or_create_datasource)

    # Create dashboard folder
    local folder_id
    folder_id=$(create_dashboard_folder)

    # Import dashboards
    local dashboards=(
        "${DASHBOARDS_DIR}/system_health_dashboard.json"
        "${DASHBOARDS_DIR}/request_performance_dashboard.json"
        "${DASHBOARDS_DIR}/pipeline_quality_dashboard.json"
        "${DASHBOARDS_DIR}/agent_status_dashboard.json"
        "${DASHBOARDS_DIR}/operational_overview_dashboard.json"
    )

    local success_count=0
    for dashboard in "${dashboards[@]}"; do
        if import_dashboard "$dashboard" "$folder_id" "$datasource_id"; then
            ((success_count++))
        fi
    done

    log_info "Import complete: ${success_count}/5 dashboards imported"

    # Verify imports
    verify_dashboards

    # Print summary
    print_summary

    # Exit with appropriate code
    if [[ ${success_count} -eq 5 ]]; then
        log_success "All dashboards provisioned successfully!"
        exit 0
    else
        log_error "Some dashboards failed to import"
        exit 1
    fi
}

# Run main function if script is executed directly
main "$@"
