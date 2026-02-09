#!/usr/bin/env bash
set -euo pipefail

# Pre-Build Cleanup Script for JustNews DevContainer
# Runs on the HOST (not in container) before docker-compose builds
# Cleans up containers and volumes from previous builds to prevent naming conflicts
# Archives MariaDB data for potential recovery

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# ============================================================================
# CONFIGURATION
# ============================================================================

# Get the directory name (used by docker-compose for container naming)
PROJECT_DIR="$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)")"
DEVCONTAINER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Backup directory
BACKUP_DIR="${HOME}/.justnews_backups"
BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/mariadb_${BACKUP_TIMESTAMP}"

# Volume and container patterns to clean
CONTAINER_PATTERNS=(
    "${PROJECT_DIR}_app"
    "${PROJECT_DIR}_mariadb"
    "${PROJECT_DIR}_chromadb"
    "${PROJECT_DIR}_vllm"
    "justnews_app"
    "justnews_mariadb"
    "justnews_chromadb"
    "justnews_vllm"
    "app"
    "mariadb"
    "chromadb"
    "vllm"
)

VOLUME_PATTERNS=(
    "${PROJECT_DIR}_justnews_deps"
    "${PROJECT_DIR}_justnews_data"
    "${PROJECT_DIR}_mariadb_data"
    "${PROJECT_DIR}_chromadb_data"
    "justnews_deps"
    "justnews_data"
    "mariadb_data"
    "chromadb_data"
)

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

check_docker() {
    if ! command -v docker &>/dev/null; then
        log_error "Docker is not installed or not in PATH"
        return 1
    fi
    
    if ! docker ps &>/dev/null; then
        log_error "Docker daemon is not running or you don't have permissions"
        return 1
    fi
    
    log_success "Docker is available"
    return 0
}

# Find containers matching patterns
find_containers() {
    local all_containers=()
    
    # Get all container names
    local containers=$(docker ps -a --format "{{.Names}}" 2>/dev/null | sort -u)
    
    for container in $containers; do
        for pattern in "${CONTAINER_PATTERNS[@]}"; do
            # Match pattern in container name (substring match)
            if [[ "$container" =~ $pattern ]]; then
                all_containers+=("$container")
                break
            fi
        done
    done
    
    echo "${all_containers[@]:-}"
}

# Find volumes matching patterns
find_volumes() {
    local all_volumes=()
    
    # Get all volume names
    local volumes=$(docker volume ls --format "{{.Name}}" 2>/dev/null | sort -u)
    
    for volume in $volumes; do
        for pattern in "${VOLUME_PATTERNS[@]}"; do
            # Match pattern in volume name (substring match)
            if [[ "$volume" =~ $pattern ]]; then
                all_volumes+=("$volume")
                break
            fi
        done
    done
    
    echo "${all_volumes[@]:-}"
}

# Archive MariaDB data
archive_mariadb_data() {
    local backup_volumes=()
    
    # Find mariadb_data volumes
    local container_ids=$(docker ps -a \
        --filter "name=mariadb" \
        --format "{{.ID}}" 2>/dev/null || true)
    
    if [ -z "$container_ids" ]; then
        log_info "No existing MariaDB containers found to archive"
        return 0
    fi
    
    mkdir -p "$BACKUP_PATH"
    
    log_info "Archiving MariaDB data from existing containers..."
    
    for container_id in $container_ids; do
        local container_name=$(docker ps -a \
            --filter "id=$container_id" \
            --format "{{.Names}}" 2>/dev/null || true)
        
        if [ -z "$container_name" ]; then
            continue
        fi
        
        log_info "  Archiving from container: $container_name"
        
        # Try to dump database if container is running or can be started
        if docker ps --filter "id=$container_id" --quiet 2>/dev/null | grep -q .; then
            # Container is running
            log_info "    Container is running, requesting graceful shutdown..."
            docker stop "$container_id" --time=10 2>/dev/null || true
        fi
        
        # Attempt to use docker cp to backup mysql data directory
        if docker ps -a --filter "id=$container_id" --quiet 2>/dev/null | grep -q .; then
            log_info "    Attempting to copy /var/lib/mysql from container..."
            if docker cp "$container_id:/var/lib/mysql" "$BACKUP_PATH/mysql_data_${container_name}" 2>/dev/null; then
                log_success "    ✓ Backed up MySQL data directory"
            else
                log_warning "    Could not copy MySQL data directory (may not exist yet)"
            fi
        fi
    done
    
    if [ -d "$BACKUP_PATH" ] && [ -n "$(ls -A "$BACKUP_PATH" 2>/dev/null)" ]; then
        log_success "MariaDB data archived to: $BACKUP_PATH"
    else
        log_warning "No MariaDB data was archived (database may be new)"
        rmdir "$BACKUP_PATH" 2>/dev/null || true
    fi
}

