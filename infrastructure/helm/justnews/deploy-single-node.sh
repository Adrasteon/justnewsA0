#!/usr/bin/env bash

# DEPRECATED: Kubernetes/Helm deployment scripts have been removed from this workspace.
# The JustNews system now runs exclusively under systemd. Please use the systemd
# deployment scripts located at `deploy/refactor/systemd`.
#
# If you are reading this file, it remains here for historical/documentary purposes only.
# Execution of this file will print a warning and exit.

echo "ERROR: This script is DEPRECATED and has been removed. Use systemd-based deployment instead."
echo "The original Helm chart content has been archived: infrastructure/archives/helm/justnews/"
echo "See: deploy/refactor/systemd/DEPLOYMENT.md and infrastructure/README.md for systemd deployment guidance."
exit 1

# Set kubeconfig for kubectl
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Check system requirements
check_system() {
    log_info "Checking system requirements..."

    # Check CPU cores
    CPU_CORES=$(nproc)
    if [ "$CPU_CORES" -lt 8 ]; then
        log_warning "Recommended: 16+ CPU cores, found: $CPU_CORES"
    else
        log_success "CPU cores: $CPU_CORES ✓"
    fi

    # Check memory
    TOTAL_MEM=$(free -g | awk 'NR==2{printf "%.0f", $2}')
    if [ "$TOTAL_MEM" -lt 16 ]; then
        log_error "Minimum required: 16GB RAM, found: ${TOTAL_MEM}GB"
        exit 1
    elif [ "$TOTAL_MEM" -lt 32 ]; then
        log_warning "Recommended: 32GB+ RAM, found: ${TOTAL_MEM}GB"
    else
        log_success "Memory: ${TOTAL_MEM}GB ✓"
    fi

    # Check GPU
    if command -v nvidia-smi &> /dev/null; then
        GPU_COUNT=$(nvidia-smi --list-gpus | wc -l)
        if [ "$GPU_COUNT" -gt 0 ]; then
            log_success "GPU detected: $GPU_COUNT GPU(s) ✓"
            nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits
        else
            log_warning "No NVIDIA GPU detected"
        fi
    else
        log_warning "nvidia-smi not found - install NVIDIA drivers for GPU support"
    fi

    # Check available disk space
    DISK_FREE=$(df / | tail -1 | awk '{print int($4/1024/1024)}')  # GB
    if [ "$DISK_FREE" -lt 50 ]; then
        log_error "Minimum required: 50GB free disk space, found: ${DISK_FREE}GB"
        exit 1
    else
        log_success "Disk space: ${DISK_FREE}GB free ✓"
    fi
}

# Install k3s (lightweight Kubernetes)
install_k3s() {
    log_info "Installing k3s..."

    if command -v k3s &> /dev/null; then
        log_info "k3s already installed"
        return
    fi

    # Install k3s with GPU support
    curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable traefik --disable servicelb" sh -

    # Wait for k3s to start
    sleep 30

    # Set up kubectl
    mkdir -p ~/.kube
    sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
    sudo chown $(id -u):$(id -g) ~/.kube/config
    export KUBECONFIG=~/.kube/config
    export KUBECONFIG=~/.kube/config

    log_success "k3s installed and configured"
}

# Install NVIDIA GPU operator (optional)
install_nvidia_operator() {
    log_info "Installing NVIDIA GPU Operator with MPS support for RTX 3090..."

    # Add NVIDIA Helm repository
    helm repo add nvidia https://nvidia.github.io/gpu-operator
    helm repo update

    # Install GPU operator with MPS enabled for RTX 3090 (no MIG support)
    helm upgrade --install gpu-operator \
         -n gpu-operator --create-namespace \
         nvidia/gpu-operator \
         --set driver.enabled=false \
         --set devicePlugin.config.name=nvidia-mps-config \
         --wait --timeout=300s

    # Create MPS config map for GPU sharing
    kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: nvidia-mps-config
  namespace: gpu-operator
data:
  config.yaml: |
    version: v1
    sharing:
      mps: true
EOF

    log_success "NVIDIA GPU Operator installed with MPS support"
}

# Install Helm
install_helm() {
    log_info "Installing Helm..."

    if command -v helm &> /dev/null; then
        log_info "Helm already installed"
        return
    fi

    curl https://get.helm.sh/helm-v3.12.0-linux-amd64.tar.gz -o helm.tar.gz
    tar -zxvf helm.tar.gz
    sudo mv linux-amd64/helm /usr/local/bin/helm
    rm -rf linux-amd64 helm.tar.gz

    log_success "Helm installed"
}

