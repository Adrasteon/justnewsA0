#!/usr/bin/env bash

# DEPRECATED: Kubernetes manifests generation has been removed from this workspace.
# The JustNews system now runs only under systemd. This script has been replaced with
# systemd service unit templates and systemd packaging scripts.

echo "ERROR: Kubernetes support (manifests generation) has been DEPRECATED and removed."
echo "Use systemd-based deployment and refer to deploy/refactor/systemd for guidance."
exit 1

# Agent configurations: name:port:gpu_required
declare -A agents=(
    ["mcp-bus"]="8000:false"
    ["scout"]="8002:true"
    ["analyst"]="8004:true"
    ["synthesizer"]="8005:true"
    ["fact-checker"]="8003:true"
    ["memory"]="8007:false"
    ["chief-editor"]="8001:false"
    ["reasoning"]="8008:false"
    ["newsreader"]="8009:true"
    ["critic"]="8006:false"
    ["dashboard"]="8013:false"
    ["analytics"]="8012:false"
    ["archive"]="8012:false"
    # balancer removed - no longer generate manifest for it
    ["gpu-orchestrator"]="8015:false"
)

# Create directory for agent manifests
mkdir -p infrastructure/kubernetes/base/agents

# Function to generate deployment for an agent
generate_deployment() {
    local agent=$1
    local port=$2
    local gpu_required=$3

    # Convert agent name to service name format
    local service_name="${agent//-/_}_service"

    # GPU resources if required
    local gpu_resources=""
    local node_selector=""
    if [ "$gpu_required" = "true" ]; then
        gpu_resources="
          nvidia.com/gpu: 1"
        node_selector='
      nodeSelector:
        accelerator: nvidia-tesla-k80'
    fi

    cat > "infrastructure/kubernetes/base/agents/${agent}-deployment.yaml" << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${agent}
  namespace: justnews
  labels:
    app: ${agent}
    component: agent
    gpu-required: ${gpu_required}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ${agent}
  template:
    metadata:
      labels:
        app: ${agent}
        component: agent
        gpu-required: ${gpu_required}
    spec:
      containers:
      - name: ${agent}
        image: justnews/${agent}:latest
        ports:
        - containerPort: ${port}
          name: http
        envFrom:
        - configMapRef:
            name: justnews-config
        - secretRef:
            name: justnews-secrets
        env:
        - name: AGENT_NAME
          value: "${agent}"
        - name: AGENT_PORT
          value: "${port}"
        resources:
          limits:
            memory: 2Gi
            cpu: 1000m${gpu_resources}
          requests:
            memory: 1Gi
            cpu: 500m${gpu_resources}
        livenessProbe:
          httpGet:
            path: /health
            port: http
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 6
        readinessProbe:
          httpGet:
            path: /ready
            port: http
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3${node_selector}

---
apiVersion: v1
kind: Service
metadata:
  name: ${agent}-service
  namespace: justnews
  labels:
    app: ${agent}
    component: agent
spec:
  selector:
    app: ${agent}
  ports:
  - port: ${port}
    targetPort: http
    name: http
  type: ClusterIP

---
EOF

    echo "Generated Kubernetes manifests for ${agent} (port ${port}, GPU: ${gpu_required})"
}

# Generate manifests for each agent
for agent in "${!agents[@]}"; do
    IFS=':' read -r port gpu_required <<< "${agents[$agent]}"
    generate_deployment "$agent" "$port" "$gpu_required"
done

echo "All agent Kubernetes manifests generated successfully!"