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

prompt_docker_recovery_ack() {
    local auto_wait="${PREBUILD_WAIT_ON_DOCKER_MISSING:-true}"

    log_warning "Docker is currently unavailable in this execution context."
    log_info "Fix or verify Docker state, then re-run this script."

    if [ "$auto_wait" = "false" ]; then
        log_info "PREBUILD_WAIT_ON_DOCKER_MISSING=false; skipping interactive pause."
        return 0
    fi

    if [ -t 0 ]; then
        echo ""
        log_info "Press Enter once Docker is confirmed healthy to continue (script will then exit; re-run cleanup)."
        read -r
        return 0
    fi

    log_info "Non-interactive shell detected; cannot pause for keypress."
    return 0
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

# IDEMPOTENCE: Check for force-clean flag (allows explicit data destruction)
FORCE_CLEAN_REBUILD=false
if [[ "${1:-}" == "--force-clean" ]] || [[ "${1:-}" == "--clean" ]]; then
    FORCE_CLEAN_REBUILD=true
    log_warning "FORCE CLEAN MODE ENABLED - This will DELETE all volumes and data!"
fi

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
    "${PROJECT_DIR}_huggingface_cache"
    "justnews_deps"
    "justnews_data"
    "mariadb_data"
    "chromadb_data"
    "huggingface_cache"
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
    local all_containers=($(find_containers))
    
    # Filter for mariadb containers from the already found containers
    local container_ids=()
    for container in "${all_containers[@]}"; do
        if [[ "$container" =~ "mariadb" ]]; then
            container_ids+=("$container")
        fi
    done
    
    if [ ${#container_ids[@]} -eq 0 ]; then
        log_info "No existing MariaDB containers found to archive"
        return 0
    fi
    
    mkdir -p "$BACKUP_PATH"
    
    log_info "Archiving MariaDB data from existing containers..."
    
    for container_id in "${container_ids[@]}"; do
        local container_name="$container_id"
        
        log_info "  Archiving from container: $container_name"
        
        # Try to dump database if container is running or can be started
        if docker ps --filter "name=^/${container_name}$" --format "{{.Status}}" 2>/dev/null | grep -q "Up"; then
            # Container is running
            log_info "    Container is running, requesting graceful shutdown..."
            docker stop "$container_name" --time=10 2>/dev/null || true
        fi
        
        # Attempt to use docker cp to backup mysql data directory
        log_info "    Attempting to copy /var/lib/mysql from container..."
        if docker cp "${container_name}:/var/lib/mysql" "$BACKUP_PATH/mysql_data_${container_name}" 2>/dev/null; then
            log_success "    ✓ Backed up MySQL data directory"
        else
            log_warning "    Could not copy MySQL data directory (may not exist yet)"
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
    local all_containers=($(find_containers))
    local container_ids=()
    for container in "${all_containers[@]}"; do
        if [[ "$container" =~ "chromadb" ]]; then
            container_ids+=("$container")
        fi
    done
    
    if [ ${#container_ids[@]} -gt 0 ]; then
        log_info "Archiving ChromaDB data from containers..."
        
        for container_id in "${container_ids[@]}"; do
            local container_name="$container_id"
            
            log_info "  Archiving from container: $container_name"
            
            # Stop container if running
            if docker ps --filter "name=^/${container_name}$" --format "{{.Status}}" 2>/dev/null | grep -q "Up"; then
                log_info "    Stopping container for backup..."
                docker stop "$container_name" --time=5 2>/dev/null || true
            fi
            
            # Copy chroma data directory from container
            if [ -d "$BACKUP_PATH" ]; then
                if docker cp "${container_name}:/chroma/data" "$BACKUP_PATH/chromadb_container_${container_name}" 2>/dev/null; then
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

# Remove volumes (IDEMPOTENT: Check if volume is in-use before removing)
remove_volumes() {
    # DEFENSE IN DEPTH: Double-check the force flag
    # This prevents accidental deletion even if this function is called incorrectly
    if [ "$FORCE_CLEAN_REBUILD" != true ]; then
        log_info "  Safe Mode: Skipping volume removal logic inside remove_volumes"
        return 0
    fi

    local volumes=("$@")
    
    if [ ${#volumes[@]} -eq 0 ]; then
        log_info "No volumes to remove"
        return 0
    fi
    
    log_info "Checking volume status before removal..."
    
    for volume in "${volumes[@]}"; do
        # Check if volume is being used by any container (even stopped ones)
        # Using a more reliable check: docker ps -a --filter volume=...
        local in_use=$(docker ps -a --filter "volume=$volume" --format "{{.ID}}" 2>/dev/null | wc -l)
        
        if [ "$in_use" -gt 0 ]; then
            log_warning "  Preserving: $volume (recorded as in-use by $in_use container(s))"
        else
            log_info "  Removing orphaned volume: $volume"
            docker volume rm "$volume" 2>/dev/null || true
        fi
    done
    
    log_success "Volume cleanup completed"
}

# Check if a volume is currently being used by running containers
is_volume_in_use() {
    local volume="$1"
    
    # Get containers that use this volume
    local containers=$(docker ps -a --format "table {{.ID}}\t{{.Mounts}}" 2>/dev/null | grep "$volume" | wc -l)
    
    if [ "$containers" -gt 0 ]; then
        return 0  # Volume is in use
    else
        return 1  # Volume is not in use
    fi
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
    local found_containers=0
    local found_volumes=0
    local found_running_containers=0
    local archived_any_data=0
    local removed_any_containers=0
    local removed_any_volumes=0
    local preserved_any_volumes=0
    local preserved_any_containers=0

    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}JustNews DevContainer Pre-Build Cleanup${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    log_info "Starting pre-build cleanup sequence..."
    log_info "Project directory: $PROJECT_DIR"
    log_info "DevContainer path: $DEVCONTAINER_DIR"
    log_info "Backup location: $BACKUP_DIR"
    
    if [ "$FORCE_CLEAN_REBUILD" = true ]; then
        log_warning "MODE: FORCE_CLEAN_REBUILD is ENABLED. Volumes WILL be removed."
    else
        log_success "MODE: IDEMPOTENT. Volumes will be PRESERVED."
    fi
    echo ""
    
    # Step 1: Check Docker
    if ! check_docker; then
        log_error "Docker check failed. Cleanup not executed."
        log_info "You may need to:"
        log_info "  1. Install Docker"
        log_info "  2. Start Docker daemon"
        log_info "  3. Grant docker permissions to your user: sudo usermod -aG docker \$USER"
        prompt_docker_recovery_ack
        log_warning "Pre-build cleanup exited without changes. Re-run after Docker is functional."
        return 0
    fi
    echo ""
    
    # Step 2: Find existing resources
    log_info "Scanning for existing containers and volumes..."
    local containers=($(find_containers))
    local volumes=($(find_volumes))
    local running_containers=()
    for container in "${containers[@]}"; do
        if docker ps --filter "name=^/${container}$" --format "{{.Names}}" 2>/dev/null | grep -q "^${container}$"; then
            running_containers+=("$container")
        fi
    done
    found_containers=${#containers[@]}
    found_volumes=${#volumes[@]}
    found_running_containers=${#running_containers[@]}
    
    if [ ${#containers[@]} -eq 0 ] && [ ${#volumes[@]} -eq 0 ]; then
        log_success "No existing containers or volumes found. Clean slate!"
        echo ""
        log_success "Pre-build cleanup complete (nothing to clean)"
        log_info "Ready for devcontainer build (no prior resources detected)"
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
    
    # Step 4/5: Cleanup behavior differs by mode
    if [ "$FORCE_CLEAN_REBUILD" = true ]; then
        # Step 4: Archive MariaDB data (non-destructive)
        if [ ${#containers[@]} -gt 0 ]; then
            log_info "Step 1: Archiving data from existing containers..."
            archive_mariadb_data
            if [ -d "$BACKUP_PATH" ] && [ -n "$(ls -A "$BACKUP_PATH" 2>/dev/null)" ]; then
                archived_any_data=1
            fi
            echo ""
        fi
        
        # Step 4b: Archive ChromaDB data (non-destructive)
        if [ ${#volumes[@]} -gt 0 ]; then
            log_info "Step 1b: Archiving ChromaDB embeddings..."
            archive_chromadb_data
            if [ -d "$BACKUP_PATH" ] && [ -n "$(ls -A "$BACKUP_PATH" 2>/dev/null)" ]; then
                archived_any_data=1
            fi
            echo ""
        fi

        # Step 5: Stop and remove containers
        log_info "Step 2: Removing containers..."
        stop_containers "${containers[@]}"
        wait

        remove_containers "${containers[@]}"
        if [ ${#containers[@]} -gt 0 ]; then
            removed_any_containers=1
        fi
        echo ""
    else
        # IDEMPOTENT MODE: do not disrupt currently running containers
        if [ "$found_running_containers" -gt 0 ]; then
            preserved_any_containers=1
            log_success "Step 1: Preserving ${found_running_containers} running container(s) in idempotent mode"
            log_info "  → No archive/stop/remove actions executed for running containers"
            echo ""
        fi

        if [ "$found_containers" -gt "$found_running_containers" ]; then
            log_info "Step 1b: Leaving non-running matched containers untouched in idempotent mode"
            log_info "  → Use --force-clean to archive and remove stale containers"
            echo ""
        fi
    fi
    
    # Step 6: Remove volumes (IDEMPOTENT MODE - preserve by default)
    log_info "Step 3: Handling volumes (IDEMPOTENT MODE)..."
    
    if [ "$FORCE_CLEAN_REBUILD" = true ]; then
        # FORCE CLEAN: User explicitly requested data destruction
        log_warning "  FORCE CLEAN: Removing all volumes (DATA WILL BE LOST)"
        remove_volumes "${volumes[@]}"
        if [ ${#volumes[@]} -gt 0 ]; then
            removed_any_volumes=1
        fi
    else
        # IDEMPOTENT: Preserve existing volumes for data preservation
        log_info "  IDEMPOTENT MODE: Skipping volume removal to preserve data"
        log_info "  → Containers are preserved; volumes are retained"
        
        if [ ${#volumes[@]} -gt 0 ]; then
            preserved_any_volumes=1
            log_success "  ✓ Data volumes preserved"
            log_info "  → To force a clean rebuild: .devcontainer/scripts/pre-build-cleanup.sh --force-clean"
        fi
    fi
    echo ""
    
    # Step 7: Verify cleanup
    log_info "Verifying cleanup..."
    local remaining_containers=($(find_containers))
    local remaining_volumes=($(find_volumes))
    
    if [ "$FORCE_CLEAN_REBUILD" = true ]; then
        if [ ${#remaining_containers[@]} -eq 0 ] && [ ${#remaining_volumes[@]} -eq 0 ]; then
            log_success "✓ All containers and volumes cleaned"
        else
            log_warning "Some containers/volumes remain (FORCE CLEAN failed to remove some items)"
        fi
    else
        if [ ${#remaining_containers[@]} -gt 0 ]; then
            log_success "✓ Existing containers preserved in idempotent mode (${#remaining_containers[@]} matched)"
        fi
        if [ ${#remaining_volumes[@]} -gt 0 ]; then
            log_success "✓ Existing volumes preserved as requested (${#remaining_volumes[@]} volumes)"
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
    
    if [ "$FORCE_CLEAN_REBUILD" = true ]; then
        log_warning "FORCE CLEAN MODE: All volumes were removed (fresh start)"
        if [ "$archived_any_data" -eq 1 ]; then
            log_info "Any archived data can be found at: $BACKUP_DIR"
        fi
    else
        if [ "$preserved_any_volumes" -eq 1 ]; then
            log_success "IDEMPOTENT MODE ACTIVE: Data volumes preserved"
            log_info "Workflow data should remain available after container start"
            log_info "To force a clean rebuild next time, run:"
            log_info "  bash .devcontainer/scripts/pre-build-cleanup.sh --force-clean"
        else
            log_info "IDEMPOTENT MODE ACTIVE: No matching data volumes found to preserve"
        fi
    fi
    
    if [ -d "$BACKUP_PATH" ] && [ -n "$(ls -A "$BACKUP_PATH" 2>/dev/null)" ]; then
        log_info ""
        log_info "Backup archive created at: $BACKUP_PATH"
        log_info "To restore archived data, contact your DevOps team"
        echo ""
    fi
    
    if [ "$removed_any_containers" -eq 1 ]; then
        log_info "Ready for new devcontainer build (previous containers removed)"
    elif [ "$preserved_any_containers" -eq 1 ]; then
        log_info "Ready for new devcontainer build (running containers preserved)"
    else
        log_info "Ready for new devcontainer build"
    fi

    if [ "$FORCE_CLEAN_REBUILD" = true ]; then
        if [ "$removed_any_volumes" -eq 1 ]; then
            log_warning "Next build will start with fresh volumes"
        else
            log_info "No matching volumes were removed in force-clean mode"
        fi
    else
        if [ "$preserved_any_volumes" -eq 1 ]; then
            log_info "Preserved volumes will be mounted on container start"
        elif [ "$found_volumes" -eq 0 ]; then
            log_info "No existing data volumes were present before build"
        fi
    fi
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