# Setup local storage
setup_storage() {
    log_info "Setting up local storage..."

    # Install local-path-provisioner for local storage
    kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.24/deploy/local-path-storage.yaml

    # Create storage class
    kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-path
provisioner: rancher.io/local-path
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Delete
EOF

    log_success "Local storage configured"
}

# Deploy JustNews
deploy_justnews() {
    log_info "Deploying JustNews..."

    # Create namespace
    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

    # Add Helm repositories
    helm repo add bitnami https://charts.bitnami.com/bitnami
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
    helm repo add grafana https://grafana.github.io/helm-charts
    helm repo update

    # Deploy JustNews using local chart
    helm upgrade --install "$RELEASE_NAME" "$HELM_CHART" \
         --namespace "$NAMESPACE" \
         --values "$HELM_CHART/$VALUES_FILE" \
         --wait \
         --timeout 600s

    log_success "JustNews deployed"
}

# Check deployment status
check_deployment() {
    log_info "Checking deployment status..."

    # Wait for all pods to be ready
    kubectl wait --for=condition=ready pod --all -n "$NAMESPACE" --timeout=300s

    # Show pod status
    log_info "Pod status:"
    kubectl get pods -n "$NAMESPACE"

    # Show service status
    log_info "Service status:"
    kubectl get services -n "$NAMESPACE"

    # Check if GPU is being used
    GPU_PODS=$(kubectl get pods -n "$NAMESPACE" -o jsonpath='{.items[*].spec.containers[*].resources.requests.nvidia\.com/gpu}' 2>/dev/null | tr ' ' '\n' | grep -v '^$' | wc -l)
    if [ "$GPU_PODS" -gt 0 ]; then
        log_success "GPU resources allocated to $GPU_PODS pod(s)"
    fi
}

# Setup port forwarding for access
setup_port_forwarding() {
    log_info "Setting up port forwarding..."

    # Grafana
    kubectl port-forward -n "$NAMESPACE" svc/justnews-grafana 3000:80 &
    echo "Grafana: http://localhost:3000 (admin/admin_password)"

    # Prometheus
    kubectl port-forward -n "$NAMESPACE" svc/justnews-prometheus-server 9090:80 &
    echo "Prometheus: http://localhost:9090"

    # MCP Bus
    kubectl port-forward -n "$NAMESPACE" svc/mcp-bus-service 8000:8000 &
    echo "MCP Bus: http://localhost:8000"

    log_success "Port forwarding established"
}

# Show usage
usage() {
    cat << EOF
JustNews Single-Node Kubernetes Deployment Script

Optimized for AMD Ryzen 7 (16 cores) + 32GB RAM + RTX3090

Usage: $0 [COMMAND]

Commands:
    check         Check system requirements
    install       Install k3s, Helm, and dependencies
    gpu-setup     Install NVIDIA GPU operator (optional)
    storage       Setup local storage
    deploy        Deploy JustNews
    status        Check deployment status
    ports         Setup port forwarding
    all           Run full deployment (check + install + deploy + status + ports)
    cleanup       Remove JustNews deployment
    help          Show this help

Environment Variables:
    NAMESPACE     Kubernetes namespace (default: justnews)
    VALUES_FILE   Helm values file (default: values-single-node.yaml)
    RELEASE_NAME  Helm release name (default: justnews)

Examples:
    $0 check
    $0 all
    $0 deploy
    $0 status

EOF
}

# Cleanup function
cleanup() {
    log_info "Cleaning up JustNews deployment..."

    helm uninstall "$RELEASE_NAME" -n "$NAMESPACE" || true
    kubectl delete namespace "$NAMESPACE" --ignore-not-found=true

    log_success "Cleanup completed"
}

# Main command handling
case "${1:-help}" in
    check)
        check_system
        ;;
    install)
        install_k3s
        install_helm
        setup_storage
        ;;
    gpu-setup)
        install_nvidia_operator
        ;;
    storage)
        setup_storage
        ;;
    deploy)
        deploy_justnews
        ;;
    status)
        check_deployment
        ;;
    ports)
        setup_port_forwarding
        ;;
    all)
        check_system
        echo
        install_k3s
        install_helm
        setup_storage
        echo
        deploy_justnews
        echo
        check_deployment
        echo
        setup_port_forwarding
        echo
        log_success "JustNews deployment completed!"
        echo
        log_info "Access URLs:"
        echo "  Grafana: http://localhost:3000 (admin/admin_password)"
        echo "  Prometheus: http://localhost:9090"
        echo "  MCP Bus: http://localhost:8000"
        echo
        log_info "To check status: $0 status"
        log_info "To cleanup: $0 cleanup"
        ;;
    cleanup)
        cleanup
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        log_error "Unknown command: $1"
        usage
        exit 1
        ;;
esac