# Archive ChromaDB data
archive_chromadb_data() {
    log_info "Archiving ChromaDB data from existing containers..."
    
    # Find chromadb_data volume
    local chromadb_volume=$(docker volume ls --format "{{.Name}}" 2>/dev/null | grep -i chromadb || true)
    
    if [ -z "$chromadb_volume" ]; then
        log_info "No ChromaDB volumes found to archive"
        return 0
    fi
    
    mkdir -p "$BACKUP_PATH"
    
    log_info "Found ChromaDB volume(s): $chromadb_volume"
    
    for volume in $chromadb_volume; do
        log_info "  Archiving volume: $volume"
        
        # Create a temporary container to mount and copy the volume
        local temp_container="temp_backup_chroma_$$"
        
        if docker run --rm -v "$volume:/chroma_data" -v "$BACKUP_PATH:$BACKUP_PATH" \
            alpine sh -c "cp -r /chroma_data \"$BACKUP_PATH/chromadb_${volume}\" 2>/dev/null && true" 2>/dev/null; then
            log_success "  ✓ Backed up ChromaDB volume: $volume"
        else
            log_warning "  Could not backup ChromaDB volume (may be empty or inaccessible)"
        fi
    done
    
    # Also attempt to archive from running containers
    local container_ids=$(docker ps -a \
        --filter "name=chromadb" \
        --format "{{.ID}}" 2>/dev/null || true)
    
    if [ -n "$container_ids" ]; then
        log_info "Archiving ChromaDB data from running containers..."
        
        for container_id in $container_ids; do
            local container_name=$(docker ps -a \
                --filter "id=$container_id" \
                --format "{{.Names}}" 2>/dev/null || true)
            
            if [ -z "$container_name" ]; then
                continue
            fi
            
            log_info "  Archiving from container: $container_name"
            
            # Stop container if running
            if docker ps --filter "id=$container_id" --quiet 2>/dev/null | grep -q .; then
                log_info "    Stopping container for backup..."
                docker stop "$container_id" --time=5 2>/dev/null || true
            fi
            
            # Copy chroma data directory from container
            if [ -d "$BACKUP_PATH" ]; then
                if docker cp "$container_id:/chroma/data" "$BACKUP_PATH/chromadb_container_${container_name}" 2>/dev/null; then
                    log_success "    ✓ Backed up ChromaDB data directory from container"
                else
                    log_warning "    Could not copy ChromaDB data directory (may not exist yet)"
                fi
            fi
        done
    fi
}

