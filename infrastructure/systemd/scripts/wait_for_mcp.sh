#!/bin/bash
# wait_for_mcp.sh - Wait for MCP Bus to be ready before starting dependent services

set -euo pipefail

MCP_BUS_URL="${MCP_BUS_URL:-http://localhost:8000}"
MAX_WAIT="${MAX_WAIT:-90}"

echo "Waiting for MCP Bus at $MCP_BUS_URL..."

count=0
while [[ $count -lt $MAX_WAIT ]]; do
    if curl -s --max-time 30 "$MCP_BUS_URL/health" >/dev/null 2>&1; then
        echo "MCP Bus is ready!"
        exit 0
    fi

    echo "MCP Bus not ready yet, waiting... ($count/$MAX_WAIT)"
    sleep 1
    ((count++))
done

echo "MCP Bus failed to become ready within $MAX_WAIT seconds"
exit 1
