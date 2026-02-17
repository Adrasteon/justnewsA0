#!/bin/bash

################################################################################
# Vault Integration Testing Script
# Purpose: Automated testing of Vault connectivity, authentication, and secret
#          retrieval functionality
# Usage: bash test_vault_integration.sh [OPTIONS]
# Options:
#   --verbose           Show detailed output
#   --failfast          Stop at first error
#   --full              Run all tests including long-running tests
#   --dry-run           Show what would be tested without making changes
#   --help              Show this help message
################################################################################

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# Configuration
VAULT_ADDR="${VAULT_ADDR:-https://vault.prod.internal:8200}"
VAULT_NAMESPACE="${VAULT_NAMESPACE:-prod}"
VAULT_AUTH_METHOD="${VAULT_AUTH_METHOD:-approle}"
VERBOSE=false
FAILFAST=false
DRY_RUN=false
FULL_TESTS=false

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

print_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

print_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++))
}

print_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++))
    if $FAILFAST; then
        exit 1
    fi
}

print_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
    ((TESTS_SKIPPED++))
}

print_info() {
    if $VERBOSE; then
        echo -e "${YELLOW}[INFO]${NC} $1"
    fi
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if environment variable is set
check_env() {
    local var_name=$1
    if [ -z "${!var_name:-}" ]; then
        print_fail "$var_name not set"
        return 1
    fi
    return 0
}

################################################################################
# Configuration Validation
################################################################################

test_configuration() {
    print_header "Configuration"
    
    print_test "Checking required commands"
    for cmd in curl jq; do
        if command_exists "$cmd"; then
            print_pass "Command available: $cmd"
        else
            print_fail "Command not available: $cmd"
        fi
    done
    
    print_test "Configuration values"
    print_info "VAULT_ADDR: $VAULT_ADDR"
    print_info "VAULT_NAMESPACE: $VAULT_NAMESPACE"
    print_info "VAULT_AUTH_METHOD: $VAULT_AUTH_METHOD"
}

################################################################################
# Part 1: Connectivity Tests
################################################################################

test_vault_connectivity() {
    print_header "Vault Connectivity"
    
    print_test "Testing Vault health endpoint (with TLS skip for testing)"
    local response
    if response=$(curl -k -s -f "$VAULT_ADDR/v1/sys/health" 2>&1); then
        print_pass "Vault health endpoint responded"
        
        local initialized=$(echo "$response" | jq -r '.initialized // false')
        local sealed=$(echo "$response" | jq -r '.sealed // false')
        
        if [ "$initialized" = "true" ]; then
            print_pass "Vault is initialized"
        else
            print_fail "Vault not initialized"
        fi
        
        if [ "$sealed" = "false" ]; then
            print_pass "Vault is unsealed"
        else
            print_fail "Vault is sealed"
        fi
    else
        print_fail "Cannot reach Vault at $VAULT_ADDR"
        return 1
    fi
    
    print_test "Testing TLS certificate validity"
    if openssl s_client -connect "${VAULT_ADDR#https://}" -showcerts </dev/null 2>/dev/null | \
       openssl x509 -noout -checkend 86400 >/dev/null 2>&1; then
        print_pass "TLS certificate valid (expires in > 1 day)"
    else
        print_fail "TLS certificate invalid or expired"
    fi
}

################################################################################
# Part 2: Authentication Tests
################################################################################

test_approle_authentication() {
    print_header "AppRole Authentication"
    
    # Check for AppRole credentials
    if [ -z "${VAULT_ROLE_ID:-}" ] || [ -z "${VAULT_SECRET_ID:-}" ]; then
        print_skip "AppRole credentials not set (VAULT_ROLE_ID, VAULT_SECRET_ID)"
        return 0
    fi
    
    print_test "Authenticating with AppRole"
    local auth_response
    if auth_response=$(curl -k -s -X POST \
        "$VAULT_ADDR/v1/auth/approle/login" \
        -d "{\"role_id\":\"$VAULT_ROLE_ID\",\"secret_id\":\"$VAULT_SECRET_ID\"}" 2>&1); then
        
        local errors=$(echo "$auth_response" | jq -r '.errors[]? // empty')
        if [ -n "$errors" ]; then
            print_fail "Authentication error: $errors"
            return 1
        fi
        
        VAULT_TOKEN=$(echo "$auth_response" | jq -r '.auth.client_token // empty')
        if [ -n "$VAULT_TOKEN" ] && [ "$VAULT_TOKEN" != "null" ]; then
            print_pass "AppRole authentication successful, token obtained"
            print_info "Token: ${VAULT_TOKEN:0:20}..."
            export VAULT_TOKEN
        else
            print_fail "No token in authentication response"
            return 1
        fi
    else
        print_fail "AppRole authentication request failed"
        return 1
    fi
    
    # Validate token
    print_test "Validating token properties"
    if local token_info=$(curl -k -s -H "X-Vault-Token: $VAULT_TOKEN" \
        "$VAULT_ADDR/v1/auth/token/lookup-self" 2>&1); then
        
        local ttl=$(echo "$token_info" | jq -r '.data.ttl // 0')
        local policies=$(echo "$token_info" | jq -r '.data.policies[]? // empty')
        
        if [ "$ttl" -gt 0 ]; then
            print_pass "Token TTL valid: ${ttl}s"
        else
            print_fail "Token TTL invalid: $ttl"
        fi
        
        if [ -n "$policies" ]; then
            print_pass "Token policies: $(echo "$policies" | tr '\n' ', ' | sed 's/,$//')"
        else
            print_fail "Token has no policies"
        fi
    else
        print_fail "Could not lookup token"
    fi
}

################################################################################
# Part 3: Secret Retrieval Tests
################################################################################

test_secret_retrieval() {
    print_header "Secret Retrieval"
    
    if [ -z "${VAULT_TOKEN:-}" ]; then
        print_skip "No Vault token available, skipping secret tests"
        return 0
    fi
    
    print_test "Listing secrets in secret/prod/"
    if local secret_list=$(curl -k -s -X LIST \
        -H "X-Vault-Token: $VAULT_TOKEN" \
        "$VAULT_ADDR/v1/secret/prod/" 2>&1); then
        
        local keys=$(echo "$secret_list" | jq -r '.data.keys[]? // empty' | wc -l)
        if [ "$keys" -gt 0 ]; then
            print_pass "Found $keys secret keys"
            print_info "Secrets: $(echo "$secret_list" | jq -r '.data.keys[]?' | tr '\n' ', ' | sed 's/,$//')"
        else
            print_fail "No secrets found in secret/prod/"
        fi
    else
        print_fail "Could not list secrets"
    fi
    
    # Test standard secret paths
    local secret_paths=(
        "secret/data/prod/mariadb"
        "secret/data/prod/encryption"
        "secret/data/prod/huggingface"
        "secret/data/prod/django"
    )
    
    for path in "${secret_paths[@]}"; do
        print_test "Testing secret retrieval: $path"
        if local secret_content=$(curl -k -s \
            -H "X-Vault-Token: $VAULT_TOKEN" \
            "$VAULT_ADDR/v1/$path" 2>&1); then
            
            local errors=$(echo "$secret_content" | jq -r '.errors[]? // empty')
            if [ "$errors" = "permission denied" ]; then
                print_skip "Permission denied for $path (policy not granted)"
            elif [ -n "$errors" ]; then
                print_fail "$path: $errors"
            else
                local keys=$(echo "$secret_content" | jq -r '.data.data | keys[]?' | wc -l)
                if [ "$keys" -gt 0 ]; then
                    print_pass "$path: Retrieved successfully ($keys keys)"
                else
                    print_fail "$path: No data in response"
                fi
            fi
        else
            print_fail "$path: Request failed"
        fi
    done
}

################################################################################
# Part 4: Secret Rotation Tests
################################################################################

test_secret_rotation() {
    print_header "Secret Rotation"
    
    if [ -z "${VAULT_TOKEN:-}" ]; then
        print_skip "No Vault token available, skipping rotation tests"
        return 0
    fi
    
    if ! $FULL_TESTS; then
        print_skip "Full tests not enabled (use --full for rotation tests)"
        return 0
    fi
    
    print_test "Testing secret version history"
    if local metadata=$(curl -k -s \
        -H "X-Vault-Token: $VAULT_TOKEN" \
        "$VAULT_ADDR/v1/secret/metadata/prod/mariadb" 2>&1); then
        
        local versions=$(echo "$metadata" | jq -r '.data.versions | keys[]? // empty' | wc -l)
        if [ "$versions" -gt 0 ]; then
            print_pass "Secret has $versions versions in history"
        else
            print_fail "No version history found"
        fi
    else
        print_fail "Could not retrieve metadata"
    fi
}

################################################################################
# Part 5: Error Handling Tests
################################################################################

test_error_handling() {
    print_header "Error Handling"
    
    print_test "Testing invalid credentials (should fail)"
    if local response=$(curl -k -s -X POST \
        "$VAULT_ADDR/v1/auth/approle/login" \
        -d '{"role_id":"invalid","secret_id":"invalid"}' 2>&1); then
        
        local errors=$(echo "$response" | jq -r '.errors[]? // empty')
        if [ -n "$errors" ]; then
            print_pass "Invalid credentials rejected correctly"
        else
            print_fail "Invalid credentials not rejected"
        fi
    fi
    
    print_test "Testing missing secret path"
    if [ -n "${VAULT_TOKEN:-}" ]; then
        if local response=$(curl -k -s \
            -H "X-Vault-Token: $VAULT_TOKEN" \
            "$VAULT_ADDR/v1/secret/data/prod/nonexistent" 2>&1); then
            
            if echo "$response" | jq . >/dev/null 2>&1; then
                print_pass "Missing secret handled without crash"
            else
                print_fail "Invalid response format for missing secret"
            fi
        else
            print_fail "Could not test missing secret"
        fi
    fi
}

################################################################################
# Part 6: Integration Tests
################################################################################

test_fetch_secrets_script() {
    print_header "Fetch Secrets Script"
    
    if [ ! -f "infrastructure/scripts/fetch_secrets_to_env.sh" ]; then
        print_skip "fetch_secrets_to_env.sh not found"
        return 0
    fi
    
    print_test "Checking script exists and is executable"
    if [ -x "infrastructure/scripts/fetch_secrets_to_env.sh" ]; then
        print_pass "Script is executable"
    else
        print_fail "Script not executable"
    fi
    
    if ! $FULL_TESTS; then
        print_skip "Full tests not enabled (use --full to test script execution)"
        return 0
    fi
    
    print_test "Running fetch_secrets_to_env.sh in dry-run mode"
    if bash infrastructure/scripts/fetch_secrets_to_env.sh --dry-run 2>&1 | tee /tmp/fetch_test.log; then
        print_pass "Script executed without errors"
    else
        print_fail "Script failed to execute"
    fi
}

################################################################################
# Summary and Report
################################################################################

print_summary() {
    print_header "Test Summary"
    
    local total=$((TESTS_PASSED + TESTS_FAILED + TESTS_SKIPPED))
    
    echo "Tests Passed:  ${GREEN}$TESTS_PASSED${NC}"
    echo "Tests Failed:  ${RED}$TESTS_FAILED${NC}"
    echo "Tests Skipped: ${YELLOW}$TESTS_SKIPPED${NC}"
    echo "Total Tests:   $total"
    
    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "\n${GREEN}✓ All tests passed!${NC}"
        return 0
    else
        echo -e "\n${RED}✗ Some tests failed${NC}"
        return 1
    fi
}

################################################################################
# Main Execution
################################################################################

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --verbose)
                VERBOSE=true
                shift
                ;;
            --failfast)
                FAILFAST=true
                shift
                ;;
            --full)
                FULL_TESTS=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --help)
                grep '^#' "$0" | grep -v '#!/bin/bash' | sed 's/^# *//'
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    echo -e "${BLUE}========================================${NC}"
    echo "   Vault Integration Test Suite"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    # Run tests
    test_configuration
    test_vault_connectivity
    test_approle_authentication || true
    test_secret_retrieval || true
    test_secret_rotation || true
    test_error_handling || true
    test_fetch_secrets_script || true
    
    echo ""
    print_summary
    
    exit_code=$?
    exit $exit_code
}

# Run main function
main "$@"