# Stop containers
stop_containers() {
    local containers=("$@")
    
    if [ ${#containers[@]} -eq 0 ]; then
        log_info "No containers to stop"
        return 0
    fi
    
    log_info "Stopping ${#containers[@]} container(s)..."
    
    for container in "${containers[@]}"; do
        log_info "  Stopping: $container"
        docker stop "$container" --time=5 2>/dev/null || true
    done
    
    log_success "All containers stopped"
}

# Remove containers
remove_containers() {
    local containers=("$@")
    
    if [ ${#containers[@]} -eq 0 ]; then
        log_info "No containers to remove"
        return 0
    fi
    
    log_info "Removing ${#containers[@]} container(s)..."
    
    for container in "${containers[@]}"; do
        log_info "  Removing: $container"
        docker rm "$container" -f 2>/dev/null || true
    done
    
    log_success "All containers removed"
}

# Remove volumes
remove_volumes() {
    local volumes=("$@")
    
    if [ ${#volumes[@]} -eq 0 ]; then
        log_info "No volumes to remove"
        return 0
    fi
    
    log_info "Removing ${#volumes[@]} volume(s)..."
    
    for volume in "${volumes[@]}"; do
        log_info "  Removing: $volume"
        docker volume rm "$volume" 2>/dev/null || true
    done
    
    log_success "All volumes removed"
}

# Verify Docker images are available
verify_images() {
    local required_images=(
        "nvidia/cuda:12.4.1-devel-ubuntu22.04"
        "mariadb:latest"
        "chromadb/chroma:latest"
        "vllm/vllm-openai:latest"
    )
    
    log_info "Verifying Docker images..."
    
    for image in "${required_images[@]}"; do
        if docker image inspect "$image" &>/dev/null; then
            log_success "  ✓ $image exists"
        else
            log_warning "  ! $image needs to be pulled (will happen during docker-compose up)"
        fi
    done
}

# ============================================================================
# MAIN CLEANUP SEQUENCE
# ============================================================================

main() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}JustNews DevContainer Pre-Build Cleanup${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    log_info "Starting pre-build cleanup sequence..."
    log_info "Project directory: $PROJECT_DIR"
    log_info "DevContainer path: $DEVCONTAINER_DIR"
    log_info "Backup location: $BACKUP_DIR"
    echo ""
    
    # Step 1: Check Docker
    if ! check_docker; then
        log_error "Docker check failed. Skipping cleanup."
        log_info "You may need to:"
        log_info "  1. Install Docker"
        log_info "  2. Start Docker daemon"
        log_info "  3. Grant docker permissions to your user: sudo usermod -aG docker \$USER"
        return 1
    fi
    echo ""
    
    # Step 2: Find existing resources
    log_info "Scanning for existing containers and volumes..."
    local containers=($(find_containers))
    local volumes=($(find_volumes))
    
    if [ ${#containers[@]} -eq 0 ] && [ ${#volumes[@]} -eq 0 ]; then
        log_success "No existing containers or volumes found. Clean slate!"
        echo ""
        log_success "Pre-build cleanup complete (nothing to clean)"
        return 0
    fi
    echo ""
    
    # Step 3: Report findings
    if [ ${#containers[@]} -gt 0 ]; then
        log_warning "Found ${#containers[@]} container(s) from previous builds:"
        for container in "${containers[@]}"; do
            echo "    • $container"
        done
        echo ""
    fi
    
    if [ ${#volumes[@]} -gt 0 ]; then
        log_warning "Found ${#volumes[@]} volume(s) from previous builds:"
        for volume in "${volumes[@]}"; do
            echo "    • $volume"
        done
        echo ""
    fi
    
    # Step 4: Archive MariaDB data (non-destructive)
    if [ ${#containers[@]} -gt 0 ]; then
        log_info "Step 1: Archiving data from existing containers..."
        archive_mariadb_data
        echo ""
    fi
    
    # Step 4b: Archive ChromaDB data (non-destructive)
    if [ ${#volumes[@]} -gt 0 ]; then
        log_info "Step 1b: Archiving ChromaDB embeddings..."
        archive_chromadb_data
        echo ""
    fi
    
    # Step 5: Stop and remove containers
    log_info "Step 2: Removing containers..."
    stop_containers "${containers[@]}"
    wait
    
    remove_containers "${containers[@]}"
    echo ""
    
    # Step 6: Remove volumes
    log_info "Step 3: Removing volumes..."
    remove_volumes "${volumes[@]}"
    echo ""
    
    # Step 7: Verify cleanup
    log_info "Verifying cleanup..."
    local remaining_containers=($(find_containers))
    local remaining_volumes=($(find_volumes))
    
    if [ ${#remaining_containers[@]} -eq 0 ] && [ ${#remaining_volumes[@]} -eq 0 ]; then
        log_success "✓ All containers and volumes cleaned"
    else
        log_warning "Some containers/volumes remain (may be expected)"
        if [ ${#remaining_containers[@]} -gt 0 ]; then
            log_warning "  Remaining containers: ${remaining_containers[*]}"
        fi
        if [ ${#remaining_volumes[@]} -gt 0 ]; then
            log_warning "  Remaining volumes: ${remaining_volumes[*]}"
        fi
    fi
    echo ""
    
    # Step 8: Verify images
    verify_images
    echo ""
    
    # Final summary
    echo -e "${GREEN}========================================${NC}"
    log_success "Pre-build cleanup complete!"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    
    if [ -d "$BACKUP_PATH" ] && [ -n "$(ls -A "$BACKUP_PATH" 2>/dev/null)" ]; then
        log_info "Data archived to: $BACKUP_PATH"
        log_info "To restore archived data, contact your DevOps team"
        echo ""
    fi
    
    log_info "Ready for new devcontainer build!"
    log_info "New containers will use correct names without -1 suffixes"
    echo ""
    
    return 0
}

# ============================================================================
# EXECUTION
# ============================================================================

if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
    exit $?
fi
